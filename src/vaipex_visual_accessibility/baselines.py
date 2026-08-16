"""Govern candidate generation, approval, and integrity of visual baselines."""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = PROJECT_ROOT / "policies" / "visual-baselines.json"
CANDIDATE_ROOT = PROJECT_ROOT / "artifacts" / "visual" / "candidates"
BASELINE_ROOT = PROJECT_ROOT / "tests" / "visual" / "baselines"
APPROVAL_ENVIRONMENT_VARIABLE = "VAIPEX_APPROVE_BASELINES"


class BaselineApprovalRequired(RuntimeError):
    """Raised when a caller attempts promotion without explicit approval."""


class BaselineIntegrityError(RuntimeError):
    """Raised when baseline content no longer matches its approval manifest."""


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n")


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _image_dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def _safe_relative_image_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.suffix.lower() != ".png":
        raise BaselineIntegrityError(f"Unsafe baseline path: {value}")
    return path


def _open_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_until_ready(base_url: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/health/ready", timeout=0.5) as response:  # noqa: S310
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(0.1)
    raise RuntimeError(f"Reference application did not become ready at {base_url}.")


@contextmanager
def _reference_application() -> Iterator[str]:
    port = _open_port()
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "vaipex_visual_accessibility.app:app",
            "--app-dir",
            str(PROJECT_ROOT / "src"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_ready(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def propose_baselines(
    *,
    policy_path: Path = POLICY_PATH,
    candidate_root: Path = CANDIDATE_ROOT,
) -> dict[str, Any]:
    """Capture review candidates without writing to the approval boundary."""

    policy = _load_json(policy_path)
    items: dict[str, dict[str, Any]] = {}

    with _reference_application() as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            browser_version = browser.version
            for profile_name, profile in policy["profiles"].items():
                context = browser.new_context(
                    viewport={"width": profile["width"], "height": profile["height"]},
                    device_scale_factor=1,
                    color_scheme="light",
                    locale="en-US",
                    reduced_motion="reduce",
                    timezone_id="UTC",
                )
                try:
                    for state_name, route in policy["states"].items():
                        page = context.new_page()
                        page.goto(f"{base_url}{route}", wait_until="networkidle")
                        page.evaluate("document.fonts.ready")
                        page.add_style_tag(
                            content="*,*::before,*::after{animation:none!important;transition:none!important}"
                        )
                        relative_path = Path(profile_name) / f"{state_name}.png"
                        candidate_path = candidate_root / relative_path
                        candidate_path.parent.mkdir(parents=True, exist_ok=True)
                        page.screenshot(
                            path=candidate_path,
                            full_page=True,
                            animations="disabled",
                            caret="hide",
                            scale="css",
                        )
                        width, height = _image_dimensions(candidate_path)
                        item_key = f"{profile_name}/{state_name}"
                        items[item_key] = {
                            "browser_version": browser_version,
                            "file": relative_path.as_posix(),
                            "height": height,
                            "renderer": policy["renderer"],
                            "route": route,
                            "sha256": _digest(candidate_path),
                            "width": width,
                        }
                        page.close()
                finally:
                    context.close()
        finally:
            browser.close()

    manifest = {
        "items": items,
        "policy_sha256": _digest(policy_path),
        "render_contract": policy["render_contract"],
        "schema_version": policy["schema_version"],
    }
    _write_json(candidate_root / "manifest.json", manifest)
    return manifest


def accept_candidate_set(
    *,
    candidate_root: Path = CANDIDATE_ROOT,
    baseline_root: Path = BASELINE_ROOT,
) -> dict[str, Any]:
    """Promote an intact candidate set only after explicit human approval."""

    if os.environ.get(APPROVAL_ENVIRONMENT_VARIABLE) != "1":
        raise BaselineApprovalRequired(
            f"Set {APPROVAL_ENVIRONMENT_VARIABLE}=1 only after reviewing "
            "every candidate."
        )

    candidate_manifest_path = candidate_root / "manifest.json"
    if not candidate_manifest_path.is_file():
        raise BaselineIntegrityError(
            "No candidate manifest exists; propose baselines first."
        )

    manifest = _load_json(candidate_manifest_path)
    for item in manifest["items"].values():
        relative_path = _safe_relative_image_path(item["file"])
        candidate_path = candidate_root / relative_path
        if not candidate_path.is_file() or _digest(candidate_path) != item["sha256"]:
            raise BaselineIntegrityError(
                f"Candidate is missing or changed: {item['file']}"
            )
        if _image_dimensions(candidate_path) != (item["width"], item["height"]):
            raise BaselineIntegrityError(
                f"Candidate dimensions changed: {item['file']}"
            )

        baseline_path = baseline_root / relative_path
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_bytes(candidate_path.read_bytes())

    _write_json(baseline_root / "manifest.json", manifest)
    return manifest


def verify_approved_baselines(*, baseline_root: Path = BASELINE_ROOT) -> int:
    """Verify approved images against their review manifest."""

    manifest_path = baseline_root / "manifest.json"
    if not manifest_path.is_file():
        raise BaselineIntegrityError("Approved baseline manifest is missing.")

    manifest = _load_json(manifest_path)
    for item in manifest["items"].values():
        baseline_path = baseline_root / _safe_relative_image_path(item["file"])
        if not baseline_path.is_file():
            raise BaselineIntegrityError(
                f"Approved baseline is missing: {item['file']}"
            )
        if _digest(baseline_path) != item["sha256"]:
            raise BaselineIntegrityError(f"Approved baseline changed: {item['file']}")
        if _image_dimensions(baseline_path) != (item["width"], item["height"]):
            raise BaselineIntegrityError(
                f"Approved baseline dimensions changed: {item['file']}"
            )
    return len(manifest["items"])


def main() -> int:
    """Run the supported baseline-lifecycle command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("propose", "accept", "verify"))
    args = parser.parse_args()

    try:
        if args.operation == "propose":
            manifest = propose_baselines()
            print(
                f"Proposed {len(manifest['items'])} baseline candidate(s) "
                f"in {CANDIDATE_ROOT}."
            )
            print("Approved baselines were not changed.")
        elif args.operation == "accept":
            manifest = accept_candidate_set()
            print(
                f"Accepted {len(manifest['items'])} reviewed baseline(s) "
                f"into {BASELINE_ROOT}."
            )
        else:
            count = verify_approved_baselines()
            print(f"Verified {count} approved baseline(s) against the review manifest.")
    except (BaselineApprovalRequired, BaselineIntegrityError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
