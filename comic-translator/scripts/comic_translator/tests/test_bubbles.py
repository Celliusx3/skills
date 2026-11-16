"""Lines of one paragraph joined into one box."""

from __future__ import annotations

from comic_translator.bubbles import by_paragraph
from comic_translator.notes import Box


def test_stacked_lines_of_one_bubble_become_one_box() -> None:
    lines = [Box(100, 1458, 273, 1497), Box(80, 1502, 330, 1627)]

    assert by_paragraph(lines) == [Box(80, 1458, 330, 1627)]


def test_a_bubble_further_down_stays_its_own_box() -> None:
    boxes = [Box(80, 1833, 344, 1960), Box(90, 1973, 393, 2031), Box(60, 2191, 354, 2330)]

    assert by_paragraph(boxes) == [Box(80, 1833, 393, 2031), Box(60, 2191, 354, 2330)]


def test_lines_side_by_side_in_different_bubbles_stay_apart() -> None:
    boxes = [Box(10, 100, 100, 140), Box(300, 145, 400, 190)]

    assert by_paragraph(boxes) == boxes
