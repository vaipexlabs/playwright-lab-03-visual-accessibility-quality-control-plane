"""Compare responsive interface captures with approved visual baselines."""

import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageEnhance, ImageOps

from vaipex_visual_accessibility.baselines import (
    BASELINE_ROOT,
    POLICY_PATH,
    BaselineIntegrityError,
    _digest,
    _load_json,
    _safe_relative_image_path,
    _write_json,
    propose_baselines,
    verify_approved_baselines,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACTUAL_ROOT = PROJECT_ROOT / "artifacts" / "visual" / "actual"
DIFF_ROOT = PROJECT_ROOT / "artifacts" / "visual" / "diffs"
REPORT_PATH = PROJECT_ROOT / "reports" / "visual" / "results.json"


def compare_images(
    *,
    expected_path: Path,
    actual_path: Path,
    diff_path: Path,
    channel_delta_threshold: int,
    max_changed_pixel_ratio: float,
) -> dict[str, Any]:
    """Compare two images and write reviewable difference evidence."""

    with Image.open(expected_path) as expected_source:
        expected = expected_source.convert("RGB")
    with Image.open(actual_path) as actual_source:
        actual = actual_source.convert("RGB")

    expected_dimensions = expected.size
    actual_dimensions = actual.size
    if expected_dimensions != actual_dimensions:
        separator_width = 8
        evidence_width = expected.width + separator_width + actual.width
        evidence_height = max(expected.height, actual.height)
        diff_evidence = Image.new("RGB", (evidence_width, evidence_height), "#ff2d55")
        diff_evidence.paste(expected, (0, 0))
        diff_evidence.paste(actual, (expected.width + separator_width, 0))
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_evidence.save(diff_path)
        return {
            "actual_dimensions": list(actual_dimensions),
            "changed_pixel_ratio": 1.0,
            "changed_pixels": None,
            "expected_dimensions": list(expected_dimensions),
            "reason": "dimension-mismatch",
            "status": "failed",
            "total_pixels": None,
        }

    raw_difference = ImageChops.difference(expected, actual)
    red, green, blue = raw_difference.split()
    maximum_channel_delta = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    changed_mask = maximum_channel_delta.point(
        lambda value: 255 if value > channel_delta_threshold else 0
    )
    changed_pixels = changed_mask.histogram()[255]
    total_pixels = expected.width * expected.height
    changed_pixel_ratio = changed_pixels / total_pixels

    muted_expected = ImageEnhance.Brightness(
        ImageOps.grayscale(expected).convert("RGB")
    ).enhance(0.55)
    regression_color = Image.new("RGB", expected.size, "#ff2d55")
    diff_evidence = Image.composite(regression_color, muted_expected, changed_mask)
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_evidence.save(diff_path)

    status = "passed" if changed_pixel_ratio <= max_changed_pixel_ratio else "failed"
    return {
        "actual_dimensions": list(actual_dimensions),
        "changed_pixel_ratio": round(changed_pixel_ratio, 8),
        "changed_pixels": changed_pixels,
        "expected_dimensions": list(expected_dimensions),
        "reason": "within-policy" if status == "passed" else "pixel-drift",
        "status": status,
        "total_pixels": total_pixels,
    }


def run_visual_regression(
    *,
    policy_path: Path = POLICY_PATH,
    baseline_root: Path = BASELINE_ROOT,
    actual_root: Path = ACTUAL_ROOT,
    diff_root: Path = DIFF_ROOT,
    report_path: Path = REPORT_PATH,
    capture: bool = True,
) -> dict[str, Any]:
    """Capture responsive states and evaluate them against approval policy."""

    verify_approved_baselines(baseline_root=baseline_root)
    policy = _load_json(policy_path)
    baseline_manifest = _load_json(baseline_root / "manifest.json")
    if baseline_manifest.get("policy_sha256") != _digest(policy_path):
        raise BaselineIntegrityError(
            "Visual policy changed after baseline approval; propose and accept "
            "a new set."
        )

    if capture:
        actual_manifest = propose_baselines(
            policy_path=policy_path,
            candidate_root=actual_root,
        )
    else:
        actual_manifest = _load_json(actual_root / "manifest.json")

    if actual_manifest.get("policy_sha256") != baseline_manifest["policy_sha256"]:
        raise BaselineIntegrityError(
            "Actual captures were produced by a different policy."
        )

    expected_keys = set(baseline_manifest["items"])
    actual_keys = set(actual_manifest["items"])
    if expected_keys != actual_keys:
        missing = sorted(expected_keys - actual_keys)
        unexpected = sorted(actual_keys - expected_keys)
        raise BaselineIntegrityError(
            "Capture set differs from approved set; "
            f"missing={missing}, unexpected={unexpected}."
        )

    comparison_policy = policy["comparison"]
    results: dict[str, dict[str, Any]] = {}
    for item_key in sorted(expected_keys):
        baseline_item = baseline_manifest["items"][item_key]
        actual_item = actual_manifest["items"][item_key]
        relative_path = _safe_relative_image_path(baseline_item["file"])
        if actual_item["file"] != baseline_item["file"]:
            raise BaselineIntegrityError(f"Capture path changed for {item_key}.")
        for contract_field in ("browser_version", "full_page", "renderer", "route"):
            if actual_item.get(contract_field) != baseline_item.get(contract_field):
                raise BaselineIntegrityError(
                    f"Capture contract field {contract_field} changed for {item_key}."
                )

        diff_relative_path = relative_path.with_name(f"{relative_path.stem}-diff.png")
        result = compare_images(
            expected_path=baseline_root / relative_path,
            actual_path=actual_root / relative_path,
            diff_path=diff_root / diff_relative_path,
            channel_delta_threshold=comparison_policy["channel_delta_threshold"],
            max_changed_pixel_ratio=comparison_policy["max_changed_pixel_ratio"],
        )
        result.update(
            {
                "actual": relative_path.as_posix(),
                "diff": diff_relative_path.as_posix(),
                "expected": relative_path.as_posix(),
                "profile_state": item_key,
            }
        )
        results[item_key] = result

    failed = sum(result["status"] == "failed" for result in results.values())
    report = {
        "comparison_policy": comparison_policy,
        "failed": failed,
        "passed": len(results) - failed,
        "render_contract": baseline_manifest["render_contract"],
        "results": results,
        "schema_version": 1,
        "status": "failed" if failed else "passed",
    }
    _write_json(report_path, report)
    return report


def main() -> int:
    """Run the responsive visual-regression contract."""

    try:
        report = run_visual_regression()
    except BaselineIntegrityError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    for item_key, result in report["results"].items():
        ratio = result["changed_pixel_ratio"]
        print(f"{result['status'].upper():6} {item_key}: changed_pixel_ratio={ratio}")
    print(
        f"Visual quality gate {report['status'].upper()}: "
        f"{report['passed']} passed, {report['failed']} failed."
    )
    print(f"Machine-readable results: {REPORT_PATH}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
