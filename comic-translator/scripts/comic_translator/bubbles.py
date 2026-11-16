"""Boxes that are lines of one paragraph, stacked with almost no gap, joined into one box, so
that a bubble's lines are read, translated and lettered together."""

from __future__ import annotations

from collections.abc import Sequence

from comic_translator.notes import Box

LINE_GAP = 24
SIDEWAYS_SHARE = 0.4


def stacked(upper: Box, lower: Box) -> bool:
    """Whether `lower` reads on from `upper`: starting at most LINE_GAP below it, and sharing at
    least SIDEWAYS_SHARE of the narrower one's width."""
    gap = lower.top - upper.bottom
    shared = min(upper.right, lower.right) - max(upper.left, lower.left)
    narrower = min(upper.right - upper.left, lower.right - lower.left)
    return -LINE_GAP <= gap <= LINE_GAP and shared >= SIDEWAYS_SHARE * narrower


def joined(one: Box, other: Box) -> Box:
    return Box(
        min(one.left, other.left),
        min(one.top, other.top),
        max(one.right, other.right),
        max(one.bottom, other.bottom),
    )


def by_paragraph(boxes: Sequence[Box]) -> list[Box]:
    """`boxes` with every run of stacked lines joined into one box, top to bottom."""
    found = sorted(boxes, key=lambda b: (b.top, b.left))
    changed = True
    while changed:
        changed = False
        for i, upper in enumerate(found):
            for j in range(i + 1, len(found)):
                if stacked(upper, found[j]):
                    found[i] = joined(upper, found.pop(j))
                    changed = True
                    break
            if changed:
                break
    return sorted(found, key=lambda b: (b.top, b.left))
