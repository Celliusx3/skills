"""What the model checks the notes against: the page in ruled stretches, each box numbered."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from comic_translator.notes import Entry

STRETCH = 1000
RULER = 56
TICK = 50
BOX_COLOUR = (230, 20, 60)
BOX_WIDTH = 3
LABEL_SIZE = 22
RULER_SIZE = 16
QUALITY = 85
OVERLAP = 150
SHRINK = 0.25
COLUMN = 4000
GAP = 12
OVERVIEW_LABEL = 14


def cut_points(height: int) -> list[int]:
    """Where to cut the page into stretches: every STRETCH pixels, the same on every render."""
    return [*range(0, height, STRETCH), height]


def ruled(stretch: Image.Image, top: int) -> Image.Image:
    """`stretch` with a ruler along its top and left edge, labelled in page pixels."""
    width, height = stretch.size
    sheet = Image.new("RGB", (width + RULER, height + RULER), "white")
    sheet.paste(stretch, (RULER, RULER))
    pen = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=RULER_SIZE)
    for x in range(0, width, TICK):
        pen.line((RULER + x, RULER - 10, RULER + x, RULER), fill="black")
        pen.text((RULER + x + 2, 4), str(x), fill="black", font=font)
    first = -(-top // TICK) * TICK
    for y in range(first, top + height, TICK):
        pen.line((RULER - 10, RULER + y - top, RULER, RULER + y - top), fill="black")
        pen.text((2, RULER + y - top + 2), str(y), fill="black", font=font)
    return sheet


def label_place(pen: ImageDraw.ImageDraw, label: str, left: int, upper: int, lower: int) -> tuple:
    """Where an id label goes: just above its box, or just below when there is no room above."""
    font = ImageFont.load_default(size=LABEL_SIZE)
    x0, y0, x1, y1 = pen.textbbox((0, 0), label, font=font)
    tall = y1 - y0 + 4
    y = upper - tall - BOX_WIDTH if upper - tall - BOX_WIDTH >= RULER else lower + BOX_WIDTH
    return (left, y), (left - 3, y + y0 - 2, left + x1 + 3, y + y1 + 2)


def boxed(sheet: Image.Image, entries: list[Entry], top: int, bottom: int) -> Image.Image:
    """`sheet` with each entry reaching into its stretch drawn as a box, its id outside it."""
    pen = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=LABEL_SIZE)
    for entry in entries:
        if entry.box.bottom <= top or entry.box.top >= bottom:
            continue
        left, upper = RULER + entry.box.left, RULER + entry.box.top - top
        right, lower = RULER + entry.box.right, RULER + entry.box.bottom - top
        pen.rectangle((left, upper, right, lower), outline=BOX_COLOUR, width=BOX_WIDTH)
        at, tag = label_place(pen, str(entry.id), left, upper, lower)
        pen.rectangle(tag, fill=BOX_COLOUR)
        pen.text(at, str(entry.id), fill="white", font=font)
    return sheet


def overview(page: Image.Image, entries: list[Entry], path: Path) -> Path:
    """The whole page at SHRINK, in columns side by side, every box drawn with its id."""
    small = page.resize((round(page.width * SHRINK), round(page.height * SHRINK)))
    pen = ImageDraw.Draw(small)
    font = ImageFont.load_default(size=OVERVIEW_LABEL)
    for entry in entries:
        corners = [round(edge * SHRINK) for edge in entry.box.corners()]
        pen.rectangle(corners, outline=BOX_COLOUR, width=2)
        pen.text((corners[2] + 3, corners[1]), str(entry.id), fill=BOX_COLOUR, font=font)
    tall = round(COLUMN * SHRINK)
    columns = [
        small.crop((0, top, small.width, min(small.height, top + tall)))
        for top in range(0, small.height, tall)
    ]
    sheet = Image.new("RGB", ((small.width + GAP) * len(columns), tall), "white")
    for number, column in enumerate(columns):
        sheet.paste(column, (number * (small.width + GAP), 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=QUALITY)
    return path


def review_images(page: Image.Image, entries: list[Entry], prefix: Path) -> list[Path]:
    """The ruled stretches of the page that hold a box, each reaching OVERLAP into its
    neighbours so a line near a cut shows whole, saved as `prefix`-<stretch>.jpg."""
    prefix.parent.mkdir(parents=True, exist_ok=True)
    cuts = cut_points(page.height)
    paths = []
    for number, (top, bottom) in enumerate(zip(cuts, cuts[1:], strict=False), start=1):
        if not any(e.box.top < bottom and e.box.bottom > top for e in entries):
            continue
        shown_top, shown_bottom = max(0, top - OVERLAP), min(page.height, bottom + OVERLAP)
        stretch = page.crop((0, shown_top, page.width, shown_bottom))
        sheet = boxed(ruled(stretch, shown_top), entries, shown_top, shown_bottom)
        path = prefix.with_name(f"{prefix.name}-{number}.jpg")
        sheet.save(path, quality=QUALITY)
        paths.append(path)
    return paths
