"""Detection: pages unpacked in order, the text map run in tiles, lines grown into blocks."""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from comic_translator.detect import DetectError, blocks, line_boxes, page_blocks, text_map, unpacked
from comic_translator.notes import Box
from comic_translator.tests.fakes import DarkIsText, page_with_lines


def test_an_archive_is_unpacked_in_name_order_and_only_its_images(tmp_path: Path) -> None:
    archive = tmp_path / "chapter.cbz"
    with zipfile.ZipFile(archive, "w") as packed:
        for name in ("b/002.png", "001.jpg", "notes.txt"):
            packed.writestr(name, b"x")

    pages = unpacked(archive, tmp_path / "pages")

    assert [page.name for page in pages] == ["001.jpg", "002.png"]


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

    assert blocks(lines) == [Box(10, 10, 200, 55), Box(10, 300, 100, 320)]


def test_trailing_dots_overlapping_their_word_join_it_however_small() -> None:
    lines = [Box(510, 9982, 616, 10055), Box(601, 10024, 640, 10047)]

    assert blocks(lines) == [Box(510, 9982, 640, 10055)]


def test_blocks_left_overlapping_after_grouping_become_one_block() -> None:
    lines = [Box(172, 79, 700, 130), Box(172, 150, 500, 200), Box(618, 135, 1016, 260)]

    assert blocks(lines) == [Box(172, 79, 1016, 260)]


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

    assert blocks(lines) == [Box(10, 0, 300, 20), Box(0, 40, 700, 530), Box(10, 560, 300, 610)]
