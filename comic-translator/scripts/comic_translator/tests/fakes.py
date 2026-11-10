"""A stand-in for the text finder: every dark pixel is text, so tests can draw where text is."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from comic_translator.detect import MEAN, SPREAD

DARK = 0.3


class DarkIsText:
    def run(self, outputs: None, feeds: dict) -> list:
        bgr = feeds["x"][0].transpose(1, 2, 0) * SPREAD + MEAN
        return [(bgr.mean(axis=-1) < DARK).astype(np.float32)[None, None]]


def page_with_lines(path: Path, lines: list[tuple[int, int, int, int]], size=(400, 600)) -> Path:
    """A white page with a black bar for each line of text, saved at `path`."""
    page = Image.new("RGB", size, "white")
    pen = ImageDraw.Draw(page)
    for line in lines:
        pen.rectangle(line, fill="black")
    page.save(path)
    return path


class FlatGrey:
    """A stand-in for the inpainting model that redraws every hole mid grey."""

    def run(self, outputs: None, feeds: dict) -> list:
        image = feeds["image"] * 255
        image[:, :, feeds["mask"][0, 0] > 0] = 128
        return [image]


def fake_session(model, folder) -> object:
    from comic_translator.models import TEXT_FINDER

    return DarkIsText() if model == TEXT_FINDER else FlatGrey()
