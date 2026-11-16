"""The one-call-per-page commands: parts, jobs files, the names list, and answers into notes."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

import run
from comic_translator.batch import split_evenly

SKILL = Path(__file__).parents[3]
CLIENT_TOOLS = (
    "ticket_route",
    "ticket_report",
    "execute_typescript",
    "ask_about_images",
    "ask_about_image_jobs",
    "computer__",
)

BOX = {"left": 20, "top": 20, "right": 40, "bottom": 30}


def called(argv: list[str]) -> tuple[int, dict | str]:
    out = io.StringIO()
    code = run.main(argv, out)
    text = out.getvalue().strip()
    return code, json.loads(text) if code == 0 and text.startswith("{") else text


@pytest.fixture
def work(tmp_path: Path) -> Path:
    """A work folder whose pages 9, 10 and 100 have text and page 11 has none."""
    folder = tmp_path / "ch-work"
    for page, ids in (("9", [1, 2]), ("10", [1]), ("11", []), ("100", [1])):
        (folder / "pages").mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (60, 150), "white").save(folder / "pages" / f"{page}.jpg")
        (folder / "notes").mkdir(exist_ok=True)
        entries = [{"id": i, "box": BOX, "original": "", "translation": ""} for i in ids]
        (folder / "notes" / f"{page}.json").write_text(json.dumps(entries))
        (folder / "boxes").mkdir(exist_ok=True)
        if ids:
            (folder / "boxes" / f"{page}-1.jpg").write_bytes(b"x")
    return folder


def answer(work: Path, page: str, content: object) -> None:
    (work / "drafts").mkdir(exist_ok=True)
    text = content if isinstance(content, str) else json.dumps(content)
    (work / "drafts" / f"{page}.json").write_text(text)


def notes(work: Path, page: str) -> list[dict]:
    return json.loads((work / "notes" / f"{page}.json").read_text())


def test_pages_split_as_evenly_as_they_go() -> None:
    assert split_evenly(["1", "2", "3", "4", "5"], 3) == [["1", "2"], ["3", "4"], ["5"]]
    assert split_evenly(["1"], 3) == [["1"]]


def test_parts_name_each_part_s_pages_and_leave_out_pages_with_no_text(work: Path) -> None:
    code, result = called(["parts", str(work), "2", "English", "/x/ch-english.zip"])

    assert code == 0
    summary = result["summary"]
    assert (
        "The chapter has 4 pages, 3 of them with text, so it is translated in 2 parts." in summary
    )
    assert f"- Part: translate pages 9, 10 of the chapter in {work} into English" in summary
    assert f"- Part: translate pages 100 of the chapter in {work} into English" in summary
    assert "hand over /x/ch-english.zip." in summary
    assert "Start one worker task for each line below now" in summary


def jobs_at(path: str) -> list[dict]:
    return json.loads(Path(path).read_text())


def test_a_jobs_file_lists_one_job_per_page_saving_its_answer(work: Path) -> None:
    (work / "names.json").write_text(json.dumps({"민준": "Minjun"}))

    code, result = called(["jobs", str(work), "English", "9", "100"])

    assert code == 0
    assert result["jobs"] == str(work / "jobs" / "pages-9-100.json")
    assert result["count"] == 2
    jobs = jobs_at(result["jobs"])
    assert [set(job) for job in jobs] == [{"paths", "instructions", "save_to"}] * 2
    assert [job["save_to"] for job in jobs] == [
        str(work / "drafts" / f"{p}.json") for p in ("9", "100")
    ]
    assert jobs[0]["paths"] == [str(work / "boxes" / "9-1.jpg")]
    assert "For every box number in 1, 2," in jobs[0]["instructions"]
    assert '{"민준": "Minjun"}' in jobs[0]["instructions"]


def test_jobs_refuse_a_page_with_no_text(work: Path) -> None:
    code, text = called(["jobs", str(work), "English", "11"])

    assert code == 1
    assert text == "error: pages 11 have no text to translate"


def test_answers_become_notes_leaving_signs_drawn_sounds_and_titles(work: Path) -> None:
    answer(
        work,
        "9",
        "```json\n"
        + json.dumps(
            {
                "boxes": [
                    {"id": 1, "kind": "shout", "original": "어서 와", "translation": "Welcome"},
                    {"id": 2, "kind": "sign", "original": "편의점", "translation": "Store"},
                ],
                "missed": "",
            }
        )
        + "\n```",
    )

    code, result = called(["apply", str(work), "9"])

    assert code == 0
    assert result == {"applied": 1, "flagged": {}}
    assert [(e["id"], e["original"], e["translation"]) for e in notes(work, "9")] == [
        (1, "어서 와", "Welcome")
    ]


def test_a_page_with_a_doubtful_answer_is_flagged_and_its_unanswered_box_kept(work: Path) -> None:
    answer(
        work,
        "9",
        {
            "boxes": [
                {"id": 1, "kind": "speech", "original": "?", "translation": "Hm", "unsure": True}
            ],
            "missed": "a caption at the top",
        },
    )

    code, result = called(["apply", str(work), "9", "10"])

    assert code == 0
    assert result["flagged"] == {
        "9": ["box 1 is unsure", "no answer for box 2", "missed: a caption at the top"],
        "10": ["no answer saved"],
    }
    assert [e["id"] for e in notes(work, "9")] == [1, 2]


def test_a_kept_box_with_no_translation_is_flagged_and_left_for_a_look(work: Path) -> None:
    answer(
        work,
        "10",
        {"boxes": [{"id": 1, "kind": "sound_in_bubble", "original": "a", "translation": " "}]},
    )

    code, result = called(["apply", str(work), "10"])

    assert result["flagged"] == {"10": ["box 1 has no translation"]}
    assert notes(work, "10")[0]["translation"] == ""


def test_saved_names_are_added_to_the_names_list_keeping_those_already_there(work: Path) -> None:
    (work / "names.json").write_text(json.dumps({"민준": "Minjun"}))
    (work / "drafts").mkdir()
    (work / "drafts" / "names-1.json").write_text(
        json.dumps({"names": {"민준": "Min-jun", "예나": "Yena"}})
    )
    (work / "drafts" / "names-2.json").write_text("not json")

    code, result = called(["names", str(work)])

    assert code == 0
    assert result == {"names": {"민준": "Minjun", "예나": "Yena"}}
    assert json.loads((work / "names.json").read_text()) == result["names"]


def test_the_names_jobs_read_the_box_sheets_a_few_at_a_time(work: Path) -> None:
    code, result = called(["names-jobs", str(work), "English"])

    assert code == 0
    assert result == {"jobs": str(work / "jobs" / "names.json"), "count": 1}
    [job] = jobs_at(result["jobs"])
    assert job["paths"] == [str(work / "boxes" / f"{p}-1.jpg") for p in ("9", "10", "100")]
    assert job["save_to"] == str(work / "drafts" / "names-1.json")


def test_the_skill_names_no_tool_of_the_client_it_runs_in() -> None:
    for path in (
        SKILL / "SKILL.md",
        SKILL / "scripts" / "run.py",
        *(SKILL / "scripts" / "comic_translator").glob("*.py"),
        *(SKILL / "scripts" / "comic_translator" / "instructions").glob("*.txt"),
    ):
        text = path.read_text()
        assert not [tool for tool in CLIENT_TOOLS if tool in text], path


def test_a_folder_that_is_not_a_work_folder_is_refused(tmp_path: Path) -> None:
    code, text = called(["apply", str(tmp_path), "1"])

    assert code == 1
    assert text.endswith("is not a work folder from detect")


def test_a_box_with_no_kind_is_kept_as_speech(work: Path) -> None:
    answer(work, "10", {"boxes": [{"id": 1, "original": "하아", "translation": "Hah"}]})

    code, result = called(["apply", str(work), "10"])

    assert result["flagged"] == {}
    assert notes(work, "10")[0]["translation"] == "Hah"


def bubbled(work: Path, page: str) -> None:
    """Draw a closed bubble outline round the test box on `page`."""
    image = Image.new("RGB", (60, 150), "white")
    ImageDraw.Draw(image).rectangle((8, 8, 52, 42), outline="black", width=2)
    image.save(work / "pages" / f"{page}.jpg")


def test_a_sound_called_drawn_but_inside_a_bubble_is_kept(work: Path) -> None:
    bubbled(work, "10")
    answer(
        work,
        "10",
        {"boxes": [{"id": 1, "kind": "drawn_sound", "original": "하아..", "translation": "Hah.."}]},
    )

    called(["apply", str(work), "10"])

    assert notes(work, "10")[0]["translation"] == "Hah.."


def test_a_sound_drawn_on_open_paper_is_left_as_it_is(work: Path) -> None:
    answer(
        work,
        "10",
        {"boxes": [{"id": 1, "kind": "drawn_sound", "original": "쿵", "translation": "THUD"}]},
    )

    called(["apply", str(work), "10"])

    assert notes(work, "10") == []
