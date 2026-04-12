import json
import re
from pathlib import Path

from app.services.model_provider import OpenAIProvider
from app.services.page_fetcher import fetch_page_snapshot, snapshot_for_prompt
from app.services.prompt_templates import ARTIFACT_TYPES, build_prompt, prompt_version_for
from app.services.scoring import TrendSignals, score_candidate


class TrendScoutAgent:
    name = "TrendScoutAgent"

    def __init__(self, source_config_path: str = "config/trend_sources.json") -> None:
        self.source_config_path = source_config_path

    def _load_sources(self) -> list[dict]:
        path = Path(self.source_config_path)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def run(self, niche_tags: list[str]) -> list[dict]:
        seeds = self._load_sources()
        recs: list[dict] = []
        normalized_tags = {tag.lower() for tag in niche_tags}
        requested_platforms = normalized_tags.intersection({"instagram", "x"})

        for seed in seeds:
            seed_platform = seed.get("platform", "").lower()
            if requested_platforms and seed_platform and seed_platform not in requested_platforms:
                continue
            signals = TrendSignals(**seed["signals"])
            if niche_tags:
                signals.niche_relevance = min(1.0, signals.niche_relevance + 0.08)
            score, reasons = score_candidate(signals)
            recs.append(
                {
                    "source_url": seed["source_url"],
                    "title": seed["title"],
                    "score": score,
                    "reasons": reasons,
                    "signals": {
                        "recency": signals.recency,
                        "engagement": signals.engagement,
                        "structural_quality": signals.structural_quality,
                        "niche_relevance": signals.niche_relevance,
                        "novelty": signals.novelty,
                    },
                }
            )

        return sorted(recs, key=lambda x: x["score"], reverse=True)


class PageAnalyzerAgent:
    name = "PageAnalyzerAgent"

    def __init__(self, provider: OpenAIProvider | None = None) -> None:
        self.provider = provider or OpenAIProvider()

    def _parsed_analysis(self, llm_text: str) -> dict:
        if not llm_text:
            return {}
        try:
            payload = json.loads(llm_text)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def run(self, source_url: str) -> dict:
        snapshot = fetch_page_snapshot(source_url)
        platform = "instagram" if "instagram.com" in source_url else "x" if "x.com" in source_url else "web"
        prompt = (
            "Analyze this page snapshot and infer its marketing structure. "
            "Return strict JSON with keys: offer, cta, proof, structure, headline_pattern, what_is_selling, "
            "marketing_style. Keep structure as an array of short strings.\n"
            f"Snapshot: {snapshot_for_prompt(snapshot)}"
        )
        llm_text = self.provider.generate_text(prompt)
        parsed = self._parsed_analysis(llm_text)
        fallback_offer = snapshot.get("offer") or "Bundle-first with limited-time urgency"
        fallback_cta = "Tap through to learn more and buy now" if platform in {"instagram", "x"} else "Single high-contrast buy CTA repeated across sections"
        fallback_proof = "Social proof, comments, and audience response" if platform in {"instagram", "x"} else "UGC testimonials above fold + trust badges"
        fallback_structure = ["Hero", "Problem", "Benefits", "Proof", "Offer", "FAQ", "CTA"]
        fallback_headline = "Outcome-first + timeframe + confidence cue"
        sold_product = snapshot.get("title") or snapshot.get("description") or "Unknown product/category"
        marketing_style = "Social-first performance marketing with hooks, proof, and repeated CTA" if platform in {"instagram", "x"} else "Direct-response performance marketing with visual proof"
        return {
            "reference_url": source_url,
            "offer": str(parsed.get("offer") or fallback_offer)[:220],
            "cta": str(parsed.get("cta") or fallback_cta)[:180],
            "proof": str(parsed.get("proof") or fallback_proof)[:220],
            "structure": parsed.get("structure") if isinstance(parsed.get("structure"), list) and parsed.get("structure") else fallback_structure,
            "headline_pattern": str(parsed.get("headline_pattern") or fallback_headline)[:180],
            "what_is_selling": str(parsed.get("what_is_selling") or sold_product)[:180],
            "marketing_style": str(parsed.get("marketing_style") or marketing_style)[:220],
            "likes": snapshot.get("likes"),
            "comments": snapshot.get("comments"),
            "views": snapshot.get("views"),
            "followers": snapshot.get("followers"),
            "description": snapshot.get("description"),
            "fetch_ok": snapshot.get("fetch_ok", False),
            "final_url": snapshot.get("final_url"),
            "platform": platform,
        }


