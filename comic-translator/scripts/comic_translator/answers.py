"""A page's saved answer turned into its notes: kept boxes translated, the others deleted, and
what needs a closer look named."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from comic_translator.batch import DRAFTS, answer_of

Raw = dict[str, object]

LEFT_AS_DRAWN = frozenset({"drawn_sound", "sign", "title", "no_text"})
DRAWN_SOUND = "drawn_sound"
RING = 8
WIDEST_BUBBLE_SHARE = 0.6
PAPER_SPREAD = 45


def ring_colour(pixels: np.ndarray, box: Raw) -> np.ndarray:
    """The middle colour of the page in a thin ring round `box`."""
    height, width = pixels.shape[:2]
    left, top, right, bottom = (box[edge] for edge in ("left", "top", "right", "bottom"))
    outer = pixels[
        max(0, top - RING) : min(height, bottom + RING),
        max(0, left - RING) : min(width, right + RING),
    ]
    inside = np.zeros(outer.shape[:2], dtype=bool)
    inside[
        top - max(0, top - RING) : bottom - max(0, top - RING),
        left - max(0, left - RING) : right - max(0, left - RING),
    ] = True
    return np.median(outer[~inside], axis=0)


def in_closed_bubble(pixels: np.ndarray, box: Raw) -> bool:
    """Whether the paper round `box` is fenced in by an outline, as inside a bubble, rather than
    running out to the page's edge, as a gutter does round a sound drawn on the art."""
    if box["right"] - box["left"] > WIDEST_BUBBLE_SHARE * pixels.shape[1]:
        return False
    near = np.abs(pixels - ring_colour(pixels, box)).max(axis=2) <= PAPER_SPREAD
    labels, _ = ndimage.label(near)
    height, width = labels.shape
    left, top, right, bottom = (box[edge] for edge in ("left", "top", "right", "bottom"))
    ring = labels[
        max(0, top - RING) : min(height, bottom + RING),
        max(0, left - RING) : min(width, right + RING),
    ]
    found, counts = np.unique(ring[ring > 0], return_counts=True)
    if not found.size:
        return False
    paper = found[np.argmax(counts)]
    edges = np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1]))
    return paper not in set(np.unique(edges))


def boxes_by_id(answer: object) -> dict[int, Raw]:
    """The answer's boxes by id, leaving out any that are not a box with a whole-number id."""
    boxes = answer.get("boxes") if isinstance(answer, dict) else None
    if not isinstance(boxes, list):
        return {}
    return {
        box["id"]: box for box in boxes if isinstance(box, dict) and isinstance(box.get("id"), int)
    }


def entry_answered(entry: Raw, box: Raw | None, in_bubble: bool) -> tuple[Raw | None, list[str]]:
    """`entry` as `box` answers it, None when it is not kept, and what to look at again; a
    sound called drawn but `in_bubble` is kept and translated."""
    number = entry["id"]
    if box is None:
        return entry, [f"no answer for box {number}"]
    kind = box.get("kind")
    if kind in LEFT_AS_DRAWN and not (kind == DRAWN_SOUND and in_bubble):
        return None, []
    original, translation = box.get("original"), box.get("translation")
    if not isinstance(original, str) or not isinstance(translation, str) or not translation.strip():
        return entry, [f"box {number} has no translation"]
    flags = [f"box {number} is unsure"] if box.get("unsure") is True else []
    return {**entry, "original": original, "translation": translation}, flags


def answered_notes(
    entries: Sequence[Raw], answer: object, in_bubbles: frozenset[int]
) -> tuple[list[Raw], list[str]]:
    """The notes `answer` makes of `entries`, those in `in_bubbles` sitting inside a bubble, and
    what to look at again on the page."""
    if answer is None:
        return list(entries), ["no answer saved"]
    by_id = boxes_by_id(answer)
    kept, flags = [], []
    for entry in entries:
        result, found = entry_answered(entry, by_id.get(entry["id"]), entry["id"] in in_bubbles)
        flags.extend(found)
        if result is not None:
            kept.append(result)
    missed = answer.get("missed") if isinstance(answer, dict) else None
    if isinstance(missed, str) and missed.strip():
        flags.append(f"missed: {missed.strip()}")
    return kept, flags


def applied(work: Path, pages: Sequence[str]) -> Mapping[str, object]:
    """Each page's saved answer written into its notes; the pages that need a closer look."""
    flagged: dict[str, list[str]] = {}
    for page in pages:
        path = work / "notes" / f"{page}.json"
        entries = json.loads(path.read_text())
        notes, flags = answered_notes(
            entries, answer_of(work / DRAFTS / f"{page}.json"), in_bubbles_of(work, page, entries)
        )
        path.write_text(json.dumps(notes, ensure_ascii=False, indent=1))
        if flags:
            flagged[page] = flags
    return {"applied": len(pages), "flagged": flagged}


def in_bubbles_of(work: Path, page: str, entries: Sequence[Raw]) -> frozenset[int]:
    """The ids of `page`'s entries whose boxes sit inside a closed bubble."""
    found = sorted((work / "pages").glob(f"{page}.*"))
    if not found:
        return frozenset()
    with Image.open(found[0]) as opened:
        pixels = np.asarray(opened.convert("RGB"), dtype=np.int16)
    return frozenset(e["id"] for e in entries if in_closed_bubble(pixels, e["box"]))
