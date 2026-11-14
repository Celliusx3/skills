"""Erase an entry's text: the pixels in its box unlike its paper, filled flat or redrawn."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from scipy import ndimage

from comic_translator.models import Session
from comic_translator.notes import Box

RING = 4
RIM = 3
KINDS = 8
PAPER_SHARE = 0.25
MOST = 0.5
AWAY_LEAST = 0.02
TEXT_LIKELY = 77
NEAR = 40
SPECK_SHARE = 0.01
LETTER_SHARE = 0.5
PAD_SHARE = 0.15
EVEN_SHARE = 0.85
GHOST = 90
GHOST_REACH = 2
SMALL_PIECE = 0.1
REACH = 0.15
AWAY = 12
MARGIN = 2.0
SEEN_GROW = 2
INK = 128
TALL = 3
SIDE = 512

Mask = NDArray[np.bool_]
Pixels = NDArray[np.int16]


@dataclass(frozen=True)
class Patch:
    """A changed piece of a page, and where its top-left corner goes on the page."""

    image: Image.Image
    at: tuple[int, int]


def frame_of(box: Box, size: tuple[int, int], grow: int) -> Box:
    width, height = size
    return Box(
        max(0, box.left - grow),
        max(0, box.top - grow),
        min(width, box.right + grow),
        min(height, box.bottom + grow),
    )


def inside(frame: Box, box: Box) -> Mask:
    mask = np.zeros((frame.bottom - frame.top, frame.right - frame.left), dtype=np.bool_)
    mask[
        box.top - frame.top : box.bottom - frame.top, box.left - frame.left : box.right - frame.left
    ] = True
    return mask


def distance(pixels: Pixels, colour: NDArray[np.int16]) -> NDArray[np.int16]:
    return np.abs(pixels - colour).max(axis=-1)


def paper_colours(
    pixels: Pixels, box_mask: Mask, near: Mask | None = None
) -> list[NDArray[np.int16]]:
    """What the box's text is printed on: where the text finder saw text, the colours covering
    PAPER_SHARE of the strip just past it in the box, as a burst behind the letters is, while a
    panel further off is not; else the colours covering PAPER_SHARE of the box's inner edge,
    and any covering MOST of the whole box, as a bubble does when the box reaches past it."""
    if near is not None:
        strip = ndimage.binary_dilation(near, iterations=AWAY) & ~near & box_mask
        if strip.sum() >= AWAY_LEAST * box_mask.sum():
            return shares_of(pixels[strip], PAPER_SHARE)
    rim = box_mask & ~ndimage.binary_erosion(box_mask, iterations=RIM)
    return [*shares_of(pixels[rim], PAPER_SHARE), *shares_of(pixels[box_mask], MOST)]


def shares_of(pixels: Pixels, least: float) -> list[NDArray[np.int16]]:
    """The colours of `pixels` making up at least `least` of them, counting every colour within
    NEAR of one as that colour, so a paper split over shades of white still counts whole."""
    flat = pixels.astype(np.uint8).reshape(1, -1, 3)
    colours = Image.fromarray(flat).quantize(colors=KINDS)
    palette = colours.getpalette() or []
    counted = [
        (count, np.array(palette[3 * index : 3 * index + 3], dtype=np.int16))
        for count, index in colours.getcolors() or []
    ]
    return [
        colour
        for _, colour in counted
        if sum(n for n, other in counted if distance(other, colour) <= NEAR)
        >= least * flat.shape[1]
    ]


def pieces(mask: Mask) -> tuple[NDArray[np.int32], NDArray[np.float64]]:
    labels, count = ndimage.label(mask, structure=np.ones((3, 3)))
    return labels, ndimage.sum_labels(mask, labels, np.arange(1, count + 1))


def letter_height(labels: NDArray[np.int32], running_off: NDArray[np.int32]) -> int:
    """The typical height of the tallest pieces not running off, as a letter's, while a border or
    a figure running past the margin is none; 1 when there are none."""
    heights = [
        rows.stop - rows.start
        for label, (rows, _) in enumerate(ndimage.find_objects(labels) or [], start=1)
        if label not in running_off
    ]
    if not heights:
        return 1
    tall = [h for h in heights if h >= LETTER_SHARE * max(heights)]
    return round(float(np.median(tall)))


def without_specks(mask: Mask, edge: Mask) -> Mask:
    """`mask` without pieces tiny beside one of its letters, as noise is; accents and dots stay."""
    labels, sizes = pieces(mask)
    least = SPECK_SHARE * letter_height(labels, np.unique(labels[edge & mask])) ** 2
    return np.isin(labels, np.flatnonzero(sizes >= least) + 1) if sizes.size else mask


def seen_text(likely: NDArray[np.uint8], box_mask: Mask) -> Mask:
    """Where the text finder saw text in the box: a thin band along each line."""
    return (likely >= TEXT_LIKELY) & ndimage.binary_dilation(box_mask, iterations=RIM)


def near_text(likely: NDArray[np.uint8], box_mask: Mask) -> Mask:
    """Where the text finder saw text in the box, grown by the band's own thickness to take in
    whole letters; everywhere when it saw none there, as in a box the model added."""
    band = seen_text(likely, box_mask)
    if not band.any():
        return np.ones_like(box_mask)
    thickness = 2 * float(ndimage.distance_transform_edt(band).max())
    return ndimage.distance_transform_edt(~band) <= thickness


def paper_in(pixels: Pixels, margin: Mask, box_mask: Mask, near: Mask | None) -> Mask:
    """The paper round the text: each paper colour's large pieces and those running off the
    margin, as a panel does; a small piece of it alone, as a letter's own outline, is text."""
    edge = margin & ~ndimage.binary_erosion(margin)
    paper = np.zeros_like(margin)
    for colour in paper_colours(pixels, box_mask, near):
        labels, sizes = pieces(margin & (distance(pixels, colour) <= NEAR))
        large = np.flatnonzero(sizes >= SMALL_PIECE * box_mask.sum()) + 1
        running_off = np.setdiff1d(labels[edge], [0])
        paper |= np.isin(labels, np.union1d(large, running_off))
    return paper


