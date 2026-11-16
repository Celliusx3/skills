"""How many times each page of a work folder was rendered, so a page cannot be redrawn forever."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from comic_translator.detect import DetectError

MAX_RENDERS = 3
COUNTS = ".renders"
SPENT = (
    "pages {pages} were rendered {limit} times already: leave them as they are, and report "
    "what is still not clean on them"
)


def renders_so_far(work: Path, pages: Sequence[str]) -> dict[str, int]:
    """How many times each of `pages` was rendered in `work`."""
    folder = work / COUNTS
    return {
        page: int((folder / page).read_text()) if (folder / page).is_file() else 0 for page in pages
    }


def spent(counts: Mapping[str, int]) -> list[str]:
    """The pages, in order, rendered as many times as a page may be."""
    return [page for page, count in counts.items() if count >= MAX_RENDERS]


def refuse_spent(work: Path, pages: Sequence[str]) -> None:
    """Refuse, naming them, when any of `pages` may be rendered no more."""
    used = spent(renders_so_far(work, pages))
    if used:
        raise DetectError(SPENT.format(pages=", ".join(used), limit=MAX_RENDERS))


def count_render(work: Path, page: str) -> None:
    """Note one more render of `page`."""
    folder = work / COUNTS
    folder.mkdir(exist_ok=True)
    (folder / page).write_text(str(renders_so_far(work, [page])[page] + 1))
