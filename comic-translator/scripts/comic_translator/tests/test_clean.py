"""Erasing: the text in a box unlike its paper, filled flat on even paper and redrawn on uneven."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from comic_translator.clean import erased as erased_patch
from comic_translator.clean import paper_in, shares_of
from comic_translator.notes import Box
from comic_translator.tests.fakes import FlatGrey

BOX = Box(100, 100, 300, 160)


def erased(page: Image.Image, box: Box, inpainter):
    patch = erased_patch(page, box, inpainter)
    done = page.copy()
    done.paste(patch.image, patch.at)
    return done


def bubble(paper: str, lower: str | None = None) -> Image.Image:
    """Black letters and a dot, as of `!`, on `paper`; the lower half on `lower` when given."""
    page = Image.new("RGB", (400, 300), paper)
    pen = ImageDraw.Draw(page)
    if lower:
        pen.rectangle((0, 130, 400, 300), fill=lower)
    for x in range(110, 270, 30):
        pen.rectangle((x, 110, x + 18, 140), fill="black")
    pen.ellipse((285, 145, 293, 153), fill="black")
    return page


def test_text_on_even_paper_is_filled_with_the_paper_colour_dot_and_all() -> None:
    done = erased(bubble("white"), BOX, FlatGrey)

    assert np.asarray(done)[100:160, 100:300].min() == 255


def test_text_on_two_tones_is_redrawn_by_the_inpainter() -> None:
    done = erased(bubble("#9e9e9e", lower="#e6d6cc"), BOX, FlatGrey)

    assert done.getpixel((120, 120)) == (128, 128, 128)


def test_paper_outside_the_box_is_never_touched() -> None:
    page = bubble("white")

    done = erased(page, BOX, FlatGrey)

    assert np.array_equal(np.asarray(done)[:, :90], np.asarray(page)[:, :90])


def test_paper_in_shades_of_white_counts_as_one_paper() -> None:
    shades = np.array([[255, 255, 255], [250, 252, 255], [245, 248, 250], [252, 250, 245]] * 25)

    assert len(shares_of(shades.astype(np.int16), 0.5)) >= 1


def test_a_dark_panel_stays_paper_while_dark_letters_of_its_colour_are_text() -> None:
    page = np.full((100, 200, 3), 255, dtype=np.int16)
    page[:30] = 0
    page[60:70, 50:60] = 0
    margin = np.ones((100, 200), dtype=np.bool_)
    box_mask = np.zeros_like(margin)
    box_mask[10:90, 20:180] = True

    paper = paper_in(page, margin, box_mask, None)

    assert paper[:30].all()
    assert not paper[60:70, 50:60].any()