def text_in(
    pixels: Pixels, box_mask: Mask, line_height: int, near: Mask | None = None
) -> tuple[Mask, Mask, Mask]:
    """The letters: small pieces unlike the paper lying wholly within REACH of the box's height
    past its edge, as letters, accents and a `¡` a box misses are; the rest of the box unlike
    its paper, as a halo is; and the pieces running past the margin, as a bubble's outline
    joined to the panel round it is, with any letter touching it."""
    reach = max(RING, round(REACH * line_height))
    margin = ndimage.binary_dilation(box_mask, iterations=reach)
    edge = margin & ~ndimage.binary_erosion(margin)
    far = without_specks(margin & ~paper_in(pixels, margin, box_mask, near), edge)
    labels, sizes = pieces(far)
    small = np.flatnonzero(sizes <= SMALL_PIECE * box_mask.sum()) + 1
    running_off = np.unique(labels[edge])
    letters = np.isin(labels, np.setdiff1d(small, running_off))
    letters |= inked_letters(far & ink_of(pixels, paper_colours(pixels, box_mask, near)), edge)
    running = np.isin(labels, np.setdiff1d(running_off, [0])) & ~letters
    return letters, far & box_mask & ~letters & ~running, running


def ink_of(pixels: Pixels, colours: list[NDArray[np.int16]]) -> Mask:
    """The pixels further than INK from every paper colour, as letters and outlines are, while a
    caption's own tint is not."""
    if not colours:
        return np.ones(pixels.shape[:2], dtype=np.bool_)
    return np.min([distance(pixels, colour) for colour in colours], axis=0) > INK


def inked_letters(ink: Mask, edge: Mask) -> Mask:
    """The pieces of ink no taller than TALL typical ones and not running past the margin, as the
    letters on a caption's tint are, while an outline round a bubble is far taller."""
    labels, _ = pieces(ink)
    found = ndimage.find_objects(labels) or []
    heights = np.array([rows.stop - rows.start for rows, _ in found])
    if not heights.size:
        return ink
    short = np.flatnonzero(heights <= TALL * np.median(heights)) + 1
    return np.isin(labels, np.setdiff1d(short, labels[edge]))


def text_of(
    pixels: Pixels, box_mask: Mask, height: int, likely: NDArray[np.uint8] | None
) -> tuple[Mask, Mask]:
    """The text to take out, and the outlines and panels to keep: without the text finder, every
    letter and the rest of the box; with it, the letters reaching near its lines, the rest near
    them, and of what runs past the margin only what lies on its lines, as a letter touching an
    outline does."""
    if likely is None:
        letters, rest, running = text_in(pixels, box_mask, height)
        return letters | rest, running
    near = near_text(likely, box_mask)
    letters, rest, running = text_in(pixels, box_mask, height, near)
    on_lines = running & ndimage.binary_dilation(seen_text(likely, box_mask), iterations=SEEN_GROW)
    return touching(letters, near) | (rest & near) | on_lines, running & ~on_lines


