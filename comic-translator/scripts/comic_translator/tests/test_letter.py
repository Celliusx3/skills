"""Lettering: the translation wrapped and sized to fit the plain space in its box, in contrast."""

from __future__ import annotations

import numpy as np
from PIL import Image

from comic_translator.letter import fitted, largest_rectangle, lettered, room_in
from comic_translator.notes import Box

BOX = Box(50, 50, 250, 150)


def test_a_long_translation_is_wrapped_and_shrunk_until_it_fits() -> None:
    size, lines = fitted("IF ANOTHER MAN ROUGHLY TREATS HIS WIFE", BOX)

    assert len(lines) > 1
    assert size * 1.1 * len(lines) <= 100


def test_a_word_too_long_for_any_size_is_kept_whole_at_the_smallest_size() -> None:
    size, lines = fitted("A" * 200, Box(0, 0, 30, 20))

    assert (size, lines) == (8, ["A" * 200])


def test_the_largest_rectangle_of_a_mask_is_found() -> None:
    mask = np.zeros((10, 12), dtype=np.bool_)
    mask[2:8, 3:11] = True
    mask[0:10, 0:1] = True

    assert largest_rectangle(mask) == (2, 3, 8, 11)


def test_the_room_keeps_off_a_bubble_outline_the_box_reaches_over() -> None:
    piece = np.full((100, 200, 3), 255, dtype=np.uint8)
    piece[:, 170:] = 0

    room, roomy = room_in(piece, BOX)

    assert roomy
    assert room.right < 170
    assert room.left >= 0


def test_a_busy_box_is_lettered_across_the_whole_box() -> None:
    noise = np.random.default_rng(0).integers(0, 256, (100, 200, 3), dtype=np.uint8)

    room, roomy = room_in(noise, BOX)

    assert not roomy
    assert room.right - room.left > 180


def test_light_paper_gets_black_letters_and_the_page_is_untouched() -> None:
    page = Image.new("RGB", (300, 200), "silver")

    piece = np.asarray(lettered(page, BOX, "HELLO THERE"))

    assert piece.shape == (100, 200, 3)
    assert piece.min() == 0
    assert piece.max() == 192
    assert np.asarray(page).max() == 192


def test_dark_paper_gets_white_letters() -> None:
    page = Image.new("RGB", (300, 200), "black")

    piece = np.asarray(lettered(page, BOX, "HELLO THERE"))

    assert piece.max() == 255
