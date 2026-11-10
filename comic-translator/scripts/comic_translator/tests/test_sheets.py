"""Box sheets: each box cut out with its margin, enlarged, numbered, sheets filled in order."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from comic_translator.notes import Box, Entry
from comic_translator.sheets import LABEL, MARGIN, TALL, WIDTH, box_sheets, laid_out, tile


def test_a_small_box_is_cut_with_its_margin_and_enlarged_under_its_label() -> None:
    page = Image.new("RGB", (400, 400), "white")
    ImageDraw.Draw(page).rectangle((100, 100, 139, 119), fill="black")

    cut = tile(page, Entry(7, Box(100, 100, 140, 120), "", ""))

    assert cut.size == (2 * (40 + 2 * MARGIN), 2 * (20 + 2 * MARGIN) + LABEL)
    assert cut.getpixel((2 * MARGIN + 10, LABEL + 2 * MARGIN + 10)) == (0, 0, 0)
    red, green, _ = cut.getpixel((4, 4))
    assert red > 180 and green < 90


def test_a_box_at_the_page_edge_is_cut_without_reaching_past_it() -> None:
    page = Image.new("RGB", (100, 100), "white")

    cut = tile(page, Entry(1, Box(0, 0, 50, 30), "", ""))

    assert cut.size == (2 * (50 + MARGIN), 2 * (30 + MARGIN) + LABEL)


def test_tiles_fill_rows_then_start_a_new_sheet_when_one_is_full() -> None:
    tiles = [Image.new("RGB", (400, 600), "white") for _ in range(6)]

    sheets = laid_out(tiles)

    assert [sheet.size for sheet in sheets] == [(WIDTH, 2 * 600 + 14), (WIDTH, 600)]
    assert all(sheet.height <= TALL for sheet in sheets)


def test_sheets_are_saved_numbered_and_a_page_with_no_entries_gets_none(tmp_path: Path) -> None:
    page = Image.new("RGB", (400, 400), "white")
    entries = [Entry(1, Box(10, 10, 60, 40), "", ""), Entry(2, Box(10, 200, 60, 230), "", "")]

    paths = box_sheets(page, entries, tmp_path / "boxes" / "001")

    assert [p.name for p in paths] == ["001-1.jpg"]
    assert box_sheets(page, [], tmp_path / "boxes" / "002") == []
