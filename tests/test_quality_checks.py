from app.services.workers import QAComplianceAgent


def test_quality_checks_pass_for_expected_campaign_bundle() -> None:
    agent = QAComplianceAgent()
    campaign_bundle = {
        "hero": {
            "headline": "Get Premium Results in Days, Not Months",
            "subheadline": "Confident buyers choose a premium routine with less effort.",
            "cta": "Get Yours Today",
        },
        "product_description": "A premium product built for fast, reliable results without inflated promises.",
        "ads": [
            "Fast results. Premium quality. Try it today.",
            "The smarter way to upgrade your daily routine.",
            "Trusted feel, visible outcomes, low effort.",
        ],
        "email": "Subject: Discover a premium upgrade\nBody: See how this product helps you get better outcomes with less effort.",
        "social": "Discover the premium switch customers are making. See what fits your routine.",
        "page_draft": "Hero -> Benefits -> Proof -> Offer -> FAQ -> CTA",
        "creative_brief": {
            "visual_direction": "Clean product focus with premium cues.",
            "tone": "confident, benefit-led, direct response",
            "product_angles": ["time-saving", "premium feel"],
        },
    }

    result = agent.run(campaign_bundle)

    assert result["ready_for_draft"] is True
    assert result["quality_checks"]["tone_alignment"]["passed"] is True
    assert result["quality_checks"]["cta_clarity"]["passed"] is True
    assert result["quality_checks"]["policy_safe_claims"]["passed"] is True


def test_policy_safe_claims_check_blocks_unsafe_copy() -> None:
    agent = QAComplianceAgent()
    campaign_bundle = {
        "hero": {
            "headline": "Guaranteed cure for everyone",
            "subheadline": "Instant results with zero risk.",
            "cta": "Buy Now",
        },
        "product_description": "Clinically proven and risk-free for every customer.",
        "ads": ["Instant results guaranteed."],
        "email": "Subject: Guaranteed cure\nBody: Works for everyone.",
        "social": "100% guaranteed results.",
        "page_draft": "Hero -> CTA",
        "creative_brief": {
            "visual_direction": "Bold medical-style proof.",
            "tone": "confident, benefit-led, direct response",
            "product_angles": ["fast"],
        },
    }

    result = agent.run(campaign_bundle)

    assert result["quality_checks"]["policy_safe_claims"]["passed"] is False
    assert "guaranteed" in result["quality_checks"]["policy_safe_claims"]["violations"]
    assert result["ready_for_draft"] is False
