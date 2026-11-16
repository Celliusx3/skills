"""Letter a translation bold into the plain space its box opens onto, as tall as the original's."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFont

from comic_translator.clean import Patch
from comic_translator.notes import Box

FONT = Path(__file__).parent / "fonts" / "Mali-Bold.ttf"
SMALLEST = 8
LARGEST = 64
ORIGINAL_SHARE = 2.0
LINE_PITCH = 1.45
OUTLINE_SHARE = 0.08
CLEAN_NEAR = 60
INK_FAR = 100
INK_ROW_SHARE = 0.2
LINE_RUN_SHARE = 0.5
INSET_SHARE = 0.06
LEAST_ROOM = 0.4
SPREAD_SHARE = 1.0
LIGHT = 128
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

Span = tuple[int, int, int, int]
Colour = tuple[int, int, int]
Paint = tuple[Colour, Colour | None]
Pixels = NDArray[np.uint8]
Mask = NDArray[np.bool_]


@cache
def font_at(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), size)


@cache
def cap_of(size: int) -> int:
    """How tall a capital stands above its baseline at `size`."""
    return -int(font_at(size).getbbox("H", anchor="ls")[1])


@cache
def x_of(size: int) -> int:
    """How tall a lowercase letter without an ascender stands above its baseline at `size`."""
    return -int(font_at(size).getbbox("x", anchor="ls")[1])


@cache
def size_for(height: int, lower: bool = False) -> int:
    """The largest size whose capitals, or lowercase letters when `lower`, stand no taller than
    `height`."""
    measure = x_of if lower else cap_of
    size = SMALLEST
    while measure(size + 1) <= height:
        size += 1
    return size


def mostly_lower(written: str) -> bool:
    """Whether `written` has more lowercase letters than capitals, so the dense rows of its lines
    are its lowercase letters' height, not its capitals'."""
    return sum(c.islower() for c in written) > sum(c.isupper() for c in written)


def pitch_of(size: int) -> int:
    """How far apart two lines' baselines stand at `size`: LINE_PITCH of a capital's height."""
    return round(LINE_PITCH * cap_of(size))


def width_of(line: str, size: int) -> int:
    """How wide `line`'s ink spreads from its pen position at `size`, any overhang counted."""
    left, _, right, _ = font_at(size).getbbox(line, anchor="ls")
    return int(right - min(0, left))


def wrapped(text: str, size: int, width: int) -> list[str]:
    """`text` broken into lines no wider than `width` at `size`, a word too long kept whole."""
    lines: list[str] = []
    for word in text.split():
        joined = f"{lines[-1]} {word}" if lines else word
        if lines and width_of(joined, size) <= width:
            lines[-1] = joined
        else:
            lines.append(word)
    return lines


def inked(lines: list[str], size: int) -> tuple[int, int]:
    """How far the first line's ink reaches above its baseline, at least a capital's height, and
    how far the last line's reaches below."""
    if not lines:
        return cap_of(size), 0
    font = font_at(size)
    above = max(cap_of(size), -int(font.getbbox(lines[0], anchor="ls")[1]))
    return above, max(0, int(font.getbbox(lines[-1], anchor="ls")[3]))


def block_height(lines: list[str], size: int) -> int:
    above, below = inked(lines, size)
    return above + pitch_of(size) * (len(lines) - 1) + below


def fits(text: str, size: int, box: Box) -> list[str] | None:
    """The lines of `text` at `size` when their ink fits inside `box`, else None."""
    width, height = box.right - box.left, box.bottom - box.top
    lines = wrapped(text, size, width)
    wide = max((width_of(line, size) for line in lines), default=0)
    return lines if block_height(lines, size) <= height and wide <= width else None


def fitted(text: str, box: Box, most: int) -> tuple[int, list[str]]:
    """The largest size, `most` at the most, at which `text` fits the box."""
    for size in range(min(most, size_for(box.bottom - box.top)), SMALLEST - 1, -1):
        lines = fits(text, size, box)
        if lines is not None:
            return size, lines
    return SMALLEST, wrapped(text, SMALLEST, box.right - box.left)


