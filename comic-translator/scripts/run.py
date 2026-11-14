# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "numpy>=2.2.6,<3",
#   "pillow>=11.3.0,<14",
#   "onnxruntime>=1.22.1,<2",
#   "scipy>=1.15.3,<2",
# ]
# ///
"""comic-translator: `detect` writes each page's notes and images to read; `render` translates."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

import numpy as np
from PIL import Image

from comic_translator.clean import erased
from comic_translator.detect import (
    DetectError,
    held_lines,
    letters_held,
    line_boxes,
    page_blocks,
    unpacked,
)
from comic_translator.letter import lettered
from comic_translator.models import (
    INPAINTER,
    TEXT_FINDER,
    ModelError,
    Session,
    cache_folder,
    session_of,
)
from comic_translator.notes import (
    Box,
    Entry,
    NotesError,
    moved,
    read_notes,
    undrawable,
    untranslated_pages,
    write_notes,
)
from comic_translator.review import overview, review_images
from comic_translator.sheets import box_sheets

USAGE = (
    "usage: run.py detect <image or archive> | run.py render <work folder> [page ...]"
    " | run.py --help"
)
HELP = """usage: uv run scripts/run.py COMMAND ARGUMENT

Translate a comic's text in place, page by page.

commands:
  detect <image, .zip or .cbz>  find the text on every page and write a work folder beside the
                                input: notes to edit, and images to read them by; notes already
                                in the work folder are kept
  render <work folder> [page ...]
                                erase each entry's text and letter its translation, from the
                                original pages, into the work folder's translated/ pages; name
                                pages, such as 005, to redo only those

Each prints one JSON object, or one line starting "error:" saying what to fix.

examples:
  uv run scripts/run.py detect chapter.zip
  uv run scripts/run.py render chapter-work"""
FAILURES = (DetectError, ModelError, NotesError, OSError)
DETECT_FILES = (
    "in the work folder, for each page: notes/<page>.json to edit; overview/<page>.jpg the whole"
    " page with every box; boxes/<page>-<n>.jpg every box cut out, numbered; review/<page>-<n>.jpg"
    " the page in ruled stretches"
)
RENDER_FILES = (
    "in the work folder, for each page: translated/<page> the result; result-boxes/<page>-<n>.jpg"
    " every box cut from the result, numbered; result/<page>-<n>.jpg the result in ruled stretches"
)
RUNNING = ".rendering"
UNTRANSLATED = (
    "pages {pages} still have entries with no translation: translate each one, or delete it to "
    "leave its text as it is"
)
UNDRAWN = "page {found}, which the lettering font cannot draw: write it in words or leave it out"
JPEG_QUALITY = 90
FEW_LETTERS = 0.5


def work_of(source: Path) -> Path:
    return source.with_name(f"{source.stem}-work")


def detected_page(session: Session, path: Path, work: Path) -> dict[str, object]:
    """One page's blocks written as detect's own copy and, unless notes are already there, as
    its notes; drawn on its images as the notes have them."""
    page = page_image(path)
    blocks, likely = page_blocks(session, page)
    found = [Entry(n, box, "", "") for n, box in enumerate(blocks, start=1)]
    (work / "maps").mkdir(parents=True, exist_ok=True)
    likely.save(work / "maps" / f"{path.stem}.png", optimize=True)
    write_notes(work / "detected" / f"{path.stem}.json", found)
    notes = work / "notes" / f"{path.stem}.json"
    kept = notes.is_file()
    entries = read_notes(notes, page.size) if kept else found
    if not kept:
        write_notes(notes, found)
    overview(page, entries, work / "overview" / f"{path.stem}.jpg")
    drawn(page, entries, work / "review", path.stem)
    return {
        "page": path.stem,
        "entries": len(entries),
        "boxes": len(sheets(page, entries, work / "boxes", path.stem)),
        "notes": "kept" if kept else "written",
    }


def detect(source: Path, session: Session) -> dict[str, object]:
    """Every page of `source` unpacked into its work folder, with its notes and images to read."""
    work = work_of(source)
    pages = unpacked(source, work / "pages")
    found = [detected_page(session, p, work) for p in pages]
    return {"work": str(work), "files": DETECT_FILES, "pages": found}


def page_image(path: Path) -> Image.Image:
    with Image.open(path) as opened:
        return opened.convert("RGB")


class Inpainter:
    """The inpainting model, loaded the first time an entry needs it and then kept."""

    def __init__(self) -> None:
        self.session: Session | None = None

    def __call__(self) -> Session:
        if self.session is None:
            self.session = session_of(INPAINTER, cache_folder())
        return self.session


def translated(
    page: Image.Image, entries: list[Entry], inpainter: Inpainter, likely: Image.Image | None
) -> Image.Image:
    """A copy of `page` with every entry's text erased, then its translation lettered if any,
    clear of the other boxes; each step pastes only the piece it changed, so a tall page is never
    copied per entry."""
    done = page.copy()
    for entry in entries:
        patch = erased(done, entry.box, inpainter, likely)
        done.paste(patch.image, patch.at)
    for entry in entries:
        if entry.translation.strip():
            others = [other.box for other in entries if other is not entry]
            patch = lettered(done, page, entry.box, entry.translation, others)
            done.paste(patch.image, patch.at)
    return done


def cleared(folder: Path, stem: str) -> Path:
    for old in folder.glob(f"{stem}-*.jpg"):
        old.unlink()
    return folder / stem


def drawn(page: Image.Image, entries: list[Entry], folder: Path, stem: str) -> list[Path]:
    return review_images(page, entries, cleared(folder, stem))


def sheets(page: Image.Image, entries: list[Entry], folder: Path, stem: str) -> list[Path]:
    return box_sheets(page, entries, cleared(folder, stem))


def saved(done: Image.Image, path: Path, work: Path) -> Path:
    """The translated page saved under the original's name and in its format."""
    output = work / "translated" / path.name
    output.parent.mkdir(exist_ok=True)
    if path.suffix.lower() in (".jpg", ".jpeg"):
        done.save(output, quality=JPEG_QUALITY)
    else:
        done.save(output)
    return output


