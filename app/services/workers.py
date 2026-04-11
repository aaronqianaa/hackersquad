import json
from pathlib import Path

from app.services.model_provider import OpenAIProvider
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

    def run(self, brand_pattern: dict, product_context: dict) -> dict:
        prompt = (
            "Generate marketing copy using the following brand pattern and product context.\n"
            f"Brand pattern: {json.dumps(brand_pattern)}\n"
            f"Product context: {json.dumps(product_context)}\n"
            "Return concise copy for: headline, subheadline, product_description, 3 ads, email, social."
        )
        llm_text = self.provider.generate_text(prompt)
        headline = "Get Premium Results in Days, Not Months"
        subheadline = "Built for modern buyers who want visible outcomes with less effort."
        if llm_text:
            lines = [line.strip() for line in llm_text.splitlines() if line.strip()]
            if lines:
                headline = lines[0][:120]
            if len(lines) > 1:
                subheadline = lines[1][:160]
        return {
            "hero": {
                "headline": headline,
                "subheadline": subheadline,
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


class QAComplianceAgent:
    name = "QAComplianceAgent"

    def run(self, campaign_bundle: dict) -> dict:
        checks = {
            "has_hero": "hero" in campaign_bundle,
            "has_ads": bool(campaign_bundle.get("ads")),
            "has_email": bool(campaign_bundle.get("email")),
            "has_cta": bool(campaign_bundle.get("hero", {}).get("cta")),
            "human_approval_required": True,
            "originality_risk": "low",
        }
        checks["ready_for_draft"] = all([checks["has_hero"], checks["has_ads"], checks["has_email"], checks["has_cta"]])
        return checks