def runs_of(rows: Mask) -> list[int]:
    """The lengths of the stretches of True in `rows`."""
    edges = np.diff(np.concatenate([[0], rows.astype(np.int8), [0]]))
    return (np.where(edges == -1)[0] - np.where(edges == 1)[0]).tolist()


def background_of(piece: Pixels) -> NDArray[np.float64]:
    return np.median(piece.reshape(-1, 3), axis=0)


def letter_height(piece: Pixels) -> int | None:
    """How tall the original's lines of letters stand: the typical stretch of rows dense with
    ink, an accent's or an outline's sparse rows left out; None when there is no ink."""
    far = np.abs(piece.astype(np.int16) - background_of(piece)).max(axis=-1) > INK_FAR
    ink = far.sum(axis=1)
    if ink.max() == 0:
        return None
    runs = runs_of(ink >= INK_ROW_SHARE * ink.max())
    return int(np.median([run for run in runs if run >= LINE_RUN_SHARE * max(runs)]))


def widest_under(heights: list[int], row: int) -> tuple[int, Span]:
    """The largest rectangle standing on one row of column heights: its area and its span."""
    best: tuple[int, Span] = (0, (row, 0, row, 0))
    stack: list[tuple[int, int]] = []
    for column, height in enumerate([*heights, 0]):
        start = column
        while stack and stack[-1][1] >= height:
            start, tall = stack.pop()
            best = max(best, (tall * (column - start), (row + 1 - tall, start, row + 1, column)))
        stack.append((start, height))
    return best


def largest_rectangle(mask: Mask) -> Span:
    """The largest upright rectangle of True in `mask`, as top, left, bottom, right."""
    heights = np.zeros(mask.shape[1], dtype=np.int64)
    best: tuple[int, Span] = (0, (0, 0, 0, 0))
    for row, line in enumerate(mask):
        heights = np.where(line, heights + 1, 0)
        best = max(best, widest_under(heights.tolist(), row))
    return best[1]


def plain_of(piece: Pixels, background: NDArray[np.float64]) -> Mask:
    return np.abs(piece.astype(np.int16) - background).max(axis=-1) <= CLEAN_NEAR


def room_in(piece: Pixels, box: Box) -> tuple[Span, bool]:
    """The largest plain stretch of the box's background and True; the whole box and False when
    that stretch is too small to letter in."""
    top, left, bottom, right = largest_rectangle(plain_of(piece, background_of(piece)))
    if (bottom - top) * (right - left) >= LEAST_ROOM * box.area():
        return (top, left, bottom, right), True
    return (0, 0, box.bottom - box.top, box.right - box.left), False


def pushed(plain: Mask, span: Span) -> Span:
    """`span` grown by a row or a column on each side whose new edge is all plain."""
    top, left, bottom, right = span
    top -= int(plain[top - 1, left:right].all())
    bottom += int(plain[bottom, left:right].all())
    left -= int(plain[top:bottom, left - 1].all())
    right += int(plain[top:bottom, right].all())
    return top, left, bottom, right


def spread(plain: Mask, seed: Span) -> Span:
    """The rectangle `seed` grows into across `plain` until every side meets something not."""
    walled = np.pad(plain, 1, constant_values=False)
    top, left, bottom, right = seed
    span: Span = (top + 1, left + 1, bottom + 1, right + 1)
    while (grown := pushed(walled, span)) != span:
        span = grown
    top, left, bottom, right = span
    return top - 1, left - 1, bottom - 1, right - 1


def around(box: Box, size: tuple[int, int]) -> Box:
    """How far the lettering may reach: SPREAD_SHARE of the box's height past it, on the page."""
    reach = round(SPREAD_SHARE * (box.bottom - box.top))
    width, height = size
    return Box(
        max(0, box.left - reach),
        max(0, box.top - reach),
        min(width, box.right + reach),
        min(height, box.bottom + reach),
    )


def free_of(plain: Mask, area: Box, taken: list[Box]) -> Mask:
    """`plain` with every other entry's box in `area` marked as not plain."""
    free = plain.copy()
    for other in taken:
        rows = slice(max(0, other.top - area.top), max(0, other.bottom - area.top))
        columns = slice(max(0, other.left - area.left), max(0, other.right - area.left))
        free[rows, columns] = False
    return free


