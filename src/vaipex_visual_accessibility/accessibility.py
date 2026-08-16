"""Evaluate rendered states against the governed accessibility policy."""

import sys
from datetime import date
from pathlib import Path
from typing import Any

from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import sync_playwright

from vaipex_visual_accessibility.baselines import (
    PROJECT_ROOT,
    _load_json,
    _reference_application,
    _write_json,
)

POLICY_PATH = PROJECT_ROOT / "policies" / "accessibility.json"
EXCEPTIONS_PATH = PROJECT_ROOT / "policies" / "accessibility-exceptions.json"
REPORT_ROOT = PROJECT_ROOT / "reports" / "accessibility"
REPORT_PATH = REPORT_ROOT / "results.json"
VALID_IMPACTS = {"critical", "serious", "moderate", "minor", None}


class AccessibilityPolicyError(RuntimeError):
    """Raised when accessibility policy or exception data is invalid."""


def validate_exceptions(payload: dict[str, Any], *, today: date | None = None) -> None:
    """Reject broad, incomplete, duplicate, or expired policy exceptions."""

    if payload.get("schema_version") != 1 or not isinstance(
        payload.get("exceptions"), list
    ):
        raise AccessibilityPolicyError(
            "Accessibility exceptions use an invalid schema."
        )

    current_date = today or date.today()
    identities: set[tuple[str, str, str]] = set()
    required = {"rule_id", "selector", "profile_state", "owner", "reason", "expires_on"}
    for index, exception in enumerate(payload["exceptions"], start=1):
        if not isinstance(exception, dict) or not required.issubset(exception):
            raise AccessibilityPolicyError(
                f"Exception {index} must define {', '.join(sorted(required))}."
            )
        if any(
            not isinstance(exception[key], str) or not exception[key].strip()
            for key in required
        ):
            raise AccessibilityPolicyError(
                f"Exception {index} contains an empty field."
            )
        if exception["selector"] in {"*", "html", "body"}:
            raise AccessibilityPolicyError(
                f"Exception {index} uses an unsafe broad selector."
            )
        if "/" not in exception["profile_state"]:
            raise AccessibilityPolicyError(
                f"Exception {index} must target one profile/state pair."
            )
        try:
            expiry = date.fromisoformat(exception["expires_on"])
        except ValueError as error:
            raise AccessibilityPolicyError(
                f"Exception {index} has an invalid expires_on date."
            ) from error
        if expiry < current_date:
            raise AccessibilityPolicyError(f"Exception {index} expired on {expiry}.")
        identity = (
            exception["rule_id"],
            exception["selector"],
            exception["profile_state"],
        )
        if identity in identities:
            raise AccessibilityPolicyError(f"Exception {index} is duplicated.")
        identities.add(identity)


def _is_excepted(
    *,
    rule_id: str,
    targets: list[list[str] | str],
    profile_state: str,
    exceptions: list[dict[str, str]],
) -> bool:
    selectors = {
        target if isinstance(target, str) else " ".join(target) for target in targets
    }
    return any(
        exception["rule_id"] == rule_id
        and exception["profile_state"] == profile_state
        and exception["selector"] in selectors
        for exception in exceptions
    )


def evaluate_violations(
    *,
    violations: list[dict[str, Any]],
    profile_state: str,
    blocking_impacts: set[str],
    advisory_impacts: set[str],
    exceptions: list[dict[str, str]],
) -> dict[str, Any]:
    """Classify rule-node findings into blocking, advisory, and excepted evidence."""

    findings: list[dict[str, Any]] = []
    for violation in violations:
        impact = violation.get("impact")
        if impact not in VALID_IMPACTS:
            raise AccessibilityPolicyError(
                f"Rule {violation.get('id')} returned unknown impact {impact}."
            )
        for node in violation.get("nodes", []):
            targets = node.get("target", [])
            excepted = _is_excepted(
                rule_id=violation["id"],
                targets=targets,
                profile_state=profile_state,
                exceptions=exceptions,
            )
            classification = (
                "excepted"
                if excepted
                else ("blocking" if impact in blocking_impacts else "advisory")
            )
            findings.append(
                {
                    "classification": classification,
                    "description": violation.get("description"),
                    "help": violation.get("help"),
                    "help_url": violation.get("helpUrl"),
                    "html": node.get("html"),
                    "impact": impact,
                    "rule_id": violation["id"],
                    "summary": node.get("failureSummary"),
                    "target": targets,
                }
            )

    counts = {
        name: sum(finding["classification"] == name for finding in findings)
        for name in ("blocking", "advisory", "excepted")
    }
    return {
        **counts,
        "findings": findings,
        "status": "failed" if counts["blocking"] else "passed",
    }


