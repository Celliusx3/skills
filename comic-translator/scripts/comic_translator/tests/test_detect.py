"""Detection: pages unpacked in order, the text map run in tiles, lines grown into blocks."""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from comic_translator.detect import (
    DetectError,
    Paper,
    blocks,
    line_boxes,
    page_blocks,
    papers,
    text_map,
    unpacked,
)
from comic_translator.notes import Box
from comic_translator.tests.fakes import DarkIsText, page_with_lines

ONE_PAPER = Paper(
    np.ones((10100, 1100), dtype=np.int32), np.full((10100, 1100, 3), 255, dtype=np.uint8)
)


def bubbles(outlines: list[tuple[int, int, int, int]], size=(400, 300)) -> Image.Image:
    """A white page with a black outline drawn round each bubble."""
    page = Image.new("RGB", size, "white")
    pen = ImageDraw.Draw(page)
    for outline in outlines:
        pen.rectangle(outline, outline="black", width=2)
    return page


def test_an_archive_is_unpacked_in_name_order_and_only_its_images(tmp_path: Path) -> None:
    archive = tmp_path / "chapter.cbz"
    with zipfile.ZipFile(archive, "w") as packed:
        for name in ("b/002.png", "001.jpg", "notes.txt"):
            packed.writestr(name, b"x")

    pages = unpacked(archive, tmp_path / "pages")

    assert [page.name for page in pages] == ["001.jpg", "002.png"]


def test_the_hidden_copies_a_mac_adds_to_an_archive_are_not_pages(tmp_path: Path) -> None:
    archive = tmp_path / "chapter.zip"
    with zipfile.ZipFile(archive, "w") as packed:
        for name in ("page-1.jpg", "__MACOSX/._page-1.jpg", "page-2.jpg", "._page-2.jpg"):
            packed.writestr(name, b"x")

    pages = unpacked(archive, tmp_path / "pages")

    assert [page.name for page in pages] == ["page-1.jpg", "page-2.jpg"]


