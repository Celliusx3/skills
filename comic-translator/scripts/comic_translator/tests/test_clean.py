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


def test_a_mark_beside_the_text_does_not_stop_even_paper_being_filled_flat() -> None:
    page = bubble("white")
    ImageDraw.Draw(page).rectangle((296, 112, 312, 138), fill="black")

    done = erased(page, BOX, FlatGrey)

    assert done.getpixel((120, 120)) == (255, 255, 255)


def test_a_border_running_past_the_box_does_not_make_an_accent_look_like_a_speck() -> None:
    page = bubble("white")
    pen = ImageDraw.Draw(page)
    pen.rectangle((94, 0, 96, 300), fill="black")
    pen.rectangle((112, 103, 116, 105), fill="black")

    done = erased(page, BOX, FlatGrey)

    assert np.asarray(done)[100:160, 100:300].min() == 255


def round_bubble(panel: str = "#3c3c96") -> tuple[Image.Image, Image.Image]:
    """Two lines of letters in a pink bubble with a black outline on `panel`, and the text
    finder's bars along the lines, reaching within a few pixels of the outline."""
    page = Image.new("RGB", (400, 300), panel)
    likely = Image.new("L", (400, 300), 0)
    pen, seen = ImageDraw.Draw(page), ImageDraw.Draw(likely)
    pen.ellipse((80, 80, 320, 220), fill=(255, 236, 229), outline="black", width=3)
    for top in (130, 160):
        for x in range(130, 270, 30):
            pen.rectangle((x, top, x + 18, top + 15), fill="black")
        seen.rectangle((100, top + 4, 300, top + 11), fill=255)
    return page, likely


def test_a_box_reaching_past_its_bubble_erases_the_text_and_keeps_the_outline_and_panel() -> None:
    page, likely = round_bubble()
    before = np.asarray(page).copy()

    patch = erased_patch(page, Box(90, 90, 310, 210), FlatGrey, likely)
    page.paste(patch.image, patch.at)
    after = np.asarray(page)

    letters = np.zeros(before.shape[:2], dtype=np.bool_)
    letters[128:178, 128:290] = True
    outline = (before.max(axis=-1) < 100) & ~letters
    assert np.array_equal(after[outline], before[outline])
    assert np.array_equal(after[90:100, 90:100], before[90:100, 90:100])
    assert after[130:176, 130:288].min() > 200


def test_a_pink_bubble_on_a_white_page_is_filled_pink_not_with_the_page_round_it() -> None:
    page, likely = round_bubble("white")

    patch = erased_patch(page, Box(80, 80, 320, 220), FlatGrey, likely)
    page.paste(patch.image, patch.at)

    assert page.getpixel((140, 137)) == (255, 236, 229)


def test_a_letter_touching_the_outline_is_erased_while_the_outline_stays() -> None:
    page, likely = round_bubble()
    ImageDraw.Draw(page).rectangle((190, 207, 208, 217), fill="black")
    ImageDraw.Draw(likely).rectangle((186, 209, 212, 214), fill=255)
    before = np.asarray(page).copy()

    patch = erased_patch(page, Box(90, 90, 310, 222), FlatGrey, likely)
    page.paste(patch.image, patch.at)
    after = np.asarray(page)

    assert after[207:216, 190:209].min() > 200
    rim = (before.max(axis=-1) < 100) & (np.arange(300)[:, None] > 190)
    rim[:, 180:220] = False
    assert np.array_equal(after[rim], before[rim])


def test_letters_on_a_tinted_caption_running_past_the_box_are_erased_and_its_border_kept() -> None:
    page = Image.new("RGB", (400, 300), (255, 236, 229))
    likely = Image.new("L", (400, 300), 0)
    pen, seen = ImageDraw.Draw(page), ImageDraw.Draw(likely)
    pen.rectangle((0, 104, 399, 126), fill=(205, 189, 220), outline="black", width=2)
    for top in (108, 150):
        for x in range(110, 270, 30):
            pen.rectangle((x, top, x + 18, top + 14), fill="black")
        seen.rectangle((110, top + 4, 288, top + 10), fill=255)
    before = np.asarray(page).copy()

    patch = erased_patch(page, Box(90, 90, 310, 190), FlatGrey, likely)
    page.paste(patch.image, patch.at)
    after = np.asarray(page)

    assert after[108:123, 110:288].min() > 100
    assert np.array_equal(after[104:106], before[104:106])


def test_a_caption_narrowing_under_its_last_line_is_filled_with_its_paper_not_the_panel() -> None:
    page = Image.new("RGB", (400, 300), (104, 189, 234))
    likely = Image.new("L", (400, 300), 0)
    pen, seen = ImageDraw.Draw(page), ImageDraw.Draw(likely)
    pen.rectangle((80, 90, 330, 130), fill="white")
    pen.rectangle((80, 130, 258, 156), fill="white")
    for top, right in ((100, 320), (116, 320), (132, 250)):
        for x in range(90, right, 16):
            pen.rectangle((x, top, x + 12, top + 11), fill="black")
        seen.rectangle((90, top + 3, right, top + 8), fill=255)

    patch = erased_patch(page, Box(88, 98, 322, 146), FlatGrey, likely)
    page.paste(patch.image, patch.at)
    after = np.asarray(page)

    assert after[100:143, 90:246].min() == 255
    assert page.getpixel((300, 140)) == (104, 189, 234)