def touching(pieces_of: Mask, near: Mask) -> Mask:
    """The whole of every piece of `pieces_of` that reaches into `near`."""
    labels, _ = pieces(pieces_of)
    return np.isin(labels, np.setdiff1d(labels[near], [0]))


def pad_of(text: Mask) -> int:
    """PAD_SHARE of a typical letter's height: how far the hole reaches past the letters."""
    labels, sizes = pieces(text)
    heights = [rows.stop - rows.start for rows, _ in ndimage.find_objects(labels) or []]
    return max(1, round(PAD_SHARE * float(np.median(heights)))) if heights else 1


def commonest(pixels: Pixels) -> NDArray[np.int16]:
    colours, counts = np.unique(pixels, axis=0, return_counts=True)
    return colours[counts.argmax()]


def flat_colour(pixels: Pixels, hole: Mask, box_mask: Mask) -> str | None:
    """When the line just outside the hole is even, the paper's commonest exact colour, taken in
    the box a little away from the letters, where they bleed no tint into it and the page round
    the bubble is not; else None. The line is even when EVEN_SHARE of it is near one colour, so
    a note or an outline touching it is no bar."""
    edge = ndimage.binary_dilation(hole) & ~hole
    if not edge.any():
        return None
    near = np.median(pixels[edge], axis=0).astype(np.int16)
    if float((distance(pixels[edge], near) <= NEAR).mean()) < EVEN_SHARE:
        return None
    away = box_mask & ndimage.binary_dilation(hole, iterations=AWAY)
    away &= ~ndimage.binary_dilation(hole, iterations=RING)
    paper = away & (distance(pixels, near) <= NEAR)
    red, green, blue = (int(v) for v in commonest(pixels[paper] if paper.any() else pixels[edge]))
    return f"#{red:02x}{green:02x}{blue:02x}"


def redrawn(crop: NDArray[np.uint8], hole: Mask, session: Session) -> NDArray[np.uint8]:
    """The crop with the hole drawn again by the inpainting model from what lies round it; the
    model sees the crop at SIDE pixels square, and only the hole is taken back from it."""
    height, width = hole.shape
    image = Image.fromarray(crop).resize((SIDE, SIDE), Image.Resampling.BICUBIC)
    mask = Image.fromarray(hole).resize((SIDE, SIDE), Image.Resampling.NEAREST)
    feeds = {
        "image": np.asarray(image, dtype=np.float32).transpose(2, 0, 1)[None] / 255,
        "mask": np.asarray(mask, dtype=np.float32)[None, None],
    }
    drawn = session.run(None, feeds)[0][0].transpose(1, 2, 0).clip(0, 255).astype(np.uint8)
    back = np.asarray(Image.fromarray(drawn).resize((width, height), Image.Resampling.BICUBIC))
    out = crop.copy()
    out[hole] = back[hole]
    return out


def erased(
    page: Image.Image,
    box: Box,
    inpainter: Callable[[], Session],
    likely: Image.Image | None = None,
) -> Patch:
    """The piece of `page` round `box` with its text, near where the text finder saw it, taken
    out."""
    height = box.bottom - box.top
    frame = frame_of(box, page.size, round(MARGIN * height))
    crop = np.asarray(page.crop((frame.left, frame.top, frame.right, frame.bottom)))
    pixels = crop.astype(np.int16)
    box_mask = inside(frame, box)
    corners = (frame.left, frame.top, frame.right, frame.bottom)
    seen = None if likely is None else np.asarray(likely.crop(corners))
    text, kept = text_of(pixels, box_mask, height, seen)
    pad = pad_of(text)
    hole = ndimage.binary_dilation(text, iterations=pad) & ndimage.binary_dilation(
        box_mask | text, iterations=RING
    )
    hole &= ~kept
    colour = flat_colour(pixels, hole, box_mask)
    out = crop.copy()
    if colour is not None:
        paint = np.array(Image.new("RGB", (1, 1), colour)).reshape(3).astype(np.int16)
        round_letters = ndimage.binary_dilation(hole, iterations=GHOST_REACH * pad)
        ghosts = round_letters & ndimage.binary_dilation(box_mask, iterations=RING)
        ghosts &= distance(pixels, paint) <= GHOST
        out[hole | ghosts] = paint
    else:
        soft_edges = ndimage.binary_dilation(hole, iterations=pad) & ndimage.binary_dilation(
            box_mask | text, iterations=RING + pad
        )
        out = redrawn(crop, soft_edges & ~kept, inpainter())
    return Patch(Image.fromarray(out), (frame.left, frame.top))
