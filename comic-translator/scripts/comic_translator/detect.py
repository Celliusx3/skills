"""Find the text on each page: pages unpacked, a text map over tiles, lines grown into blocks."""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from scipy import ndimage

from comic_translator.models import Session
from comic_translator.notes import Box

IMAGES = (".png", ".jpg", ".jpeg", ".webp")
ARCHIVES = (".zip", ".cbz")
TILE = 1024
OVERLAP = 128
STRIDE = 32
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
SPREAD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
TEXT_LIKELY = 0.3
LINE_SURE = 0.6
LEAST_LINE = 16
GROW = 1.5
LINE_GAP = 0.8
LIKE_HEIGHT = 1.6
ALIGNED = 1.0
MOSTLY_OVER = 0.67
INK = 100
PAPER_NEAR = 12
SHADE = 8

TextMap = NDArray[np.float32]
Stretches = NDArray[np.int32]


class DetectError(ValueError):
    """An input that holds no pages to translate."""


def unpacked(source: Path, pages: Path) -> list[Path]:
    """The pages of `source`, an image or an archive of images, copied into `pages` in order."""
    pages.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() in IMAGES:
        return [Path(shutil.copy(source, pages / source.name))]
    if source.suffix.lower() not in ARCHIVES:
        kinds = ", ".join(IMAGES + ARCHIVES)
        raise DetectError(f"{source.name} is not an image or an archive of images ({kinds})")
    copied = []
    with zipfile.ZipFile(source) as archive:
        names = sorted(n for n in archive.namelist() if Path(n).suffix.lower() in IMAGES)
        for name in names:
            target = pages / Path(name).name
            target.write_bytes(archive.read(name))
            copied.append(target)
    if not copied:
        raise DetectError(f"{source.name} holds no images")
    return copied


