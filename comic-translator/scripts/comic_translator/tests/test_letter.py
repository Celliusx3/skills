"""Lettering: the translation wrapped and sized to fit the plain space around its box, bold."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from comic_translator.clean import Patch
from comic_translator.letter import (
    cap_of,
    fitted,
    largest_rectangle,
    letter_height,
    lettered,
    room_in,
)
from comic_translator.notes import Box

BOX = Box(50, 50, 250, 150)
OFFER = "HEY, I'D LIKE TO OFFER YOU A RECORDING CONTRACT."


def bubble(text_height: int) -> tuple[Image.Image, Image.Image, Box]:
    """An erased bubble, the original with a line of text `text_height` tall, and its box."""
    page = Image.new("RGB", (400, 300), "white")
    ImageDraw.Draw(page).rectangle((40, 60, 360, 240), outline="black", width=4)
    original = page.copy()
    pen = ImageDraw.Draw(original)
    for left in range(134, 266, 6):
        pen.rectangle((left, 142, left + 1, 142 + text_height - 1), fill="black")
    return page, original, Box(130, 140, 270, 140 + text_height + 4)


def dark(patch: Patch) -> NDArray[np.bool_]:
    return np.asarray(patch.image.convert("L")) < 128


def ink_rows(patch: Patch) -> NDArray[np.intp]:
    return np.where(dark(patch).any(axis=1))[0] + patch.at[1]


def test_a_long_translation_is_wrapped_and_shrunk_until_it_fits() -> None:
    size, lines = fitted("IF ANOTHER MAN ROUGHLY TREATS HIS WIFE", BOX, 100)

    assert len(lines) > 1
    assert cap_of(size) * len(lines) <= 100


def test_a_word_too_long_for_any_size_is_kept_whole_at_the_smallest_size() -> None:
    size, lines = fitted("A" * 200, Box(0, 0, 30, 20), 100)

    assert (size, lines) == (8, ["A" * 200])


def test_the_largest_rectangle_of_a_mask_is_found() -> None:
    mask = np.zeros((10, 12), dtype=np.bool_)
    mask[2:8, 3:11] = True
    mask[0:10, 0:1] = True

    assert largest_rectangle(mask) == (2, 3, 8, 11)


def test_the_room_keeps_off_a_bubble_outline_the_box_reaches_over() -> None:
    piece = np.full((100, 200, 3), 255, dtype=np.uint8)
    piece[:, 170:] = 0

    (_, left, _, right), roomy = room_in(piece, BOX)

    assert roomy
    assert 0 <= left < right <= 170


def test_a_busy_box_is_lettered_across_the_whole_box() -> None:
    noise = np.random.default_rng(0).integers(0, 256, (100, 200, 3), dtype=np.uint8)

    (_, left, _, right), roomy = room_in(noise, BOX)

    assert not roomy
    assert right - left == 200


def test_light_paper_gets_black_letters_and_the_page_is_untouched() -> None:
    page = Image.new("RGB", (300, 200), "silver")

    piece = np.asarray(lettered(page, page, BOX, "HELLO THERE", []).image)

    assert piece.min() == 0
    assert piece.max() == 192
    assert np.asarray(page).max() == 192


def test_dark_paper_gets_white_letters() -> None:
    page = Image.new("RGB", (300, 200), "black")

    piece = np.asarray(lettered(page, page, BOX, "HELLO THERE", []).image)

    assert piece.max() == 255


def test_a_busy_box_is_lettered_inside_it_with_an_edge() -> None:
    noise = np.random.default_rng(0).integers(0, 256, (200, 300, 3), dtype=np.uint8)
    page = Image.fromarray(noise)

    patch = lettered(page, page, BOX, "HELLO", [])

    assert patch.at == (BOX.left, BOX.top)
    assert patch.image.size == (200, 100)


def test_the_original_letters_height_is_one_line_s_rows_of_ink() -> None:
    _, original, box = bubble(12)

    assert letter_height(np.asarray(original.crop(box.corners()))) == 12
    assert letter_height(np.full((20, 40, 3), 255, dtype=np.uint8)) is None


def test_a_long_line_in_a_tight_box_spreads_into_its_bubble_at_the_original_letters_height() -> (
    None
):
    page, original, box = bubble(16)

    rows = ink_rows(lettered(page, original, box, OFFER, []))

    assert rows.min() < box.top and rows.max() > box.bottom
    assert rows.min() > 64 and rows.max() < 236


def test_the_lettering_is_never_taller_than_the_original_letters() -> None:
    page, original, box = bubble(12)

    rows = ink_rows(lettered(page, original, box, "HI", []))

    assert 10 <= rows.max() - rows.min() + 1 <= 12


def test_the_lettering_keeps_out_of_another_entry_s_box() -> None:
    page, original, box = bubble(16)
    neighbour = Box(60, 100, 340, 135)

    patch = lettered(page, original, box, OFFER, [neighbour])

    assert ink_rows(patch).min() >= neighbour.bottom


def test_the_letters_are_drawn_bold() -> None:
    page = Image.new("RGB", (200, 100), "white")

    inked = dark(lettered(page, page, Box(0, 0, 200, 100), "I", []))
    rows = inked[inked.any(axis=1)]

    assert rows[len(rows) // 2].sum() >= 0.18 * len(rows)


def test_a_line_as_wide_as_its_room_keeps_its_last_letter_whole() -> None:
    page = Image.new("RGB", (300, 60), "white")
    box = Box(0, 0, 300, 60)

    inked = dark(lettered(page, page, box, "SOMETIMES BANKS HAVE MORE CASH ON HAND", []))
    columns = np.where(inked.any(axis=0))[0]

    assert columns.min() > 0 and columns.max() < 299