def test_pages_numbered_without_leading_zeros_are_unpacked_in_number_order(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "chapter.zip"
    with zipfile.ZipFile(archive, "w") as packed:
        for name in ("100.jpg", "10.jpg", "9.jpg", "11.jpg"):
            packed.writestr(name, b"x")

    pages = unpacked(archive, tmp_path / "pages")

    assert [page.name for page in pages] == ["9.jpg", "10.jpg", "11.jpg", "100.jpg"]


def test_an_image_is_its_own_single_page(tmp_path: Path) -> None:
    page = page_with_lines(tmp_path / "007.png", [])

    assert [p.name for p in unpacked(page, tmp_path / "pages")] == ["007.png"]


@pytest.mark.parametrize(
    ("name", "complaint"), [("notes.txt", "is not an image"), ("empty.zip", "holds no images")]
)
def test_an_input_with_no_pages_is_refused(tmp_path: Path, name: str, complaint: str) -> None:
    source = tmp_path / name
    if name.endswith(".zip"):
        with zipfile.ZipFile(source, "w") as packed:
            packed.writestr("readme.txt", b"x")
    else:
        source.write_text("x")

    with pytest.raises(DetectError, match=complaint):
        unpacked(source, tmp_path / "pages")


def test_the_text_map_covers_a_page_taller_than_one_tile(tmp_path: Path) -> None:
    page = Image.open(
        page_with_lines(tmp_path / "tall.png", [(50, 1500, 150, 1520)], size=(300, 2600))
    )

    likely = text_map(DarkIsText(), page.convert("RGB"))

    assert likely.shape == (2600, 300)
    assert likely[1510, 100] == 1.0
    assert likely[100, 100] == 0.0


def test_a_sure_line_is_grown_back_over_its_letters_and_specks_are_dropped() -> None:
    likely = np.zeros((200, 300), dtype=np.float32)
    likely[100:110, 50:250] = 0.9
    likely[20:22, 20:22] = 0.9

    [line] = line_boxes(likely)

    assert line.left < 50 and line.right > 250 and line.top < 100 and line.bottom > 110


def test_lines_stacked_close_become_one_block_and_far_ones_stay_apart() -> None:
    lines = [Box(10, 10, 200, 30), Box(20, 35, 180, 55), Box(10, 300, 100, 320)]

    assert blocks(lines, ONE_PAPER) == [Box(10, 10, 200, 55), Box(10, 300, 100, 320)]


def test_trailing_dots_overlapping_their_word_join_it_however_small() -> None:
    lines = [Box(510, 9982, 616, 10055), Box(601, 10024, 640, 10047)]

    assert blocks(lines, ONE_PAPER) == [Box(510, 9982, 640, 10055)]


def test_blocks_left_overlapping_after_grouping_become_one_block() -> None:
    lines = [Box(172, 79, 700, 130), Box(172, 150, 500, 200), Box(618, 135, 1016, 260)]

    assert blocks(lines, ONE_PAPER) == [Box(172, 79, 1016, 260)]


def test_a_page_s_blocks_are_its_lines_of_text(tmp_path: Path) -> None:
    page = Image.open(
        page_with_lines(
            tmp_path / "p.png", [(40, 50, 300, 62), (40, 70, 280, 82), (60, 400, 200, 412)]
        )
    )

    found, likely = page_blocks(DarkIsText(), page.convert("RGB"))

    assert len(found) == 2
    assert found[0].top < 50 and found[0].bottom > 82
    assert likely.size == page.size


def test_a_tall_burst_never_swallows_the_lines_round_it_into_one_block() -> None:
    lines = [Box(10, 0, 300, 20), Box(0, 40, 700, 530), Box(10, 560, 300, 580)]
    lines.append(Box(10, 590, 300, 610))

    assert blocks(lines, ONE_PAPER) == [
        Box(10, 0, 300, 20),
        Box(0, 40, 700, 530),
        Box(10, 560, 300, 610),
    ]


def test_lines_close_but_in_two_bubbles_become_two_blocks() -> None:
    page = bubbles([(20, 20, 380, 63), (20, 66, 380, 120)])
    lines = [Box(40, 40, 360, 60), Box(40, 72, 360, 92), Box(40, 90, 360, 110)]

    assert blocks(lines, papers(page)) == [Box(40, 40, 360, 60), Box(40, 72, 360, 110)]


def test_blocks_of_two_bubbles_overlapping_at_a_corner_stay_apart() -> None:
    page = bubbles([(20, 20, 200, 120), (204, 20, 390, 120)])
    lines = [Box(30, 30, 210, 60), Box(30, 62, 190, 90), Box(205, 80, 380, 110)]
    lines.append(Box(214, 30, 380, 55))

    found = blocks(lines, papers(page))

    assert found == [Box(30, 30, 210, 90), Box(214, 30, 380, 55), Box(205, 80, 380, 110)]


def test_a_dark_caption_s_lines_share_its_ink_and_stay_one_block() -> None:
    page = Image.new("RGB", (400, 300), "white")
    ImageDraw.Draw(page).rectangle((20, 20, 380, 140), fill="black")
    lines = [Box(40, 40, 360, 60), Box(40, 62, 360, 82)]

    assert blocks(lines, papers(page)) == [Box(40, 40, 360, 82)]


def test_two_lobes_of_one_balloon_stepping_aside_become_two_blocks() -> None:
    lines = [Box(657, 595, 695, 613), Box(692, 617, 895, 638), Box(684, 633, 899, 653)]

    assert blocks(lines, ONE_PAPER) == [Box(657, 595, 695, 613), Box(684, 617, 899, 653)]


@pytest.mark.parametrize(
    "lines",
    [
        [Box(80, 606, 424, 623), Box(108, 624, 481, 641)],
        [Box(300, 100, 500, 120), Box(340, 125, 460, 145)],
        [Box(586, 359, 826, 380), Box(640, 391, 760, 411)],
    ],
    ids=["hanging indent", "centred", "short line under a long one"],
)
def test_one_bubble_s_lines_however_ragged_stay_one_block(lines: list[Box]) -> None:
    assert len(blocks(lines, ONE_PAPER)) == 1


def test_lines_on_white_and_on_pink_paper_touching_become_two_blocks() -> None:
    page = Image.new("RGB", (400, 300), "white")
    ImageDraw.Draw(page).rectangle((20, 64, 380, 140), fill=(250, 232, 226))
    lines = [Box(40, 40, 360, 60), Box(40, 72, 360, 92)]

    assert blocks(lines, papers(page)) == [Box(40, 40, 360, 60), Box(40, 72, 360, 92)]


def test_lines_overlapping_on_one_stretch_of_two_colours_stay_two_blocks() -> None:
    page = Image.new("RGB", (400, 300), "white")
    ImageDraw.Draw(page).rectangle((150, 72, 380, 140), fill=(250, 200, 150))
    lines = [Box(40, 40, 200, 70), Box(150, 60, 360, 100)]

    assert blocks(lines, papers(page)) == [Box(40, 40, 200, 70), Box(150, 60, 360, 100)]


def test_a_bubble_s_word_and_a_banner_tucked_under_it_become_two_blocks() -> None:
    page = Image.new("RGB", (700, 700), (248, 248, 248))
    ImageDraw.Draw(page).rectangle((480, 630, 640, 680), fill=(232, 240, 240))
    lines = [Box(439, 597, 533, 637), Box(499, 632, 617, 664)]

    assert blocks(lines, papers(page)) == lines


def test_a_caption_s_lines_on_two_shades_of_its_paper_stay_one_block() -> None:
    page = Image.new("RGB", (500, 300), (248, 248, 248))
    ImageDraw.Draw(page).rectangle((0, 116, 500, 300), fill=(226, 226, 226))
    lines = [Box(85, 100, 424, 117), Box(77, 116, 432, 133), Box(55, 132, 454, 149)]

    assert blocks(lines, papers(page)) == [Box(55, 100, 454, 149)]