class BrandPatternAgent:
    name = "BrandPatternAgent"

    def run(self, page_analysis: dict) -> dict:
        return {
            "tone": "confident, benefit-led, direct response",
            "headline_style": page_analysis["headline_pattern"],
            "cta_style": page_analysis["cta"],
            "proof_strategy": page_analysis["proof"],
            "raw_extraction": page_analysis,
            "anonymized_features": {
                "headline_formula": "Outcome + timeframe + certainty",
                "section_order": page_analysis["structure"],
                "offer_type": "bundle + urgency",
                "marketing_style": page_analysis.get("marketing_style", ""),
            },
        }


class VisionProductAgent:
    name = "VisionProductAgent"

    def __init__(self, provider: OpenAIProvider | None = None) -> None:
        self.provider = provider or OpenAIProvider()

    def run(self, file_path: str) -> dict:
        suffix = Path(file_path).suffix.lower()
        format_name = suffix.replace(".", "") if suffix else "unknown"
        analysis = self.provider.analyze_image(
            file_path,
            (
                "Analyze this product image for marketing. "
                "Return: likely product type, 3 audience angles, and key visual hooks."
            ),
        )
        return {
            "image_path": file_path,
            "detected_format": format_name,
            "product_guess": "consumer product" if not analysis else analysis[:120],
            "angles": ["time-saving", "premium feel", "social proof readiness"],
        }


class StrategyPlannerAgent:
    name = "StrategyPlannerAgent"

    def __init__(self, provider: OpenAIProvider | None = None) -> None:
        self.provider = provider or OpenAIProvider()

    def run(self, brand_pattern: dict, product_context: dict) -> str:
        prompt = (
            "Create an executable marketing plan for this product launch. "
            "Return a concise step-by-step plan with audience angle, offer, channel priorities, creative direction, "
            "and launch sequence.\n"
            f"Brand pattern: {json.dumps(brand_pattern)}\n"
            f"Product context: {json.dumps(product_context)}"
        )
        llm_text = self.provider.generate_text(prompt)
        if llm_text:
            return llm_text
        return (
            "1. Lead with a premium, outcome-first hook tailored to buyers seeking faster results.\n"
            "2. Use product visuals that emphasize premium feel and easy routine integration.\n"
            "3. Launch with hero copy, short-form ads, and social proof-led follow-up content.\n"
            "4. Repeat a direct CTA across landing page, email, and social touchpoints.\n"
            "5. Sequence the campaign as teaser, proof, offer, and urgency-driven conversion push."
        )


