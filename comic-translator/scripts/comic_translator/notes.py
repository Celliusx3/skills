"""A page's notes: one entry per piece of text to translate, as the model reads and edits them."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

EDGES = ("left", "top", "right", "bottom")
DIRECTIONS = ("horizontal", "vertical", "rtl")
SAME_PLACE = 0.4


class NotesError(ValueError):
    """Notes the model wrote that cannot be used, naming the entry and the field to fix."""


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    right: int
    bottom: int

    def corners(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom

    def area(self) -> int:
        return (self.right - self.left) * (self.bottom - self.top)


@dataclass(frozen=True)
class Entry:
    id: int
    box: Box
    original: str
    translation: str
    direction: str = "horizontal"


def box_from(raw: object, where: str, size: tuple[int, int]) -> Box:
    """A box named by its four edges, inside a page of `size`; refused naming what is wrong."""
    if not isinstance(raw, dict) or set(raw) != set(EDGES):
        raise NotesError(f"{where}: box needs exactly left, top, right, bottom")
    if not all(isinstance(raw[edge], int) for edge in EDGES):
        raise NotesError(f"{where}: box edges are whole numbers of page pixels")
    box = Box(*(raw[edge] for edge in EDGES))
    width, height = size
    if not (0 <= box.left < box.right <= width and 0 <= box.top < box.bottom <= height):
        raise NotesError(
            f"{where}: box must lie inside the {width}x{height} page, left < right, top < bottom"
        )
    return box


def entry_from(raw: object, number: int, size: tuple[int, int]) -> Entry:
    """One entry of the notes, checked field by field."""
    where = f"entry {number}"
    if not isinstance(raw, dict):
        raise NotesError(f"{where}: each entry is an object")
    unknown = set(raw) - {"id", "box", "original", "translation", "direction"}
    if unknown:
        raise NotesError(f"{where}: unknown fields {sorted(unknown)}")
    if not isinstance(raw.get("id"), int):
        raise NotesError(f"{where}: id is a whole number")
    for field in ("original", "translation"):
        if not isinstance(raw.get(field), str):
            raise NotesError(f"{where}: {field} is text")
    direction = raw.get("direction", "horizontal")
    if direction not in DIRECTIONS:
        raise NotesError(f"{where}: direction is one of {', '.join(DIRECTIONS)}")
    box = box_from(raw.get("box"), where, size)
    return Entry(raw["id"], box, raw["original"], raw["translation"], direction)


def entries_from(raw: object, size: tuple[int, int]) -> list[Entry]:
    """Every entry of the notes; ids must not repeat."""
    if not isinstance(raw, list):
        raise NotesError("notes are a list of entries")
    entries = [entry_from(each, number, size) for number, each in enumerate(raw, start=1)]
    ids = [entry.id for entry in entries]
    repeated = sorted({each for each in ids if ids.count(each) > 1})
    if repeated:
        raise NotesError(f"ids {repeated} are used more than once")
    return entries


def shared(one: Box, other: Box) -> float:
    """How much of the two boxes is common to both: their overlap over the area either covers."""
    across = max(0, min(one.right, other.right) - max(one.left, other.left))
    down = max(0, min(one.bottom, other.bottom) - max(one.top, other.top))
    common = across * down
    return common / (one.area() + other.area() - common)


def moved(entries: list[Entry], found: list[Entry]) -> list[tuple[Entry, Box]]:
    """Each entry whose box shares less than SAME_PLACE with the box detect found under its id,
    with that box; an entry the model added has no such box and is never one."""
    boxes = {each.id: each.box for each in found}
    return [
        (entry, boxes[entry.id])
        for entry in entries
        if entry.id in boxes and shared(entry.box, boxes[entry.id]) < SAME_PLACE
    ]


def read_notes(path: Path, size: tuple[int, int]) -> list[Entry]:
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise NotesError(f"{path.name} is not valid JSON: {error}") from error
    return entries_from(raw, size)


def written(entry: Entry) -> dict[str, object]:
    raw = asdict(entry)
    if entry.direction == "horizontal":
        del raw["direction"]
    return raw


def write_notes(path: Path, entries: list[Entry]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([written(entry) for entry in entries], indent=1, ensure_ascii=False))
    return path
