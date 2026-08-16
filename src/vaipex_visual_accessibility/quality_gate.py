"""Publish one delivery decision from visual and accessibility evidence."""

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vaipex_visual_accessibility.accessibility import run_accessibility_gate
from vaipex_visual_accessibility.baselines import PROJECT_ROOT, _write_json
from vaipex_visual_accessibility.visual_regression import run_visual_regression

REPORT_PATH = PROJECT_ROOT / "reports" / "quality-gate.json"


def combine_decisions(
    *, visual_report: dict[str, Any], accessibility_report: dict[str, Any]
) -> dict[str, Any]:
    """Combine two independently reviewable signals into one stable contract."""

    dimensions = {
        "accessibility": {
            "evidence": "reports/accessibility/results.json",
            "status": accessibility_report["status"],
            "summary": {
                "advisory": accessibility_report["totals"]["advisory"],
                "blocking": accessibility_report["totals"]["blocking"],
                "excepted": accessibility_report["totals"]["excepted"],
            },
        },
        "visual": {
            "evidence": "reports/visual/results.json",
            "status": visual_report["status"],
            "summary": {
                "failed": visual_report["failed"],
                "passed": visual_report["passed"],
            },
        },
    }
    failed_dimensions = [
        name
        for name, dimension in dimensions.items()
        if dimension["status"] != "passed"
    ]
    return {
        "decision": "reject" if failed_dimensions else "promote",
        "dimensions": dimensions,
        "failed_dimensions": failed_dimensions,
        "schema_version": 1,
        "status": "failed" if failed_dimensions else "passed",
    }


def run_quality_gate(
    *,
    visual_runner: Callable[[], dict[str, Any]] = run_visual_regression,
    accessibility_runner: Callable[[], dict[str, Any]] = run_accessibility_gate,
    report_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    """Run both quality dimensions and persist the combined decision."""

    visual_report = visual_runner()
    accessibility_report = accessibility_runner()
    report = combine_decisions(
        visual_report=visual_report,
        accessibility_report=accessibility_report,
    )
    _write_json(report_path, report)
    return report


def main() -> int:
    """Run and print the combined delivery decision."""

    try:
        report = run_quality_gate()
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    for name, dimension in report["dimensions"].items():
        print(f"{name.capitalize():14} {dimension['status'].upper()}")
    print(f"Combined quality decision: {report['decision'].upper()}")
    print(f"Machine-readable decision: {REPORT_PATH}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
