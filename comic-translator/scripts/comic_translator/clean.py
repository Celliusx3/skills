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
EVEN_EDGE = 15.0
GHOST = 90
GHOST_REACH = 2
SMALL_PIECE = 0.1
REACH = 0.15
AWAY = 12
MARGIN = 2.0
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


def letter_height(labels: NDArray[np.int32]) -> int:
    """The typical height of the tallest pieces, as a letter's; 1 when there are none."""
    heights = [rows.stop - rows.start for rows, _ in ndimage.find_objects(labels) or []]
    if not heights:
        return 1
    tall = [h for h in heights if h >= LETTER_SHARE * max(heights)]
    return round(float(np.median(tall)))


def without_specks(mask: Mask) -> Mask:
    """`mask` without pieces tiny beside one of its letters, as noise is; accents and dots stay."""
    labels, sizes = pieces(mask)
    least = SPECK_SHARE * letter_height(labels) ** 2
    return np.isin(labels, np.flatnonzero(sizes >= least) + 1) if sizes.size else mask


def near_text(likely: NDArray[np.uint8], box_mask: Mask) -> Mask:
    """Where the text finder saw text in the box, grown by the band's own thickness to take in
    whole letters; everywhere when it saw none there, as in a box the model added."""
    band = (likely >= TEXT_LIKELY) & ndimage.binary_dilation(box_mask, iterations=RIM)
    if not band.any():
        return np.ones_like(box_mask)
    thickness = 2 * float(ndimage.distance_transform_edt(band).max())
    return ndimage.distance_transform_edt(~band) <= thickness


def kept_near(text: Mask, allowed: Mask, box_mask: Mask) -> Mask:
    """Every small piece of text, as letters, accents and dots are; a large piece, as a burst's
    body behind them, only near where the text finder saw text."""
    labels, sizes = pieces(text)
    small = np.flatnonzero(sizes <= SMALL_PIECE * box_mask.sum()) + 1
    return (text & allowed) | np.isin(labels, small)


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


def text_in(pixels: Pixels, box_mask: Mask, line_height: int, near: Mask | None = None) -> Mask:
    """The pixels in the box unlike its paper: letters, any halo, any outline the box takes in;
    and, within REACH of its height past its edge, small pieces wholly there, as accents and a
    `¡` a box misses."""
    reach = max(RING, round(REACH * line_height))
    margin = ndimage.binary_dilation(box_mask, iterations=reach)
    far = without_specks(margin & ~paper_in(pixels, margin, box_mask, near))
    labels, sizes = pieces(far)
    small = np.flatnonzero(sizes <= SMALL_PIECE * box_mask.sum()) + 1
    reaching_out = np.unique(labels[margin & ~ndimage.binary_erosion(margin)])
    return (far & box_mask) | np.isin(labels, np.setdiff1d(small, reaching_out))


def pad_of(text: Mask) -> int:
    """PAD_SHARE of a typical letter's height: how far the hole reaches past the letters."""
    labels, sizes = pieces(text)
    heights = [rows.stop - rows.start for rows, _ in ndimage.find_objects(labels) or []]
    return max(1, round(PAD_SHARE * float(np.median(heights)))) if heights else 1


def commonest(pixels: Pixels) -> NDArray[np.int16]:
    colours, counts = np.unique(pixels, axis=0, return_counts=True)
    return colours[counts.argmax()]


def flat_colour(pixels: Pixels, hole: Mask, box_mask: Mask) -> str | None:
    """When the line just outside the hole is even, the paper's commonest exact colour, taken a
    little away from the box where letters bleed no tint into it; else None."""
    edge = ndimage.binary_dilation(hole) & ~hole
    if not edge.any() or float(pixels[edge].std(axis=0).max()) > EVEN_EDGE:
        return None
    near = np.median(pixels[edge], axis=0).astype(np.int16)
    away = ndimage.binary_dilation(box_mask, iterations=AWAY) & ~ndimage.binary_dilation(
        box_mask, iterations=RING
    )
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
    near = None
    if likely is not None:
        corners = (frame.left, frame.top, frame.right, frame.bottom)
        near = near_text(np.asarray(likely.crop(corners)), box_mask)
    text = text_in(pixels, box_mask, height, near)
    if near is not None:
        text = kept_near(text, near, box_mask)
    pad = pad_of(text)
    hole = ndimage.binary_dilation(text, iterations=pad) & ndimage.binary_dilation(
        box_mask | text, iterations=RING
    )
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
        out = redrawn(crop, soft_edges, inpainter())
    return Patch(Image.fromarray(out), (frame.left, frame.top))
