"""Renders in one work folder take turns, and a page being rendered is not rendered twice."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from comic_translator.detect import DetectError

MARK = ".rendering-{page}"
TURN = ".render-turn"
BUSY = (
    "render is already running on page {pages}; wait for it to finish rather than starting it again"
)


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


def held(mark: Path) -> bool:
    holder = mark.read_text().strip() if mark.is_file() else ""
    return holder.isdigit() and alive(int(holder))


@contextmanager
def turn_of(work: Path, pages: Sequence[str]) -> Iterator[None]:
    """Render `pages` of `work` once another render there has finished, so one model's worth of
    memory is in use at a time; refused while another render is drawing any of them."""
    busy = [page for page in pages if held(work / MARK.format(page=page))]
    if busy:
        raise DetectError(BUSY.format(pages=", ".join(busy)))
    marks = [work / MARK.format(page=page) for page in pages]
    for mark in marks:
        mark.write_text(str(os.getpid()))
    try:
        with (work / TURN).open("a") as turn:
            fcntl.flock(turn, fcntl.LOCK_EX)
            yield
    finally:
        for mark in marks:
            mark.unlink(missing_ok=True)
