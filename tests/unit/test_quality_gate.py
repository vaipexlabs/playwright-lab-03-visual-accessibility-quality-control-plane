from vaipex_visual_accessibility.quality_gate import combine_decisions


def _visual(status: str = "passed") -> dict:
    return {
        "status": status,
        "passed": 8 if status == "passed" else 7,
        "failed": 0 if status == "passed" else 1,
    }


def _accessibility(status: str = "passed") -> dict:
    return {
        "status": status,
        "totals": {
            "blocking": 0 if status == "passed" else 1,
            "advisory": 2,
            "excepted": 0,
        },
    }


def test_combined_gate_promotes_only_when_both_dimensions_pass() -> None:
    report = combine_decisions(
        visual_report=_visual(), accessibility_report=_accessibility()
    )

    assert report["status"] == "passed"
    assert report["decision"] == "promote"


def test_combined_gate_rejects_any_failed_dimension() -> None:
    report = combine_decisions(
        visual_report=_visual("failed"), accessibility_report=_accessibility()
    )

    assert report["status"] == "failed"
    assert report["decision"] == "reject"
    assert report["failed_dimensions"] == ["visual"]
