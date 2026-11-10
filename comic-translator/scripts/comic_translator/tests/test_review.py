"""Review images: the page in stretches never cutting a box, each box drawn with its id."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from comic_translator.notes import Box, Entry
from comic_translator.review import RULER, cut_points, overview, review_images


def test_the_page_is_cut_at_the_same_places_whatever_the_boxes() -> None:
    assert cut_points(2500) == [0, 1000, 2000, 2500]


def test_a_box_across_a_cut_is_drawn_in_both_stretches(tmp_path: Path) -> None:
    page = Image.new("RGB", (300, 2000), "white")

    paths = review_images(page, [Entry(7, Box(20, 950, 200, 1050), "", "")], tmp_path / "001")

    for path, y in zip(paths, (RULER + 970, RULER + 150 + 30), strict=True):
        with Image.open(path) as sheet:
            red, green, _ = sheet.convert("RGB").getpixel((RULER + 20, y))
            assert red > 180 and green < 90


def test_each_stretch_is_saved_ruled_with_its_boxes_drawn(tmp_path: Path) -> None:
    page = Image.new("RGB", (300, 1500), "white")
    entries = [Entry(1, Box(20, 100, 120, 160), "", ""), Entry(2, Box(20, 1200, 120, 1260), "", "")]

    paths = review_images(page, entries, tmp_path / "review" / "001")

    assert [p.name for p in paths] == ["001-1.jpg", "001-2.jpg"]
    with Image.open(paths[0]) as first:
        assert first.size == (300 + RULER, 1000 + 150 + RULER)
        red, green, _ = first.convert("RGB").getpixel((RULER + 70, RULER + 100))
        assert red > 180 and green < 90


def test_a_stretch_with_no_box_gets_no_image_and_the_rest_keep_numbers(
    tmp_path: Path,
) -> None:
    page = Image.new("RGB", (300, 3000), "white")

    paths = review_images(page, [Entry(1, Box(20, 2100, 120, 2160), "", "")], tmp_path / "001")

    assert [p.name for p in paths] == ["001-3.jpg"]


def test_the_overview_shows_the_whole_page_in_columns_with_every_box(tmp_path: Path) -> None:
    page = Image.new("RGB", (400, 9000), "white")
    entries = [Entry(1, Box(20, 100, 200, 160), "", ""), Entry(2, Box(20, 8500, 200, 8600), "", "")]

    path = overview(page, entries, tmp_path / "overview" / "001.jpg")

    with Image.open(path) as sheet:
        assert sheet.size == ((100 + 12) * 3, 1000)
        red, green, _ = sheet.convert("RGB").getpixel((5, 30))
        assert red - green > 60