class DeliverablesAgent:
    name = "DeliverablesAgent"

    def __init__(self, provider: OpenAIProvider | None = None) -> None:
        self.provider = provider or OpenAIProvider()

    def _parse_json(self, text: str) -> dict:
        if not text:
            return {}
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _parse_artifacts(self, artifacts: dict[str, str]) -> dict:
        hero = {}
        try:
            hero = json.loads(artifacts.get("hero", "{}"))
        except Exception:
            hero = {}
        creative_brief = {}
        try:
            creative_brief = json.loads(artifacts.get("creative_brief", "{}"))
        except Exception:
            creative_brief = {}
        ads = []
        try:
            ads = json.loads(artifacts.get("ads", "[]"))
        except Exception:
            ads = [line.strip() for line in artifacts.get("ads", "").splitlines() if line.strip()]
        email_text = artifacts.get("email", "")
        email_match = re.search(r"Subject:\s*(.*?)(?:\n|$)\s*Body:\s*([\s\S]*)", email_text, flags=re.IGNORECASE)
        email = {
            "subject": email_match.group(1).strip() if email_match else "Campaign email",
            "body": email_match.group(2).strip() if email_match else email_text.strip(),
        }
        sections = [part.strip() for part in re.split(r"->|\n", artifacts.get("page_draft", "")) if part.strip()]
        image_concepts = [part.strip() for part in re.split(r"\n(?=Concept\s*\d+:)", artifacts.get("image_concepts", "")) if part.strip()]
        video_scenes = [part.strip() for part in re.split(r"\n(?=(?:Hook:|Scene\s*\d+:|CTA:))", artifacts.get("video_script", "")) if part.strip()]
        return {
            "hero": {
                "headline": hero.get("headline", ""),
                "subheadline": hero.get("subheadline", ""),
                "cta": hero.get("cta", ""),
            },
            "ads": ads,
            "email": email,
            "social": {"caption": artifacts.get("social", "").strip()},
            "landing_page": {"sections": sections},
            "creative_brief": creative_brief,
            "image_concepts": [{"title": concept.split(":", 1)[0], "description": concept} for concept in image_concepts],
            "video_storyboard": [{"scene": f"Scene {index + 1}", "description": scene} for index, scene in enumerate(video_scenes)],
            "product_description": artifacts.get("product_description", "").strip(),
        }

    def _build_image_prompt(self, deliverables: dict, strategy_plan: str | None) -> str:
        hero = deliverables.get("hero", {})
        brief = deliverables.get("creative_brief", {})
        prompt = (
            "Draw a polished paid-social product ad image. "
            "Subject: the uploaded product as the main focus. "
            "Shot type: clean hero product shot, medium close-up. "
            "Action: product presented as premium and ready to buy. "
            "Setting: simple studio or lifestyle backdrop that supports conversion, not clutter. "
            "Lighting: bright commercial lighting, crisp details, premium contrast. "
            f"Visual direction: {brief.get('visual_direction', '')[:180]}. "
            f"Tone: {brief.get('tone', '')[:90]}. "
            f"Headline direction: {hero.get('headline', '')[:140]}. "
            f"CTA emphasis: {hero.get('cta', '')[:80]}. "
            "Output one final ad image, photorealistic, no collage, minimal text."
        )
        return prompt[:900]

    def _build_video_prompt(self, deliverables: dict, strategy_plan: str | None) -> str:
        scenes = deliverables.get("video_storyboard", [])
        scene_text = " ".join(
            [
                " ".join(str(value) for value in scene.values() if value)
                for scene in scenes
                if isinstance(scene, dict)
            ]
        )
        hero = deliverables.get("hero", {})
        prompt = (
            "Create a short vertical paid-social marketing video. "
            "Shot type: fast premium ad cuts, designed for mobile viewing. "
            "Subject: the product as the hero asset. "
            "Action: show the product clearly, then show it in use, then end on a conversion-focused finish. "
            "Setting: clean, premium, modern environment. "
            "Lighting: bright commercial lighting with strong subject separation. "
            f"Core hook: {hero.get('headline', '')[:140]}. "
            f"Storyboard guidance: {scene_text[:280]}. "
            f"Tone: {deliverables.get('creative_brief', {}).get('tone', '')[:90]}. "
            "Keep it realistic, visually coherent, and suitable for a product ad. No copyrighted characters, no real people."
        )
        return prompt[:900]

    def _media_url(self, generated_path: str) -> str:
        marker = "/uploads/"
        normalized = generated_path.replace("\\", "/")
        if marker in normalized:
            return normalized[normalized.index(marker):]
        if normalized.startswith("uploads/"):
            return f"/{normalized}"
        return generated_path

    def _generate_media_assets(
        self,
        deliverables: dict,
        *,
        output_dir: str,
        reference_image_path: str | None,
        strategy_plan: str | None,
    ) -> dict:
        media_assets = {"images": [], "videos": [], "errors": []}
        if not reference_image_path:
            media_assets["errors"].append("No uploaded product image was available for media generation.")
            return media_assets

        image_path = str(Path(output_dir) / "generated-ad-image.png")
        try:
            created_image = self.provider.generate_image(
                self._build_image_prompt(deliverables, strategy_plan),
                image_path,
                reference_image_path=reference_image_path,
            )
        except Exception as exc:
            created_image = ""
            media_assets["errors"].append(f"Image generation failed: {exc}")
        if created_image:
            media_assets["images"].append({"url": self._media_url(created_image), "label": "Primary ad image"})
        elif not any(message.startswith("Image generation failed:") for message in media_assets["errors"]):
            media_assets["errors"].append("Image generation is unavailable for the current API setup.")

        video_path = str(Path(output_dir) / "generated-ad-video.mp4")
        try:
            created_video = self.provider.generate_video(
                self._build_video_prompt(deliverables, strategy_plan),
                video_path,
                reference_image_path=reference_image_path,
            )
        except Exception as exc:
            created_video = ""
            media_assets["errors"].append(f"Video generation failed: {exc}")
        if created_video:
            media_assets["videos"].append({"url": self._media_url(created_video), "label": "Primary ad video"})
        elif not any(message.startswith("Video generation failed:") for message in media_assets["errors"]):
            media_assets["errors"].append("Video generation is unavailable for the current API setup.")
        return media_assets

    def run(
        self,
        artifacts: dict[str, str],
        strategy_plan: str | None = None,
        *,
        output_dir: str | None = None,
        reference_image_path: str | None = None,
    ) -> dict:
        fallback = self._parse_artifacts(artifacts)
        prompt = (
            "Turn these campaign artifacts into polished deliverables. "
            "Return strict JSON with keys: hero, product_description, ads, email, social, landing_page, creative_brief, image_concepts, video_storyboard. "
            "Use objects and arrays, not markdown. "
            "hero should have headline, subheadline, cta. "
            "ads should be an array of objects with title, body, cta. "
            "email should have subject and body. "
            "social should have caption and optional hashtags array. "
            "landing_page should have sections as an array of objects with title and copy. "
            "creative_brief should have visual_direction, tone, audience_angles, cta_emphasis. "
            "image_concepts should be an array of objects with title, scene, overlay, cta. "
            "video_storyboard should be an array of objects with scene, visual, voiceover, on_screen_text. "
            "Do not include unsupported claims.\n"
            f"Artifacts: {json.dumps(artifacts, indent=2, sort_keys=True)}\n"
            f"Strategy: {strategy_plan or ''}"
        )
        parsed = self._parse_json(self.provider.generate_text(prompt))
        if not parsed:
            deliverables = fallback
        else:
            deliverables = {
            "hero": parsed.get("hero") or fallback["hero"],
            "product_description": parsed.get("product_description") or fallback["product_description"],
            "ads": parsed.get("ads") or fallback["ads"],
            "email": parsed.get("email") or fallback["email"],
            "social": parsed.get("social") or fallback["social"],
            "landing_page": parsed.get("landing_page") or fallback["landing_page"],
            "creative_brief": parsed.get("creative_brief") or fallback["creative_brief"],
            "image_concepts": parsed.get("image_concepts") or fallback["image_concepts"],
            "video_storyboard": parsed.get("video_storyboard") or fallback["video_storyboard"],
        }
        if output_dir:
            deliverables["media_assets"] = self._generate_media_assets(
                deliverables,
                output_dir=output_dir,
                reference_image_path=reference_image_path,
                strategy_plan=strategy_plan,
            )
        return deliverables


