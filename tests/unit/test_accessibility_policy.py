from datetime import date

import pytest

from vaipex_visual_accessibility.accessibility import (
    AccessibilityPolicyError,
    evaluate_violations,
    validate_exceptions,
)


def _violation(impact: str = "serious") -> dict:
    return {
        "id": "button-name",
        "impact": impact,
        "description": "Ensure buttons have discernible text",
        "help": "Buttons must have discernible text",
        "helpUrl": "https://dequeuniversity.com/rules/axe/button-name",
        "nodes": [
            {
                "target": ["#save"],
                "html": '<button id="save"></button>',
                "failureSummary": "Fix the button name",
            }
        ],
    }


def test_serious_finding_blocks_without_exception() -> None:
    result = evaluate_violations(
        violations=[_violation()],
        profile_state="desktop/ready",
        blocking_impacts={"critical", "serious"},
        advisory_impacts={"moderate", "minor"},
        exceptions=[],
    )

    assert result["status"] == "failed"
    assert result["blocking"] == 1


def test_moderate_finding_is_advisory() -> None:
    result = evaluate_violations(
        violations=[_violation("moderate")],
        profile_state="desktop/ready",
        blocking_impacts={"critical", "serious"},
        advisory_impacts={"moderate", "minor"},
        exceptions=[],
    )

    assert result["status"] == "passed"
    assert result["advisory"] == 1


def test_narrow_active_exception_preserves_evidence_without_blocking() -> None:
    exception = {
        "rule_id": "button-name",
        "selector": "#save",
        "profile_state": "desktop/ready",
        "owner": "Experience Platform",
        "reason": "Vendor fix scheduled",
        "expires_on": "2026-09-01",
    }
    validate_exceptions(
        {"schema_version": 1, "exceptions": [exception]},
        today=date(2026, 8, 16),
    )
    result = evaluate_violations(
        violations=[_violation()],
        profile_state="desktop/ready",
        blocking_impacts={"critical", "serious"},
        advisory_impacts={"moderate", "minor"},
        exceptions=[exception],
    )

    assert result["status"] == "passed"
    assert result["excepted"] == 1


@pytest.mark.parametrize("selector", ["*", "html", "body"])
def test_broad_exception_is_rejected(selector: str) -> None:
    with pytest.raises(AccessibilityPolicyError, match="broad selector"):
        validate_exceptions(
            {
                "schema_version": 1,
                "exceptions": [
                    {
                        "rule_id": "button-name",
                        "selector": selector,
                        "profile_state": "desktop/ready",
                        "owner": "Experience Platform",
                        "reason": "Too broad",
                        "expires_on": "2026-09-01",
                    }
                ],
            },
            today=date(2026, 8, 16),
        )


def test_expired_exception_is_rejected() -> None:
    with pytest.raises(AccessibilityPolicyError, match="expired"):
        validate_exceptions(
            {
                "schema_version": 1,
                "exceptions": [
                    {
                        "rule_id": "button-name",
                        "selector": "#save",
                        "profile_state": "desktop/ready",
                        "owner": "Experience Platform",
                        "reason": "Expired vendor issue",
                        "expires_on": "2026-08-15",
                    }
                ],
            },
            today=date(2026, 8, 16),
        )
