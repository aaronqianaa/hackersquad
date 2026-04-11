from app.services.scoring import TrendSignals, score_candidate


def test_score_candidate_returns_percent_and_reasons() -> None:
    score, reasons = score_candidate(TrendSignals(0.8, 0.9, 0.7, 0.95, 0.6))
    assert 0 <= score <= 100
    assert len(reasons) >= 3
    assert any("niche relevance" in r for r in reasons)