def warnings_of(path: Path, work: Path, entries: list[Entry], size: tuple[int, int]) -> list[str]:
    """A line for each entry whose box has moved away from where detect found its text."""
    copy = work / "detected" / f"{path.stem}.json"
    if not copy.is_file():
        return []
    return [
        f"{path.stem} #{entry.id}: its box is far from where detect found text {found.corners()}"
        " (left, top, right, bottom); check it"
        for entry, found in moved(entries, read_notes(copy, size))
    ]


def reads_too_little(entry: Entry, lines: list[Box]) -> bool:
    """Whether the box holds two lines or more and its original far fewer letters than they do."""
    held = held_lines(entry.box, lines)
    return len(held) > 1 and len(entry.original.strip()) < FEW_LETTERS * letters_held(held)


def unread(stem: str, entries: list[Entry], likely: Image.Image | None) -> list[str]:
    """A line for each entry whose original reads only part of the text detect sees in its box."""
    if likely is None:
        return []
    lines = line_boxes(np.asarray(likely, dtype=np.float32) / 255)
    return [
        f"{stem} #{entry.id}: its box holds {len(held_lines(entry.box, lines))} lines of text"
        f' but its original reads only "{entry.original.strip()}"; read the whole box'
        for entry in entries
        if reads_too_little(entry, lines)
    ]


def left_alone(path: Path, work: Path, entries: list[Entry], size: tuple[int, int]) -> list[int]:
    """The ids of the text detect found on the page that the notes no longer hold."""
    copy = work / "detected" / f"{path.stem}.json"
    if not copy.is_file():
        return []
    kept = {entry.id for entry in entries}
    return [found.id for found in read_notes(copy, size) if found.id not in kept]


