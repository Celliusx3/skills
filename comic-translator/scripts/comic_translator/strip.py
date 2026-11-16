"""A webtoon chapter's strips joined and cut again only in blank rows, so that no bubble is
split between two pages; and the translated pages cut back at the strips' own edges."""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

STRIP_RATIO = 1.8
BLANK_SPREAD = 10
MIN_GAP = 8
LAYOUT = "strips.json"
JPEG_QUALITY = 95


@dataclass(frozen=True)
class Band:
    """Rows `top` to `bottom` of the joined strip, kept in the image `path`."""

    path: Path
    top: int
    bottom: int


def image_of(path: Path) -> Image.Image:
    with Image.open(path) as opened:
        return opened.convert("RGB")


def is_strip(sizes: Sequence[tuple[int, int]]) -> bool:
    """Whether pages of these sizes are one tall strip cut in pieces: 2 or more, all one width,
    and the middle one by height far taller than wide, as a few short pieces do not change."""
    widths = {width for width, _ in sizes}
    tall = len(sizes) >= 2 and np.median([h for _, h in sizes]) >= STRIP_RATIO * sizes[0][0]
    return len(widths) == 1 and bool(tall)


def blank_rows(image: Image.Image) -> NDArray[np.bool_]:
    """For each row of `image`, whether it is one flat colour, with nothing drawn across it."""
    pixels = np.asarray(image.convert("RGB"), dtype=np.int16)
    spread = pixels.max(axis=1) - pixels.min(axis=1)
    return spread.max(axis=1) <= BLANK_SPREAD


def gap_middles(blank: NDArray[np.bool_]) -> NDArray[np.int64]:
    """The middle row of every run of at least MIN_GAP blank rows."""
    edges = np.diff(np.concatenate(([0], blank.astype(np.int8), [0])))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    long_enough = ends - starts >= MIN_GAP
    return (starts[long_enough] + ends[long_enough]) // 2


def cut_rows(blank: NDArray[np.bool_], target: int) -> list[int]:
    """Rows to cut the joined strip at, each in a blank gap, as near `target` rows apart as the
    gaps allow; a stretch with no gap is left whole."""
    gaps, total = gap_middles(blank), len(blank)
    cuts, start = [], 0
    while total - start > target * 3 // 2:
        later = gaps[gaps > start + target // 2]
        if not later.size:
            break
        near = later[later <= start + 2 * target]
        start = int(near[np.argmin(abs(near - start - target))] if near.size else later[0])
        cuts.append(start)
    return cuts


def bands_of(paths: Sequence[Path], heights: Sequence[int]) -> list[Band]:
    """Each of `paths` as the band of the joined strip it holds, top to bottom."""
    tops = np.concatenate(([0], np.cumsum(heights)))
    return [Band(p, int(tops[i]), int(tops[i + 1])) for i, p in enumerate(paths)]


def joined(bands: Sequence[Band], top: int, bottom: int, width: int) -> Image.Image:
    """Rows `top` to `bottom` of the strip the `bands` make up, as one image."""
    out = Image.new("RGB", (width, bottom - top), "white")
    for band in bands:
        if band.bottom > top and band.top < bottom:
            first, last = max(top, band.top), min(bottom, band.bottom)
            piece = image_of(band.path).crop((0, first - band.top, width, last - band.top))
            out.paste(piece, (0, first - top))
    return out


def saved_as(image: Image.Image, path: Path) -> Path:
    if path.suffix.lower() in (".jpg", ".jpeg"):
        image.save(path, quality=JPEG_QUALITY)
    else:
        image.save(path)
    return path


def strip_run(sizes: Sequence[tuple[int, int]]) -> tuple[int, int] | None:
    """The longest run of pages of the chapter's most common width, as first and past-last
    index, when it is a strip; images of another width before or after it, such as a cover or a
    banner, are left out of it."""
    widths = [w for w, _ in sizes]
    common = max(set(widths), key=widths.count)
    best, start = (0, 0), None
    for index, width in enumerate([*widths, -1]):
        if width == common and start is None:
            start = index
        elif width != common and start is not None:
            best = max(best, (start, index), key=lambda run: run[1] - run[0])
            start = None
    first, past = best
    return best if is_strip(sizes[first:past]) else None


def laid_out(work: Path, sources: Sequence[Path]) -> list[Path]:
    """The pages to work on, in `work`/pages: a strip cut again in blank rows, with its layout
    kept for pack, and any image before or after it as a page of its own; any other chapter's
    pages as they are."""
    pages = work / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    sizes = [image_of(p).size for p in sources]
    run = strip_run(sizes)
    if run is None:
        return [Path(shutil.copy(p, pages / p.name)) for p in sources]
    first, past = run
    strip, heights = sources[first:past], [h for _, h in sizes[first:past]]
    blank = np.concatenate([blank_rows(image_of(p)) for p in strip])
    rows = [0, *cut_rows(blank, int(np.median(heights))), len(blank)]
    bands = bands_of(strip, heights)
    entries: list[dict[str, object]] = [{"extra": p.name} for p in sources[:first]]
    entries += [{"top": t, "bottom": b} for t, b in zip(rows[:-1], rows[1:], strict=True)]
    entries += [{"extra": p.name} for p in sources[past:]]
    by_name = {p.name: p for p in sources}
    made, layout_pages = [], []
    for number, entry in enumerate(entries, start=1):
        if "extra" in entry:
            source = by_name[str(entry["extra"])]
            path = Path(shutil.copy(source, pages / f"{number:03d}{source.suffix}"))
            layout_pages.append({"name": path.name, "extra": source.name})
        else:
            top, bottom = int(entry["top"]), int(entry["bottom"])
            image = joined(bands, top, bottom, sizes[first][0])
            path = saved_as(image, pages / f"{number:03d}{strip[0].suffix}")
            layout_pages.append({"name": path.name, "height": bottom - top})
        made.append(path)
    strips = [{"name": p.name, "height": h} for p, h in zip(strip, heights, strict=True)]
    (work / LAYOUT).write_text(json.dumps({"strips": strips, "pages": layout_pages}))
    return made


def cut_back(work: Path, chosen: Sequence[Path]) -> list[tuple[str, Image.Image]]:
    """The original files, by name, cut from `chosen`, one image for each page of the layout:
    a page's translation, or the page as it is; the strip cut back at its own edges, any image
    before or after it as it is."""
    layout = json.loads((work / LAYOUT).read_text())
    in_strip = [
        (path, page)
        for path, page in zip(chosen, layout["pages"], strict=True)
        if "extra" not in page
    ]
    width = image_of(in_strip[0][0]).size[0]
    bands = bands_of([path for path, _ in in_strip], [page["height"] for _, page in in_strip])
    edges = bands_of(
        [Path(s["name"]) for s in layout["strips"]], [s["height"] for s in layout["strips"]]
    )
    strips = [(edge.path.name, joined(bands, edge.top, edge.bottom, width)) for edge in edges]
    out: list[tuple[str, Image.Image]] = []
    for path, page in zip(chosen, layout["pages"], strict=True):
        if "extra" in page:
            out.append((page["extra"], image_of(path)))
        elif strips:
            out.extend(strips)
            strips = []
    return out