def tile_map(session: Session, tile: Image.Image) -> TextMap:
    """How likely each pixel of `tile` is text, from the text finder."""
    width, height = tile.size
    padded_w, padded_h = -(-width // STRIDE) * STRIDE, -(-height // STRIDE) * STRIDE
    bgr = np.asarray(tile, dtype=np.float32)[..., ::-1] / 255
    canvas = np.zeros((padded_h, padded_w, 3), dtype=np.float32)
    canvas[:height, :width] = (bgr - MEAN) / SPREAD
    likely = session.run(None, {"x": canvas.transpose(2, 0, 1)[None]})[0]
    return likely[0, 0, :height, :width].astype(np.float32)


def text_map(session: Session, page: Image.Image) -> TextMap:
    """The text map of a whole page, run TILE pixels at a time with OVERLAP between them."""
    width, height = page.size
    likely = np.zeros((height, width), dtype=np.float32)
    top = 0
    while True:
        bottom = min(height, top + TILE)
        tile = tile_map(session, page.crop((0, top, width, bottom)))
        likely[top:bottom] = np.maximum(likely[top:bottom], tile)
        if bottom == height:
            return likely
        top = bottom - OVERLAP


def grown(rows: slice, columns: slice, size: tuple[int, int]) -> Box:
    """A text line's band grown back to the line, as far as its area over its outline allows."""
    height, width = rows.stop - rows.start, columns.stop - columns.start
    step = round(GROW * width * height / (2 * (width + height)))
    page_w, page_h = size
    return Box(
        max(0, columns.start - step),
        max(0, rows.start - step),
        min(page_w, columns.stop + step),
        min(page_h, rows.stop + step),
    )


def line_boxes(likely: TextMap) -> list[Box]:
    """Each text line the map is sure of, grown to cover its letters."""
    labels, _ = ndimage.label(likely > TEXT_LIKELY)
    size = (likely.shape[1], likely.shape[0])
    lines = []
    for number, found in enumerate(ndimage.find_objects(labels), start=1):
        if found is None:
            continue
        rows, columns = found
        band = labels[found] == number
        if band.sum() < LEAST_LINE or likely[found][band].mean() < LINE_SURE:
            continue
        lines.append(grown(rows, columns, size))
    return lines


def stacked(upper: Box, lower: Box) -> bool:
    """Whether two lines are lines of one block: overlapping each other, as trailing dots do their
    word; or overlapping across, of like height, the gap between them small beside the shorter
    one, and in one column."""
    across = min(upper.right, lower.right) - max(upper.left, lower.left)
    gap = max(lower.top - upper.bottom, upper.top - lower.bottom)
    short, tall = sorted((upper.bottom - upper.top, lower.bottom - lower.top))
    if across > 0 and gap < 0:
        return True
    close = across > 0 and tall <= LIKE_HEIGHT * short and gap <= LINE_GAP * short
    return close and one_column(upper, lower, short)


def one_column(upper: Box, lower: Box, short: int) -> bool:
    """Whether two lines read as one column: sharing a left edge, a right edge or a middle, or
    the narrower mostly over the wider, while a balloon's next lobe steps aside."""
    middle = abs(upper.left + upper.right - lower.left - lower.right) / 2
    offset = min(abs(upper.left - lower.left), abs(upper.right - lower.right), middle)
    across = min(upper.right, lower.right) - max(upper.left, lower.left)
    narrow = min(upper.right - upper.left, lower.right - lower.left)
    return offset <= ALIGNED * short or across >= MOSTLY_OVER * narrow


def joined(boxes: list[Box]) -> Box:
    return Box(
        min(b.left for b in boxes),
        min(b.top for b in boxes),
        max(b.right for b in boxes),
        max(b.bottom for b in boxes),
    )


def groups(lines: list[Box]) -> list[list[Box]]:
    """The lines gathered into groups, two lines sharing a group whenever they stack."""
    group_of = list(range(len(lines)))

    def root(n: int) -> int:
        while group_of[n] != n:
            n = group_of[n]
        return n

    for i, first in enumerate(lines):
        for k in range(i + 1, len(lines)):
            if stacked(first, lines[k]):
                group_of[root(k)] = root(i)
    gathered: dict[int, list[Box]] = {}
    for n, line in enumerate(lines):
        gathered.setdefault(root(n), []).append(line)
    return list(gathered.values())


def overlapping(one: Box, other: Box) -> bool:
    across = min(one.right, other.right) - max(one.left, other.left)
    down = min(one.bottom, other.bottom) - max(one.top, other.top)
    return across > 0 and down > 0


def merged(boxes: list[Box]) -> list[Box]:
    """The boxes with any two that overlap joined into one, until none overlap, so two entries
    never erase and letter over each other."""
    result = list(boxes)
    while True:
        pair = next(
            (
                (i, k)
                for i in range(len(result))
                for k in range(i + 1, len(result))
                if overlapping(result[i], result[k])
            ),
            None,
        )
        if pair is None:
            return result
        both = joined([result[n] for n in pair])
        result = [box for n, box in enumerate(result) if n not in pair] + [both]


@dataclass(frozen=True)
class Paper:
    """A page's stretches of paper and ink, numbered, and its colours."""

    stretches: Stretches
    colours: NDArray[np.uint8]


def papers(page: Image.Image) -> Paper:
    """Each pixel's stretch of the page: touching pixels alike in being paper or ink share a
    number, so a bubble's outline parts its paper from the next bubble's."""
    ink = np.asarray(page.convert("L")) < INK
    paper, count = ndimage.label(~ink)
    dark, _ = ndimage.label(ink)
    stretches = np.where(ink, dark + count, paper).astype(np.int32)
    return Paper(stretches, np.asarray(page.convert("RGB")))


def paper_of(line: Box, paper: Paper) -> int:
    """The stretch covering most of `line`, as the bubble or caption it is printed in does."""
    under = paper.stretches[line.top : line.bottom, line.left : line.right]
    return int(np.bincount(under.ravel()).argmax())


def colour_of(line: Box, paper: Paper) -> NDArray[np.int16]:
    """The commonest colour round `line`, counted in steps of SHADE, as its paper's."""
    pixels = paper.colours[line.top : line.bottom, line.left : line.right].reshape(-1, 3)
    shades, counts = np.unique(pixels // SHADE * SHADE, axis=0, return_counts=True)
    return shades[counts.argmax()].astype(np.int16)


def on_sheets(lines: list[Box], paper: Paper) -> dict[int, list[list[Box]]]:
    """The lines sorted onto the sheets they are printed on, by stretch: one stretch in one
    colour, so a white bubble touching a pink one is two sheets though no outline parts them."""
    found: dict[int, list[tuple[NDArray[np.int16], list[Box]]]] = {}
    for line in lines:
        colour = colour_of(line, paper)
        kept = found.setdefault(paper_of(line, paper), [])
        sheet = next((s for near, s in kept if np.abs(near - colour).max() <= PAPER_NEAR), None)
        if sheet is None:
            kept.append((colour, [line]))
        else:
            sheet.append(line)
    return {stretch: [sheet for _, sheet in kept] for stretch, kept in found.items()}


def blocks(lines: list[Box], paper: Paper) -> list[Box]:
    """Each group of stacked lines on one sheet of paper as one block, overlapping blocks in one
    stretch joined, in reading order; lines in two bubbles never share a block."""
    found = [
        block
        for kept in on_sheets(lines, paper).values()
        for block in merged([joined(group) for sheet in kept for group in groups(sheet)])
    ]
    return sorted(found, key=lambda box: (box.top, box.left))


def held_lines(box: Box, lines: list[Box]) -> list[Box]:
    """The lines whose middle lies in `box`."""
    return [
        line
        for line in lines
        if box.left <= (line.left + line.right) / 2 <= box.right
        and box.top <= (line.top + line.bottom) / 2 <= box.bottom
    ]


def letters_held(lines: list[Box]) -> float:
    """About how many letters `lines` hold, a letter about as wide as its line is high."""
    return sum((line.right - line.left) / (line.bottom - line.top) for line in lines)


def page_blocks(session: Session, page: Image.Image) -> tuple[list[Box], Image.Image]:
    """The page's blocks of text, and its text map as a grey image to keep beside the notes."""
    likely = text_map(session, page)
    found = blocks(line_boxes(likely), papers(page))
    return found, Image.fromarray((likely.clip(0, 1) * 255).astype(np.uint8))