def rendered_page(path: Path, work: Path, inpainter: Inpainter) -> dict[str, object]:
    """One page translated from its checked notes, with its images redrawn to look at."""
    page = page_image(path)
    entries = read_notes(work / "notes" / f"{path.stem}.json", page.size)
    likely_path = work / "maps" / f"{path.stem}.png"
    likely = Image.open(likely_path).convert("L") if likely_path.is_file() else None
    done = translated(page, entries, inpainter, likely)
    output = saved(done, path, work)
    overview(done, entries, work / "overview" / f"{path.stem}.jpg")
    drawn(page, entries, work / "review", path.stem)
    drawn(done, entries, work / "result", path.stem)
    sheets(page, entries, work / "boxes", path.stem)
    return {
        "page": path.stem,
        "translated": output.name,
        "result-boxes": len(sheets(done, entries, work / "result-boxes", path.stem)),
        "warnings": warnings_of(path, work, entries, page.size)
        + unread(path.stem, entries, likely),
        "left as it is": left_alone(path, work, entries, page.size),
    }


def alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextmanager
def alone(work: Path) -> Iterator[None]:
    """Render on its own in `work`: refused while another render there is still running."""
    mark = work / RUNNING
    holder = mark.read_text().strip() if mark.is_file() else ""
    if holder.isdigit() and alive(int(holder)):
        raise DetectError(
            "render is already running on this work folder; wait for it to finish rather than"
            " starting it again"
        )
    mark.write_text(str(os.getpid()))
    try:
        yield
    finally:
        mark.unlink(missing_ok=True)


def chosen(pages: Sequence[Path], names: Sequence[str]) -> list[Path]:
    """The pages named, in page order, or every page when none is named."""
    if not names:
        return list(pages)
    held = {p.stem: p for p in pages}
    unknown = [name for name in names if name not in held]
    if unknown:
        raise DetectError(
            f"the work folder has no page {', '.join(unknown)}; its pages are {', '.join(held)}"
        )
    return [held[name] for name in sorted(set(names))]


def ready(notes: dict[str, list[Entry]]) -> None:
    """`DetectError` while an entry is untranslated or holds a symbol the font cannot draw."""
    missing = untranslated_pages(notes)
    if missing:
        raise DetectError(UNTRANSLATED.format(pages=", ".join(missing)))
    symbols = undrawable(notes)
    if symbols:
        raise DetectError(UNDRAWN.format(found="; page ".join(symbols)))


def render(work: Path, names: Sequence[str]) -> dict[str, object]:
    """The named pages of the work folder, or every page, translated from their notes."""
    pages = sorted(p for p in (work / "pages").iterdir() if p.is_file())
    if not pages:
        raise DetectError(f"{work} holds no pages; run detect first")
    notes = {
        p.stem: read_notes(work / "notes" / f"{p.stem}.json", page_image(p).size) for p in pages
    }
    ready(notes)
    redo = chosen(pages, names)
    inpainter = Inpainter()
    with alone(work):
        done = [rendered_page(p, work, inpainter) for p in redo]
    return {"work": str(work), "files": RENDER_FILES, "pages": done}


def command(argv: Sequence[str]) -> dict[str, object]:
    match list(argv):
        case ["detect", source]:
            path = Path(source).expanduser()
            if not path.is_file():
                raise DetectError(f"{source} is not a file")
            return detect(path.resolve(), session_of(TEXT_FINDER, cache_folder()))
        case ["render", folder, *names]:
            work = Path(folder).expanduser().resolve()
            if not (work / "pages").is_dir():
                raise DetectError(f"{folder} is not a work folder from detect")
            return render(work, names)
        case _:
            raise DetectError(USAGE)


def main(argv: Sequence[str], stdout: TextIO) -> int:
    if list(argv) in (["--help"], ["-h"]):
        print(HELP, file=stdout)
        return 0
    try:
        result = command(argv)
    except FAILURES as failure:
        print(f"error: {failure}", file=stdout)
        return 1
    print(json.dumps(result, ensure_ascii=False), file=stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], sys.stdout))