def inset(span: Span) -> Box:
    """`span` drawn in by INSET_SHARE of its shorter side, as a box."""
    top, left, bottom, right = span
    step = round(INSET_SHARE * min(bottom - top, right - left))
    left, top = left + step, top + step
    return Box(left, top, max(left + 1, right - step), max(top + 1, bottom - step))


def shifted(span: Span, rows: int, columns: int) -> Span:
    top, left, bottom, right = span
    return top + rows, left + columns, bottom + rows, right + columns


def room_around(page: Image.Image, box: Box, taken: list[Box]) -> tuple[Box, Box, bool]:
    """The part of the page to letter on, the room in it, and whether the room is plain: the
    box's plain stretch spread across the background around it, clear of other entries; on a
    busy background, the box alone."""
    inner = np.asarray(page.crop(box.corners()))
    seed, roomy = room_in(inner, box)
    if not roomy:
        return box, inset(seed), False
    area = around(box, page.size)
    plain = free_of(
        plain_of(np.asarray(page.crop(area.corners())), background_of(inner)), area, taken
    )
    return area, inset(spread(plain, shifted(seed, box.top - area.top, box.left - area.left))), True


def tallest(original: Image.Image, box: Box, written: str) -> int:
    """The largest size the original's letters allow, matched on lowercase letters when
    `written`, the original's text, is mostly lowercase; the box's height when they cannot be
    told."""
    height = letter_height(np.asarray(original.crop(box.corners())))
    if height is None:
        return size_for(box.bottom - box.top)
    return size_for(height, mostly_lower(written))


def colours(page: Image.Image, box: Box) -> tuple[Colour, Colour]:
    """Black letters edged white on light paper, white edged black on dark."""
    light = float(background_of(np.asarray(page.crop(box.corners()))).mean()) > LIGHT
    return (BLACK, WHITE) if light else (WHITE, BLACK)


def drawn(done: Image.Image, room: Box, lines: list[str], size: int, paint: Paint) -> None:
    """`lines` at `size` centred in `room` in the paint's ink, edged in its edge if it has one."""
    ink, edge = paint
    step = pitch_of(size)
    above, _ = inked(lines, size)
    baseline = room.top + (room.bottom - room.top - block_height(lines, size)) // 2 + above
    centre = (room.left + room.right) // 2
    stroke = 0 if edge is None else max(1, round(OUTLINE_SHARE * size))
    pen = ImageDraw.Draw(done)
    for number, line in enumerate(lines):
        left, _, right, _ = font_at(size).getbbox(line, anchor="ls")
        at = (centre - (left + right) // 2, baseline + number * step)
        pen.text(
            at,
            line,
            font=font_at(size),
            fill=ink,
            anchor="ls",
            stroke_width=stroke,
            stroke_fill=edge or ink,
        )


def filling_size(
    page: Image.Image, original: Image.Image, box: Box, text: str, taken: list[Box], written: str
) -> int:
    """The largest size at which `text` fills the room around `box`, no more than ORIGINAL_SHARE
    of the original's letters, `written` being their text."""
    _, room, _ = room_around(page, box, taken)
    most = min(LARGEST, round(ORIGINAL_SHARE * tallest(original, box, written)))
    return fitted(text, room, most)[0]


def lettered(
    page: Image.Image,
    original: Image.Image,
    box: Box,
    text: str,
    taken: list[Box],
    written: str,
    most: int | None = None,
) -> Patch:
    """The piece of `page` around `box` with `text` lettered in its plain room, no taller than
    `most`, or than the original's letters, `written` being their text, when `most` is not
    given; on a busy background, inside the box and edged."""
    area, room, roomy = room_around(page, box, taken)
    done = page.crop(area.corners())
    size, lines = fitted(text, room, most if most is not None else tallest(original, box, written))
    ink, edge = colours(page, box)
    drawn(done, room, lines, size, (ink, None if roomy else edge))
    return Patch(done, (area.left, area.top))
