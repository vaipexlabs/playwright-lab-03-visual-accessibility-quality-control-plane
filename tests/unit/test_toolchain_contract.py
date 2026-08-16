"""Protect the reproducible quality-toolchain contract."""

import tomllib
from pathlib import Path

import vaipex_visual_accessibility

PROJECT_ROOT = Path(__file__).parents[2]
PYPROJECT = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())

EXPECTED_RUNTIME_PINS = {
    "axe-playwright-python": "0.1.8",
    "fastapi": "0.141.1",
    "jinja2": "3.1.6",
    "pillow": "12.3.0",
    "playwright": "1.62.0",
    "uvicorn": "0.52.3",
}

EXPECTED_TEST_PINS = {
    "httpx": "0.28.1",
    "pip-tools": "7.6.1",
    "pytest": "9.1.1",
    "pytest-html": "4.2.0",
    "pytest-playwright": "0.9.0",
    "ruff": "0.16.3",
}


def _pins(requirements: list[str]) -> dict[str, str]:
    return dict(requirement.split("==", maxsplit=1) for requirement in requirements)


def test_project_requires_only_python_312() -> None:
    assert PYPROJECT["project"]["requires-python"] == ">=3.12,<3.13"


def test_runtime_dependencies_are_exactly_pinned() -> None:
    assert _pins(PYPROJECT["project"]["dependencies"]) == EXPECTED_RUNTIME_PINS


def test_test_dependencies_are_exactly_pinned() -> None:
    assert _pins(PYPROJECT["project"]["optional-dependencies"]["test"]) == (
        EXPECTED_TEST_PINS
    )


def test_direct_dependencies_are_present_in_lock() -> None:
    lock = (PROJECT_ROOT / "requirements.lock").read_text().lower()
    all_pins = EXPECTED_RUNTIME_PINS | EXPECTED_TEST_PINS
    for name, pinned_version in all_pins.items():
        normalized_name = name.replace("_", "-")
        assert f"{normalized_name}=={pinned_version}" in lock


def test_package_version_matches_project_metadata() -> None:
    assert vaipex_visual_accessibility.__version__ == PYPROJECT["project"]["version"]
