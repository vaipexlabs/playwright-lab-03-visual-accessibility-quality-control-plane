"""Validate responsive visual comparison and evidence contracts."""

from pathlib import Path

from PIL import Image

from vaipex_visual_accessibility.visual_regression import compare_images


def _image(path: Path, color: str, size: tuple[int, int] = (20, 10)) -> None:
    Image.new("RGB", size, color=color).save(path)


def test_identical_images_pass_and_produce_diff_evidence(tmp_path: Path) -> None:
    expected = tmp_path / "expected.png"
    actual = tmp_path / "actual.png"
    diff = tmp_path / "diff.png"
    _image(expected, "#6842e8")
    _image(actual, "#6842e8")

    result = compare_images(
        expected_path=expected,
        actual_path=actual,
        diff_path=diff,
        channel_delta_threshold=8,
        max_changed_pixel_ratio=0.001,
    )

    assert result["status"] == "passed"
    assert result["changed_pixels"] == 0
    assert result["changed_pixel_ratio"] == 0
    assert diff.is_file()


def test_material_pixel_drift_fails_and_is_highlighted(tmp_path: Path) -> None:
    expected = tmp_path / "expected.png"
    actual = tmp_path / "actual.png"
    diff = tmp_path / "diff.png"
    _image(expected, "#ffffff")
    _image(actual, "#ffffff")
    with Image.open(actual) as source:
        changed = source.copy()
    for x_position in range(5):
        for y_position in range(5):
            changed.putpixel((x_position, y_position), (180, 0, 0))
    changed.save(actual)

    result = compare_images(
        expected_path=expected,
        actual_path=actual,
        diff_path=diff,
        channel_delta_threshold=8,
        max_changed_pixel_ratio=0.001,
    )

    assert result["status"] == "failed"
    assert result["reason"] == "pixel-drift"
    assert result["changed_pixels"] == 25
    assert result["changed_pixel_ratio"] == 0.125
    with Image.open(diff) as diff_image:
        assert diff_image.getpixel((0, 0)) == (255, 45, 85)


def test_dimension_change_fails_before_pixel_comparison(tmp_path: Path) -> None:
    expected = tmp_path / "expected.png"
    actual = tmp_path / "actual.png"
    diff = tmp_path / "diff.png"
    _image(expected, "#ffffff", size=(20, 10))
    _image(actual, "#ffffff", size=(21, 10))

    result = compare_images(
        expected_path=expected,
        actual_path=actual,
        diff_path=diff,
        channel_delta_threshold=8,
        max_changed_pixel_ratio=0.001,
    )

    assert result["status"] == "failed"
    assert result["reason"] == "dimension-mismatch"
    assert result["expected_dimensions"] == [20, 10]
    assert result["actual_dimensions"] == [21, 10]
    assert diff.is_file()
