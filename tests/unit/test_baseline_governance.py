"""Protect the reviewed visual-baseline lifecycle."""

import json
from hashlib import sha256
from pathlib import Path

import pytest
from PIL import Image

from vaipex_visual_accessibility.baselines import (
    APPROVAL_ENVIRONMENT_VARIABLE,
    BaselineApprovalRequired,
    BaselineIntegrityError,
    accept_candidate_set,
    verify_approved_baselines,
)


def _candidate_set(root: Path) -> bytes:
    image_path = root / "desktop" / "ready.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (16, 12), color="#6842e8").save(image_path)
    image_bytes = image_path.read_bytes()
    manifest = {
        "items": {
            "desktop/ready": {
                "browser_version": "151.0",
                "file": "desktop/ready.png",
                "height": 12,
                "renderer": "chromium",
                "route": "/?state=ready",
                "sha256": sha256(image_bytes).hexdigest(),
                "width": 16,
            }
        },
        "policy_sha256": "fixture-policy-digest",
        "render_contract": "vaipex-v1",
        "schema_version": 1,
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    return image_bytes


def test_acceptance_requires_explicit_review_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate_root = tmp_path / "candidates"
    _candidate_set(candidate_root)
    monkeypatch.delenv(APPROVAL_ENVIRONMENT_VARIABLE, raising=False)

    with pytest.raises(BaselineApprovalRequired, match=APPROVAL_ENVIRONMENT_VARIABLE):
        accept_candidate_set(
            candidate_root=candidate_root,
            baseline_root=tmp_path / "baselines",
        )


def test_reviewed_candidate_is_promoted_byte_for_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate_root = tmp_path / "candidates"
    expected_bytes = _candidate_set(candidate_root)
    baseline_root = tmp_path / "baselines"
    monkeypatch.setenv(APPROVAL_ENVIRONMENT_VARIABLE, "1")

    accept_candidate_set(candidate_root=candidate_root, baseline_root=baseline_root)

    assert (baseline_root / "desktop" / "ready.png").read_bytes() == expected_bytes
    assert verify_approved_baselines(baseline_root=baseline_root) == 1


def test_integrity_check_detects_unreviewed_baseline_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate_root = tmp_path / "candidates"
    _candidate_set(candidate_root)
    baseline_root = tmp_path / "baselines"
    monkeypatch.setenv(APPROVAL_ENVIRONMENT_VARIABLE, "1")
    accept_candidate_set(candidate_root=candidate_root, baseline_root=baseline_root)

    Image.new("RGB", (16, 12), color="#b42318").save(
        baseline_root / "desktop" / "ready.png"
    )

    with pytest.raises(BaselineIntegrityError, match="changed"):
        verify_approved_baselines(baseline_root=baseline_root)


def test_acceptance_rejects_a_path_outside_the_baseline_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate_root = tmp_path / "candidates"
    _candidate_set(candidate_root)
    manifest_path = candidate_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["items"]["desktop/ready"]["file"] = "../outside.png"
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setenv(APPROVAL_ENVIRONMENT_VARIABLE, "1")

    with pytest.raises(BaselineIntegrityError, match="Unsafe baseline path"):
        accept_candidate_set(
            candidate_root=candidate_root,
            baseline_root=tmp_path / "baselines",
        )


def test_visual_policy_has_an_explicit_reference_contract() -> None:
    project_root = Path(__file__).parents[2]
    policy = json.loads(
        (project_root / "policies" / "visual-baselines.json").read_text()
    )

    assert policy["renderer"] == "chromium"
    assert policy["render_contract"] == "vaipex-v1"
    assert policy["profiles"]["desktop"] == {"width": 1440, "height": 1000}
    assert policy["profiles"]["mobile"] == {"width": 390, "height": 844}
    assert policy["schema_version"] == 2
    assert policy["states"] == {
        "degraded": {"route": "/?state=degraded", "full_page": True},
        "empty": {"route": "/?state=empty", "full_page": True},
        "ready": {"route": "/?state=ready", "full_page": True},
        "review-dialog": {"route": "/?dialog=true", "full_page": False},
    }
    assert policy["comparison"] == {
        "channel_delta_threshold": 8,
        "max_changed_pixel_ratio": 0.001,
    }
