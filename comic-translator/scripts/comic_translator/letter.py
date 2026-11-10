"""Letter a translation into the plain space in its box, sized to fit, in high contrast."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFont

from comic_translator.notes import Box

FONT = Path(__file__).parent / "fonts" / "ComicNeue-Bold.ttf"
LARGEST = 0.9
SMALLEST = 8
LINE_SPACING = 1.1
OUTLINE_SHARE = 0.08
CLEAN_NEAR = 60
INSET_SHARE = 0.06
LEAST_ROOM = 0.4
LIGHT = 128
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

Span = tuple[int, int, int, int]


@cache
def font_at(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), size)


def wrapped(text: str, size: int, width: int) -> list[str]:
    """`text` broken into lines no wider than `width` at `size`, a word too long kept whole."""
    font = font_at(size)
    lines: list[str] = []
    for word in text.split():
        joined = f"{lines[-1]} {word}" if lines else word
        if lines and font.getlength(joined) <= width:
            lines[-1] = joined
        else:
            lines.append(word)
    return lines


def fits(text: str, size: int, box: Box) -> list[str] | None:
    """The lines of `text` at `size` when they fit inside `box`, else None."""
    width, height = box.right - box.left, box.bottom - box.top
    lines = wrapped(text, size, width)
    font = font_at(size)
    tall = round(size * LINE_SPACING) * len(lines)
    wide = max((font.getlength(line) for line in lines), default=0)
    return lines if tall <= height and wide <= width else None


def fitted(text: str, box: Box) -> tuple[int, list[str]]:
    """The largest size, from LARGEST of the box's height down, at which `text` fits the box."""
    for size in range(max(SMALLEST, round(LARGEST * (box.bottom - box.top))), SMALLEST - 1, -1):
        lines = fits(text, size, box)
        if lines is not None:
            return size, lines
    return SMALLEST, wrapped(text, SMALLEST, box.right - box.left)


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


def largest_rectangle(mask: NDArray[np.bool_]) -> Span:
    """The largest upright rectangle of True in `mask`, as top, left, bottom, right."""
    heights = np.zeros(mask.shape[1], dtype=np.int64)
    best: tuple[int, Span] = (0, (0, 0, 0, 0))
    for row, line in enumerate(mask):
        heights = np.where(line, heights + 1, 0)
        best = max(best, widest_under(heights.tolist(), row))
    return best[1]


def room_in(piece: NDArray[np.uint8], box: Box) -> tuple[Box, bool]:
    """The largest plain stretch of the box's background, inset a little, and True; the box
    itself, inset, and False when that stretch is too small to letter in."""
    background = np.median(piece.reshape(-1, 3), axis=0)
    plain = np.abs(piece.astype(np.int16) - background).max(axis=-1) <= CLEAN_NEAR
    top, left, bottom, right = largest_rectangle(plain)
    width, height = box.right - box.left, box.bottom - box.top
    roomy = (bottom - top) * (right - left) >= LEAST_ROOM * width * height
    if not roomy:
        top, left, bottom, right = 0, 0, height, width
    step = round(INSET_SHARE * min(bottom - top, right - left))
    left, top = left + step, top + step
    return Box(left, top, max(left + 1, right - step), max(top + 1, bottom - step)), roomy


def lettered(page: Image.Image, box: Box, text: str) -> Image.Image:
    """The piece of `page` under `box` with `text` in its plain space, black on light or white on
    dark; edged in the other only on a busy background, where no plain space was found."""
    done = page.crop(box.corners())
    piece = np.asarray(done)
    room, roomy = room_in(piece, box)
    light = float(np.median(piece.reshape(-1, 3), axis=0).mean()) > LIGHT
    ink, edge = (BLACK, WHITE) if light else (WHITE, BLACK)
    size, lines = fitted(text, room)
    step = round(size * LINE_SPACING)
    top = room.top + ((room.bottom - room.top) - step * len(lines)) // 2
    centre = (room.left + room.right) / 2
    pen = ImageDraw.Draw(done)
    for number, line in enumerate(lines):
        pen.text(
            (centre, top + number * step),
            line,
            font=font_at(size),
            fill=ink,
            anchor="ma",
            stroke_width=0 if roomy else max(1, round(OUTLINE_SHARE * size)),
            stroke_fill=edge,
        )
    return done
