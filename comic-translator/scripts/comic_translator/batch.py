"""A chapter's pages handed to the model one call per page: the parts, the jobs files that list
the calls, the names list they share, and the notes their answers become."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

from comic_translator.detect import DetectError, number_order

SHEETS_PER_NAMES_CALL = 10
DRAFTS = "drafts"
JOBS = "jobs"
INSTRUCTIONS = Path(__file__).parent / "instructions"

PAGE_INSTRUCTIONS = (INSTRUCTIONS / "page.txt").read_text().strip()

NAMES_INSTRUCTIONS = (INSTRUCTIONS / "names.txt").read_text().strip()


def text_pages(work: Path) -> list[str]:
    """The pages, in page order, whose notes hold at least one entry."""
    notes = sorted((work / "notes").glob("*.json"), key=lambda p: number_order(p.stem))
    return [n.stem for n in notes if json.loads(n.read_text())]


def split_evenly(pages: Sequence[str], parts: int) -> list[list[str]]:
    """`pages` in order, in at most `parts` runs as even as they go."""
    count = max(1, min(parts, len(pages)))
    size, extra = divmod(len(pages), count)
    runs, start = [], 0
    for index in range(count):
        end = start + size + (1 if index < extra else 0)
        runs.append(list(pages[start:end]))
        start = end
    return [run for run in runs if run]


def parts_summary(work: Path, workers: int, language: str, archive: str) -> str:
    """Prepare's report: one Part line per worker, naming its pages, then the Combine line."""
    pages = text_pages(work)
    runs = split_evenly(pages, workers)
    total = len(list((work / "pages").iterdir()))
    lines = [
        f"The chapter has {total} pages, {len(pages)} of them with text, so it is translated in "
        f"{len(runs)} parts.",
        "Start one worker task for each line below now, the line as its whole task:",
        *(
            f"- Part: translate pages {', '.join(run)} of the chapter in {work} into {language}, "
            "with the comic-translator skill."
            for run in runs
        ),
        "Only after every one of those reports ready, start one worker task for this line:",
        f"- Combine: pack the chapter in {work} with the comic-translator skill, and hand over "
        f"{archive}.",
    ]
    return "\n".join(lines)


def page_sheets(work: Path, page: str) -> list[str]:
    """The paths of `page`'s box sheets, in order."""
    sheets = (work / "boxes").glob(f"{page}-*.jpg")
    return [str(p) for p in sorted(sheets, key=lambda p: number_order(p.name))]


def page_ids(work: Path, page: str) -> list[int]:
    """The entry ids in `page`'s notes."""
    return [entry["id"] for entry in json.loads((work / "notes" / f"{page}.json").read_text())]


def names_of(work: Path) -> dict[str, str]:
    """The chapter's names list, empty when there is none yet."""
    path = work / "names.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def jobs_file(work: Path, name: str, jobs: Sequence[dict[str, object]]) -> dict[str, object]:
    """`jobs` written to `work`/jobs/`name`.json, each a call's images, instructions and the file
    its answer is saved to; where they are, and how many."""
    folder = work / JOBS
    folder.mkdir(exist_ok=True)
    (work / DRAFTS).mkdir(exist_ok=True)
    path = folder / f"{name}.json"
    path.write_text(json.dumps(list(jobs), ensure_ascii=False, indent=1))
    return {"jobs": str(path), "count": len(jobs)}


def page_jobs(work: Path, language: str, pages: Sequence[str]) -> dict[str, object]:
    """The jobs file for `pages`: each page one call that reads its box sheets and saves its
    draft."""
    known = set(text_pages(work))
    unknown = [page for page in pages if page not in known]
    if unknown:
        raise DetectError(f"pages {', '.join(unknown)} have no text to translate")
    names = json.dumps(names_of(work), ensure_ascii=False)
    jobs = [
        {
            "paths": page_sheets(work, page),
            "instructions": PAGE_INSTRUCTIONS.format(
                language=language,
                ids=", ".join(map(str, page_ids(work, page))),
                names=names,
            ),
            "save_to": str(work / DRAFTS / f"{page}.json"),
        }
        for page in pages
    ]
    return jobs_file(work, f"pages-{pages[0]}-{pages[-1]}", jobs)


def names_jobs(work: Path, language: str) -> dict[str, object]:
    """The jobs file whose calls list the chapter's names from its box sheets, a few at a time."""
    sheets = [sheet for page in text_pages(work) for sheet in page_sheets(work, page)]
    jobs = [
        {
            "paths": sheets[i : i + SHEETS_PER_NAMES_CALL],
            "instructions": NAMES_INSTRUCTIONS.format(language=language),
            "save_to": str(work / DRAFTS / f"names-{i // SHEETS_PER_NAMES_CALL + 1}.json"),
        }
        for i in range(0, len(sheets), SHEETS_PER_NAMES_CALL)
    ]
    return jobs_file(work, "names", jobs)


def answer_of(path: Path) -> object:
    """The JSON a saved answer holds, its ```json fence removed; None when it holds none."""
    if not path.is_file():
        return None
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", path.read_text())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def merged_names(work: Path) -> dict[str, str]:
    """names.json with every saved names answer added, entries already there kept."""
    names = names_of(work)
    drafts = sorted((work / DRAFTS).glob("names-*.json"), key=lambda p: number_order(p.name))
    for draft in drafts:
        answer = answer_of(draft)
        found = answer.get("names") if isinstance(answer, dict) else None
        if isinstance(found, dict):
            for original, translation in found.items():
                if isinstance(original, str) and isinstance(translation, str):
                    names.setdefault(original, translation)
    (work / "names.json").write_text(json.dumps(names, ensure_ascii=False, indent=1))
    return names
