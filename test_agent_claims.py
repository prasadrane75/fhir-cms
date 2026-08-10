from app.ai.agent import ReviewMode, _system_prompt_for_mode, _tools_for_mode
from app.ai.tools import (
    ALL_REVIEW_TOOLS,
    CLAIMS_ADJUDICATION_TOOLS,
    PRIOR_AUTH_TOOLS,
    check_claim_pricing_rules,
    check_duplicate_claims,
)


def test_review_mode_tool_sets():
    assert _tools_for_mode(ReviewMode.PRIOR_AUTH) == PRIOR_AUTH_TOOLS
    assert _tools_for_mode(ReviewMode.CLAIMS_ADJUDICATION) == CLAIMS_ADJUDICATION_TOOLS
    assert len(ALL_REVIEW_TOOLS) == len(PRIOR_AUTH_TOOLS) + len(CLAIMS_ADJUDICATION_TOOLS)


def test_review_mode_prompts_differ():
    prior_prompt = _system_prompt_for_mode(ReviewMode.PRIOR_AUTH)
    claims_prompt = _system_prompt_for_mode(ReviewMode.CLAIMS_ADJUDICATION)

    assert "prior authorization" in prior_prompt.lower()
    assert "claims adjudication" in claims_prompt.lower()
    assert prior_prompt != claims_prompt


def test_claim_tool_names():
    assert check_claim_pricing_rules.name == "check_claim_pricing_rules"
    assert check_duplicate_claims.name == "check_duplicate_claims"
