"""The notes: read back as written, and every mistake named by entry and field."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from comic_translator.notes import Box, Entry, NotesError, moved, read_notes, write_notes

SIZE = (400, 600)
GOOD = {
    "id": 1,
    "box": {"left": 10, "top": 20, "right": 110, "bottom": 60},
    "original": "",
    "translation": "",
}


def written(tmp_path: Path, entries: list) -> Path:
    path = tmp_path / "001.json"
    path.write_text(json.dumps(entries))
    return path


def test_notes_are_read_back_as_written(tmp_path: Path) -> None:
    entries = [
        Entry(1, Box(10, 20, 110, 60), "hola", "hello"),
        Entry(2, Box(5, 5, 50, 300), "a", "b", "vertical"),
    ]

    path = write_notes(tmp_path / "notes" / "001.json", entries)

    assert read_notes(path, SIZE) == entries
    assert "direction" not in json.loads(path.read_text())[0]


@pytest.mark.parametrize(
    ("change", "complaint"),
    [
        ({"box": [10, 20, 110, 60]}, "box needs exactly left, top, right, bottom"),
        ({"box": {"left": 10, "top": 20, "right": "wide", "bottom": 60}}, "whole numbers"),
        ({"box": {"left": 10, "top": 20, "right": 500, "bottom": 60}}, "inside the 400x600 page"),
        ({"translation": None}, "translation is text"),
        ({"id": "one"}, "id is a whole number"),
        ({"direction": "diagonal"}, "direction is one of"),
        ({"colour": "red"}, "unknown fields ['colour']"),
    ],
)
def test_a_mistake_in_an_entry_is_named(tmp_path: Path, change: dict, complaint: str) -> None:
    with pytest.raises(NotesError, match="entry 2") as refused:
        read_notes(written(tmp_path, [GOOD, {**GOOD, "id": 2, **change}]), SIZE)

    assert complaint in str(refused.value)


@pytest.mark.parametrize(
    ("text", "complaint"),
    [
        ("[1, 2", "not valid JSON"),
        ('{"id": 1}', "a list of entries"),
        ("[1]", "each entry is an object"),
    ],
)
def test_notes_that_are_not_a_list_of_entries_are_refused(
    tmp_path: Path, text: str, complaint: str
) -> None:
    path = tmp_path / "001.json"
    path.write_text(text)

    with pytest.raises(NotesError, match=complaint):
        read_notes(path, SIZE)


def test_ids_used_twice_are_refused(tmp_path: Path) -> None:
    with pytest.raises(NotesError, match=r"ids \[1\] are used more than once"):
        read_notes(written(tmp_path, [GOOD, GOOD]), SIZE)


def test_a_box_nudged_to_fit_its_text_is_not_moved_but_one_put_elsewhere_is() -> None:
    found = [Entry(n, Box(236, 2966, 466, 3068), "", "") for n in (1, 2, 3)]
    entries = [
        Entry(1, Box(226, 2960, 480, 3075), "", ""),
        Entry(2, Box(24, 3001, 648, 3471), "", ""),
        Entry(3, Box(310, 4475, 542, 4591), "", ""),
        Entry(9, Box(10, 10, 50, 50), "", ""),
    ]

    assert [(entry.id, box) for entry, box in moved(entries, found)] == [
        (2, Box(236, 2966, 466, 3068)),
        (3, Box(236, 2966, 466, 3068)),
    ]
