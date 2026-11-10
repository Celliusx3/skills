"""The script: detect writes notes and images to read; render checks the notes and redraws them."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest
from PIL import Image

import run
from comic_translator.tests.fakes import fake_session, page_with_lines


def called(argv: list[str]) -> tuple[int, dict | str]:
    out = io.StringIO()
    code = run.main(argv, out)
    text = out.getvalue().strip()
    return code, json.loads(text) if code == 0 and text.startswith("{") else text


@pytest.fixture
def detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(run, "session_of", fake_session)
    page = page_with_lines(tmp_path / "001.png", [(40, 50, 300, 62), (60, 400, 200, 412)])
    code, result = called(["detect", str(page)])
    assert code == 0
    return result


def notes_of(detected: dict) -> Path:
    return Path(detected["work"]) / "notes" / "001.json"


def test_detect_writes_each_page_s_notes_its_own_copy_and_images_to_read(detected: dict) -> None:
    work = Path(detected["work"])
    [page] = detected["pages"]
    notes = json.loads(notes_of(detected).read_text())

    assert page == {"page": "001", "entries": 2, "boxes": 1, "notes": "written"}
    assert [entry["id"] for entry in notes] == [1, 2]
    assert notes[0]["original"] == notes[0]["translation"] == ""
    assert (work / "detected" / "001.json").read_text() == notes_of(detected).read_text()
    assert (work / "boxes" / "001-1.jpg").is_file()
    assert (work / "overview" / "001.jpg").is_file()
    assert list((work / "review").glob("001-*.jpg"))


def test_detect_again_keeps_the_notes_already_edited(detected: dict) -> None:
    entries = json.loads(notes_of(detected).read_text())
    notes_of(detected).write_text(json.dumps([{**entries[0], "translation": "hello"}]))
    page = Path(detected["work"]).parent / "001.png"

    code, again = called(["detect", str(page)])

    assert code == 0
    assert again["pages"][0]["notes"] == "kept"
    assert json.loads(notes_of(detected).read_text())[0]["translation"] == "hello"


def test_help_says_how_to_call_both_commands() -> None:
    code, text = called(["--help"])

    assert code == 0
    assert "run.py detect" in text and "run.py render" in text


def test_render_translates_the_page_from_the_edited_notes(detected: dict) -> None:
    work = Path(detected["work"])
    entries = json.loads(notes_of(detected).read_text())
    notes_of(detected).write_text(json.dumps([{**entries[0], "translation": "hello"}]))

    code, result = called(["render", detected["work"]])

    assert code == 0
    assert result["pages"] == [
        {"page": "001", "translated": "001.png", "result-boxes": 1, "warnings": []}
    ]
    assert (work / "translated" / "001.png").is_file()
    assert (work / "result-boxes" / "001-1.jpg").is_file()
    assert not (work / run.RUNNING).exists()


def test_render_warns_of_a_box_moved_far_from_its_text(detected: dict) -> None:
    entries = json.loads(notes_of(detected).read_text())
    far = {"left": 10, "top": 500, "right": 100, "bottom": 560}
    notes_of(detected).write_text(json.dumps([{**entries[0], "box": far}]))

    code, result = called(["render", detected["work"]])

    assert code == 0
    [warning] = result["pages"][0]["warnings"]
    assert warning.startswith("001 #1: its box is far from where detect found text (")


def test_render_refuses_while_another_render_runs_there(detected: dict) -> None:
    (Path(detected["work"]) / run.RUNNING).write_text(str(os.getpid()))

    code, message = called(["render", detected["work"]])

    assert code == 1
    assert "render is already running on this work folder" in message


def test_render_goes_ahead_past_the_mark_of_a_render_that_died(detected: dict) -> None:
    (Path(detected["work"]) / run.RUNNING).write_text("999999999")

    code, _ = called(["render", detected["work"]])

    assert code == 0


def test_a_jpeg_page_is_translated_to_a_jpeg_and_folders_among_pages_are_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run, "session_of", fake_session)
    png = page_with_lines(tmp_path / "002.png", [(40, 50, 300, 62)])
    page = tmp_path / "002.jpg"
    Image.open(png).convert("RGB").save(page)
    _, result = called(["detect", str(page)])
    (Path(result["work"]) / "pages" / "leftover").mkdir()

    code, rendered = called(["render", result["work"]])

    assert code == 0
    assert rendered["pages"][0]["translated"] == "002.jpg"


def test_render_names_the_mistake_in_the_notes(detected: dict) -> None:
    entries = json.loads(notes_of(detected).read_text())
    notes_of(detected).write_text(json.dumps([{**entries[0], "box": [1, 2, 3, 4]}]))

    code, message = called(["render", detected["work"]])

    assert code == 1
    assert message == "error: entry 1: box needs exactly left, top, right, bottom"


@pytest.mark.parametrize(
    ("argv", "complaint"),
    [
        (["translate"], "usage: run.py detect"),
        (["detect", "/no/such/page.png"], "is not a file"),
        (["render", "/no/such/work"], "is not a work folder"),
    ],
)
def test_a_wrong_call_says_what_to_do(argv: list[str], complaint: str) -> None:
    code, message = called(argv)

    assert code == 1
    assert complaint in message
