import json
from pathlib import Path

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

    def run(self, source_url: str) -> dict:
        return {
            "reference_url": source_url,
            "offer": "Bundle-first with limited-time urgency",
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

    def run(self, file_path: str) -> dict:
        suffix = Path(file_path).suffix.lower()
        format_name = suffix.replace(".", "") if suffix else "unknown"
        return {
            "image_path": file_path,
            "detected_format": format_name,
            "product_guess": "consumer product",
            "angles": ["time-saving", "premium feel", "social proof readiness"],
        }


class CampaignGeneratorAgent:
    name = "CampaignGeneratorAgent"

    def run(self, brand_pattern: dict, product_context: dict) -> dict:
        headline = "Get Premium Results in Days, Not Months"
        subheadline = "Built for modern buyers who want visible outcomes with less effort."
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
