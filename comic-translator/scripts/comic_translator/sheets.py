"""Box sheets: every entry's box cut from the page with a margin round it, enlarged, numbered."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from comic_translator.notes import Entry
from comic_translator.review import BOX_COLOUR

MARGIN = 16
WIDTH = 1000
TALL = 1400
GAP = 14
LABEL = 34
LABEL_SIZE = 26
WIDEST = 480
TALLEST = 420
LARGEST = 2.0
BACKGROUND = (235, 235, 235)
QUALITY = 85


def tile(page: Image.Image, entry: Entry) -> Image.Image:
    """The entry's box and MARGIN round it, enlarged up to LARGEST to fit WIDEST by TALLEST,
    under a label with its id."""
    box = entry.box
    piece = page.crop(
        (
            max(0, box.left - MARGIN),
            max(0, box.top - MARGIN),
            min(page.width, box.right + MARGIN),
            min(page.height, box.bottom + MARGIN),
        )
    )
    scale = min(LARGEST, WIDEST / piece.width, TALLEST / piece.height)
    piece = piece.resize((max(1, round(piece.width * scale)), max(1, round(piece.height * scale))))
    labelled = Image.new("RGB", (max(piece.width, 2 * LABEL), piece.height + LABEL), "white")
    labelled.paste(piece, (0, LABEL))
    pen = ImageDraw.Draw(labelled)
    pen.rectangle((0, 0, 2 * LABEL, LABEL - 4), fill=BOX_COLOUR)
    pen.text((8, 2), str(entry.id), fill="white", font=ImageFont.load_default(size=LABEL_SIZE))
    return labelled


def laid_out(tiles: list[Image.Image]) -> list[Image.Image]:
    """The tiles in rows across sheets WIDTH wide, a new sheet whenever one reaches TALL."""
    sheets: list[Image.Image] = []
    sheet = Image.new("RGB", (WIDTH, TALL), BACKGROUND)
    x = y = row = 0
    for each in tiles:
        if x and x + each.width > WIDTH:
            x, y, row = 0, y + row + GAP, 0
        if y and y + each.height > TALL:
            sheets.append(sheet.crop((0, 0, WIDTH, y - GAP)))
            sheet = Image.new("RGB", (WIDTH, TALL), BACKGROUND)
            x = y = row = 0
        sheet.paste(each, (x, y))
        x, row = x + each.width + GAP, max(row, each.height)
    sheets.append(sheet.crop((0, 0, WIDTH, min(TALL, y + row))))
    return sheets


def box_sheets(page: Image.Image, entries: list[Entry], prefix: Path) -> list[Path]:
    """Every entry's box from `page` on sheets saved as `prefix`-<n>.jpg, in the entries' order;
    none when there are no entries."""
    if not entries:
        return []
    prefix.parent.mkdir(parents=True, exist_ok=True)
    paths = []
    for number, sheet in enumerate(laid_out([tile(page, e) for e in entries]), start=1):
        path = prefix.with_name(f"{prefix.name}-{number}.jpg")
        sheet.save(path, quality=QUALITY)
        paths.append(path)
    return paths
