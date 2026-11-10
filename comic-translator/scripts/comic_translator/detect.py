"""Find the text on each page: pages unpacked, a text map over tiles, lines grown into blocks."""

from __future__ import annotations

import shutil
import zipfile
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

TextMap = NDArray[np.float32]


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
    word; or overlapping across, of like height, and the gap between them small beside the
    shorter one."""
    across = min(upper.right, lower.right) - max(upper.left, lower.left)
    gap = max(lower.top - upper.bottom, upper.top - lower.bottom)
    short, tall = sorted((upper.bottom - upper.top, lower.bottom - lower.top))
    if across > 0 and gap < 0:
        return True
    return across > 0 and tall <= LIKE_HEIGHT * short and gap <= LINE_GAP * short


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


def blocks(lines: list[Box]) -> list[Box]:
    """Each group of stacked lines as one block, overlapping blocks joined, in reading order."""
    grouped = [joined(group) for group in groups(lines)]
    return sorted(merged(grouped), key=lambda box: (box.top, box.left))


def page_blocks(session: Session, page: Image.Image) -> tuple[list[Box], Image.Image]:
    """The page's blocks of text, and its text map as a grey image to keep beside the notes."""
    likely = text_map(session, page)
    return blocks(line_boxes(likely)), Image.fromarray((likely.clip(0, 1) * 255).astype(np.uint8))