def run_accessibility_gate(
    *,
    policy_path: Path = POLICY_PATH,
    exceptions_path: Path = EXCEPTIONS_PATH,
    report_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    """Scan every declared profile/state and publish decision evidence."""

    policy = _load_json(policy_path)
    exceptions_payload = _load_json(exceptions_path)
    validate_exceptions(exceptions_payload)
    blocking_impacts = set(policy["blocking_impacts"])
    advisory_impacts = set(policy["advisory_impacts"])
    if blocking_impacts & advisory_impacts:
        raise AccessibilityPolicyError("Blocking and advisory impacts overlap.")

    results: dict[str, dict[str, Any]] = {}
    with _reference_application() as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for profile_name, profile in policy["profiles"].items():
                context = browser.new_context(
                    viewport={"width": profile["width"], "height": profile["height"]},
                    color_scheme="light",
                    locale="en-US",
                    reduced_motion="reduce",
                    timezone_id="UTC",
                )
                try:
                    for state_name, route in policy["states"].items():
                        profile_state = f"{profile_name}/{state_name}"
                        page = context.new_page()
                        page.goto(f"{base_url}{route}", wait_until="networkidle")
                        raw_results = (
                            Axe()
                            .run(
                                page,
                                options={
                                    "resultTypes": ["violations"],
                                    "runOnly": {
                                        "type": "tag",
                                        "values": policy["tags"],
                                    },
                                },
                            )
                            .response
                        )
                        result = evaluate_violations(
                            violations=raw_results["violations"],
                            profile_state=profile_state,
                            blocking_impacts=blocking_impacts,
                            advisory_impacts=advisory_impacts,
                            exceptions=exceptions_payload["exceptions"],
                        )
                        result.update({"profile_state": profile_state, "route": route})
                        results[profile_state] = result
                        state_path = (
                            REPORT_ROOT / "states" / f"{profile_name}-{state_name}.json"
                        )
                        _write_json(state_path, raw_results)
                        page.close()
                finally:
                    context.close()
        finally:
            browser.close()

    totals = {
        key: sum(result[key] for result in results.values())
        for key in ("blocking", "advisory", "excepted")
    }
    failed_states = sum(result["status"] == "failed" for result in results.values())
    report = {
        "automated_scan_notice": (
            "Automated checks complement, but do not replace, manual keyboard, "
            "screen-reader, content, and disability-led usability review."
        ),
        "failed_states": failed_states,
        "policy": {
            "advisory_impacts": sorted(advisory_impacts),
            "blocking_impacts": sorted(blocking_impacts),
            "standard": policy["standard"],
            "tags": policy["tags"],
        },
        "results": results,
        "schema_version": 1,
        "status": "failed" if failed_states else "passed",
        "totals": totals,
    }
    _write_json(report_path, report)
    return report


def main() -> int:
    """Run the accessibility quality gate."""

    try:
        report = run_accessibility_gate()
    except AccessibilityPolicyError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    for profile_state, result in report["results"].items():
        print(
            f"{result['status'].upper():6} {profile_state}: "
            f"blocking={result['blocking']}, advisory={result['advisory']}, "
            f"excepted={result['excepted']}"
        )
    print(
        f"Accessibility quality gate {report['status'].upper()}: "
        f"{report['failed_states']} failed state(s)."
    )
    print(f"Machine-readable results: {REPORT_PATH}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