class CampaignGeneratorAgent:
    name = "CampaignGeneratorAgent"

    _UNSAFE_PHRASE_REPLACEMENTS = {
        "100% guaranteed": "designed to deliver",
        "guaranteed": "designed to help",
        "instant results": "fast visible progress",
        "risk-free": "easy to try",
        "works for everyone": "built for a wide range of customers",
        "scientifically proven": "supported by product design choices",
        "clinically proven": "tested with care",
        "cure": "support",
    }

    def __init__(self, provider: OpenAIProvider | None = None) -> None:
        self.provider = provider or OpenAIProvider()

    def _fallback_bundle(self, brand_pattern: dict, product_context: dict) -> dict:
        return {
            "hero": {
                "headline": "Get Premium Results in Days, Not Months",
                "subheadline": "Built for modern buyers who want visible outcomes with less effort.",
                "cta": "Get Yours Today",
            },
            "product_description": "A high-impact product crafted to deliver fast, reliable results with a premium experience.",
            "ads": [
                "Ad A: Fast results. Premium quality. Try it today.",
                "Ad B: The smarter way to upgrade your daily routine.",
                "Ad C: Trusted feel, visible outcomes, low effort.",
            ],
            "email": "Subject: Your faster path to premium results\nBody: Discover how this product helps you get better outcomes with less effort.",
            "social": "Launch-ready and built to perform. Tap to see why customers switch.",
            "page_draft": "Hero -> Benefits -> Proof -> Offer -> FAQ -> CTA",
            "creative_brief": {
                "visual_direction": "Clean product focus, high contrast CTA blocks, authentic lifestyle context",
                "tone": brand_pattern["tone"],
                "product_angles": product_context["angles"],
            },
            "image_concepts": (
                "Concept 1: clean hero close-up with premium lighting, short overlay, direct CTA.\n"
                "Concept 2: lifestyle use-case shot with social proof badge and benefit overlay.\n"
                "Concept 3: before/after or routine transformation layout with offer card."
            ),
            "video_script": (
                "Hook: Stop scrolling if you want faster premium results.\n"
                "Scene 1: close product shot.\n"
                "Scene 2: show easy use in routine.\n"
                "Scene 3: proof and benefit callout.\n"
                "CTA: Try it today."
            ),
        }

    def _generate_hero(self, prompt: str, fallback: dict) -> dict:
        llm_text = self.provider.generate_text(prompt)
        if not llm_text:
            return fallback
        parsed = {"headline": fallback["headline"], "subheadline": fallback["subheadline"], "cta": fallback["cta"]}
        for raw_line in llm_text.splitlines():
            line = raw_line.strip()
            if ":" not in line:
                continue
            label, value = line.split(":", 1)
            key = label.strip().lower()
            value = value.strip()
            if key == "headline" and value:
                parsed["headline"] = value[:120]
            elif key == "subheadline" and value:
                parsed["subheadline"] = value[:180]
            elif key == "cta" and value:
                parsed["cta"] = value[:80]
        return parsed

    def _generate_ads(self, prompt: str, fallback: list[str]) -> list[str]:
        llm_text = self.provider.generate_text(prompt)
        if not llm_text:
            return fallback
        ads: list[str] = []
        for raw_line in llm_text.splitlines():
            line = raw_line.strip()
            if ":" in line:
                _, value = line.split(":", 1)
                line = value.strip()
            if line:
                ads.append(line[:160])
        return ads[:3] if ads else fallback

    def _generate_email(self, prompt: str, fallback: str) -> str:
        llm_text = self.provider.generate_text(prompt)
        return llm_text or fallback

    def _generate_text_artifact(self, prompt: str, fallback: str) -> str:
        llm_text = self.provider.generate_text(prompt)
        return llm_text or fallback

    def _generate_creative_brief(self, prompt: str, fallback: dict) -> dict:
        llm_text = self.provider.generate_text(prompt)
        if not llm_text:
            return fallback
        return {
            "visual_direction": llm_text[:220],
            "tone": fallback["tone"],
            "product_angles": fallback["product_angles"],
        }

    def _sanitize_text(self, text: str) -> str:
        sanitized = text
        for unsafe_phrase, replacement in self._UNSAFE_PHRASE_REPLACEMENTS.items():
            sanitized = re.sub(re.escape(unsafe_phrase), replacement, sanitized, flags=re.IGNORECASE)
        return sanitized

    def _sanitize_bundle(self, bundle: dict) -> dict:
        hero = bundle.get("hero", {})
        bundle["hero"] = {
            "headline": self._sanitize_text(hero.get("headline", "")),
            "subheadline": self._sanitize_text(hero.get("subheadline", "")),
            "cta": self._sanitize_text(hero.get("cta", "")),
        }
        for key in ("product_description", "email", "social", "page_draft", "image_concepts", "video_script"):
            bundle[key] = self._sanitize_text(bundle.get(key, ""))
        bundle["ads"] = [self._sanitize_text(ad) for ad in bundle.get("ads", [])]
        creative_brief = bundle.get("creative_brief", {})
        bundle["creative_brief"] = {
            **creative_brief,
            "visual_direction": self._sanitize_text(creative_brief.get("visual_direction", "")),
            "tone": self._sanitize_text(creative_brief.get("tone", "")),
        }
        return bundle

    def run(
        self,
        brand_pattern: dict,
        product_context: dict,
        artifact_instructions: dict[str, str] | None = None,
        strategy_plan: str | None = None,
    ) -> dict:
        fallback = self._fallback_bundle(brand_pattern, product_context)
        instructions = artifact_instructions or {}
        prompts = {
            artifact_type: build_prompt(
                artifact_type,
                brand_pattern,
                product_context,
                instruction=instructions.get(artifact_type),
                strategy_plan=strategy_plan,
            )
            for artifact_type in ARTIFACT_TYPES
        }
        prompt_versions = {artifact_type: prompt_version_for(artifact_type) for artifact_type in ARTIFACT_TYPES}
        bundle = {
            "hero": self._generate_hero(prompts["hero"], fallback["hero"]),
            "product_description": self._generate_text_artifact(
                prompts["product_description"], fallback["product_description"]
            ),
            "ads": self._generate_ads(prompts["ads"], fallback["ads"]),
            "email": self._generate_email(prompts["email"], fallback["email"]),
            "social": self._generate_text_artifact(prompts["social"], fallback["social"]),
            "page_draft": self._generate_text_artifact(prompts["page_draft"], fallback["page_draft"]),
            "creative_brief": self._generate_creative_brief(prompts["creative_brief"], fallback["creative_brief"]),
            "image_concepts": self._generate_text_artifact(prompts["image_concepts"], fallback["image_concepts"]),
            "video_script": self._generate_text_artifact(prompts["video_script"], fallback["video_script"]),
            "_prompt_versions": prompt_versions,
            "_artifact_instructions": instructions,
        }
        return self._sanitize_bundle(bundle)


