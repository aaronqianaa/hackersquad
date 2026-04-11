from dataclasses import dataclass


@dataclass
class TrendSignals:
    recency: float
    engagement: float
    structural_quality: float
    niche_relevance: float
    novelty: float


WEIGHTS = {
    "recency": 0.20,
    "engagement": 0.25,
    "structural_quality": 0.20,
    "niche_relevance": 0.25,
    "novelty": 0.10,
}


def score_candidate(signals: TrendSignals) -> tuple[float, list[str]]:
    raw = (
        signals.recency * WEIGHTS["recency"]
        + signals.engagement * WEIGHTS["engagement"]
        + signals.structural_quality * WEIGHTS["structural_quality"]
        + signals.niche_relevance * WEIGHTS["niche_relevance"]
        + signals.novelty * WEIGHTS["novelty"]
    )
    score = round(max(0.0, min(1.0, raw)) * 100, 2)

    factors = {
        "recency": signals.recency,
        "engagement": signals.engagement,
        "structural_quality": signals.structural_quality,
        "niche_relevance": signals.niche_relevance,
        "novelty": signals.novelty,
    }
    top = sorted(factors.items(), key=lambda x: x[1], reverse=True)[:5]
    reasons = [f"Strong {name.replace('_', ' ')} signal ({value:.2f})" for name, value in top]
    return score, reasons
