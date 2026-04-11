import json
from pathlib import Path

from app.services.model_provider import OpenAIProvider
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

        for seed in seeds:
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

    def run(self, source_url: str) -> dict:
        prompt = (
            "Analyze this landing page URL and infer its marketing structure. "
            "Return concise bullet-like insights about offer, CTA, proof, structure, and headline pattern. "
            f"URL: {source_url}"
        )
        llm_text = self.provider.generate_text(prompt)
        return {
            "reference_url": source_url,
            "offer": "Bundle-first with limited-time urgency" if not llm_text else llm_text[:180],
            "cta": "Single high-contrast buy CTA repeated across sections",
            "proof": "UGC testimonials above fold + trust badges",
            "structure": ["Hero", "Problem", "Benefits", "Proof", "Offer", "FAQ", "CTA"],
            "headline_pattern": "Outcome-first + timeframe + confidence cue",
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


class CampaignGeneratorAgent:
    name = "CampaignGeneratorAgent"

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

    def run(
        self,
        brand_pattern: dict,
        product_context: dict,
        artifact_instructions: dict[str, str] | None = None,
    ) -> dict:
        fallback = self._fallback_bundle(brand_pattern, product_context)
        instructions = artifact_instructions or {}
        prompts = {
            artifact_type: build_prompt(
                artifact_type,
                brand_pattern,
                product_context,
                instruction=instructions.get(artifact_type),
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
            "_prompt_versions": prompt_versions,
            "_artifact_instructions": instructions,
        }
        return bundle


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
                quality_checks["tone_alignment"]["passed"],
                quality_checks["cta_clarity"]["passed"],
                quality_checks["policy_safe_claims"]["passed"],
            ]
        )
        return checks