class QAComplianceAgent:
    name = "QAComplianceAgent"

    def _combined_copy(self, campaign_bundle: dict) -> str:
        hero = campaign_bundle.get("hero", {})
        ads = campaign_bundle.get("ads", [])
        creative_brief = campaign_bundle.get("creative_brief", {})
        parts = [
            hero.get("headline", ""),
            hero.get("subheadline", ""),
            hero.get("cta", ""),
            campaign_bundle.get("product_description", ""),
            *ads,
            campaign_bundle.get("email", ""),
            campaign_bundle.get("social", ""),
            campaign_bundle.get("page_draft", ""),
            creative_brief.get("visual_direction", ""),
            creative_brief.get("tone", ""),
        ]
        return " ".join(part for part in parts if part)

    def _tone_alignment_check(self, campaign_bundle: dict) -> dict:
        creative_brief = campaign_bundle.get("creative_brief", {})
        expected_tone = creative_brief.get("tone", "")
        normalized_tone = expected_tone.lower()
        tokens = [token.strip() for token in normalized_tone.replace(",", " ").split() if token.strip()]
        copy_text = self._combined_copy(campaign_bundle).lower()
        matched_tokens = [token for token in tokens if token in copy_text]
        passed = len(matched_tokens) > 0 if tokens else True
        return {
            "passed": passed,
            "expected_tone": expected_tone,
            "matched_keywords": matched_tokens,
            "reason": "tone cues detected in generated copy" if passed else "expected tone cues missing from generated copy",
        }

    def _cta_clarity_check(self, campaign_bundle: dict) -> dict:
        cta_candidates = [
            campaign_bundle.get("hero", {}).get("cta", ""),
            campaign_bundle.get("email", ""),
            campaign_bundle.get("social", ""),
            campaign_bundle.get("page_draft", ""),
        ]
        action_verbs = ("get", "shop", "start", "try", "discover", "buy", "join", "see", "claim")
        matched_ctas = [
            candidate for candidate in cta_candidates if candidate and any(verb in candidate.lower() for verb in action_verbs)
        ]
        passed = bool(matched_ctas)
        return {
            "passed": passed,
            "matched_examples": matched_ctas[:3],
            "reason": "clear CTA language present" if passed else "no clear action-oriented CTA language found",
        }

    def _policy_safe_claims_check(self, campaign_bundle: dict) -> dict:
        copy_text = self._combined_copy(campaign_bundle).lower()
        banned_phrases = (
            "guaranteed",
            "cure",
            "risk-free",
            "instant results",
            "works for everyone",
            "scientifically proven",
            "clinically proven",
            "100% guaranteed",
        )
        violations = [phrase for phrase in banned_phrases if phrase in copy_text]
        passed = not violations
        return {
            "passed": passed,
            "violations": violations,
            "reason": "no unsafe claim patterns detected" if passed else "potentially unsafe claims detected",
        }

    def run(self, campaign_bundle: dict) -> dict:
        quality_checks = {
            "tone_alignment": self._tone_alignment_check(campaign_bundle),
            "cta_clarity": self._cta_clarity_check(campaign_bundle),
            "policy_safe_claims": self._policy_safe_claims_check(campaign_bundle),
        }
        checks = {
            "has_hero": "hero" in campaign_bundle,
            "has_ads": bool(campaign_bundle.get("ads")),
            "has_email": bool(campaign_bundle.get("email")),
            "has_cta": bool(campaign_bundle.get("hero", {}).get("cta")),
            "human_approval_required": True,
            "originality_risk": "low",
            "quality_checks": quality_checks,
        }
        checks["ready_for_draft"] = all(
            [
                checks["has_hero"],
                checks["has_ads"],
                checks["has_email"],
                checks["has_cta"],
                quality_checks["policy_safe_claims"]["passed"],
            ]
        )
        return checks
