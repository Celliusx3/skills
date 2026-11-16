"""A webtoon's strips cut again only in blank rows, and cut back at their own edges to pack."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

import run
from comic_translator.strip import LAYOUT, cut_back, cut_rows, is_strip, laid_out
from comic_translator.tests.fakes import fake_session

WIDTH, HEIGHT = 100, 250


def strips(folder: Path, bubble_rows: tuple[int, int]) -> list[Path]:
    """Three white strips of one chapter, with a bubble outline drawn across rows of the joined
    strip, and a line of text in each strip's middle."""
    folder.mkdir(parents=True, exist_ok=True)
    whole = Image.new("RGB", (WIDTH, 3 * HEIGHT), "white")
    pen = ImageDraw.Draw(whole)
    top, bottom = bubble_rows
    pen.rectangle((20, top, 80, bottom), outline="black", width=2)
    for n in range(3):
        pen.rectangle((30, n * HEIGHT + 100, 70, n * HEIGHT + 110), fill="black")
    paths = []
    for n in range(3):
        path = folder / f"{n + 1}.png"
        whole.crop((0, n * HEIGHT, WIDTH, (n + 1) * HEIGHT)).save(path)
        paths.append(path)
    return paths


def rows_of(paths: list[Path]) -> np.ndarray:
    return np.concatenate([np.asarray(Image.open(p).convert("RGB")) for p in paths])


def test_only_pages_of_one_width_far_taller_than_wide_are_a_strip() -> None:
    assert is_strip([(100, 250), (100, 250)])
    assert not is_strip([(100, 250)])
    assert not is_strip([(100, 250), (120, 250)])
    assert not is_strip([(100, 140), (100, 140)])
    assert is_strip([(100, 250), (100, 250), (100, 90)])


def test_a_strip_with_a_few_short_pieces_in_it_is_still_a_strip() -> None:
    lookism_ep1 = [(690, 2000)] * 5 + [(690, 234), (690, 2000), (690, 148)] + [(690, 2000)] * 4

    assert is_strip(lookism_ep1)
    assert not is_strip([(100, 250), (100, 140), (100, 140)])


def test_cuts_fall_in_blank_gaps_and_never_through_drawn_rows() -> None:
    blank = np.ones(750, dtype=bool)
    blank[230:271] = False

    cuts = cut_rows(blank, 250)

    assert cuts
    assert all(not 230 <= cut <= 270 for cut in cuts)


def test_a_stretch_with_no_blank_gap_is_left_whole() -> None:
    assert cut_rows(np.zeros(750, dtype=bool), 250) == []


def test_a_bubble_across_two_strips_lands_on_one_page(tmp_path: Path) -> None:
    sources = strips(tmp_path / "source", (220, 280))
    work = tmp_path / "work"

    pages = laid_out(work, sources)

    edges = np.cumsum([Image.open(p).size[1] for p in pages])[:-1]
    assert all(not 220 <= edge <= 282 for edge in edges)
    assert np.array_equal(rows_of(pages), rows_of(sources))
    assert json.loads((work / LAYOUT).read_text())["strips"][0] == {"name": "1.png", "height": 250}


def test_the_pages_cut_back_into_the_original_strips(tmp_path: Path) -> None:
    sources = strips(tmp_path / "source", (220, 280))
    work = tmp_path / "work"
    pages = laid_out(work, sources)

    back = cut_back(work, pages)

    assert [name for name, _ in back] == ["1.png", "2.png", "3.png"]
    for (_, image), source in zip(back, sources, strict=True):
        assert np.array_equal(np.asarray(image), np.asarray(Image.open(source).convert("RGB")))


def test_pages_that_are_not_a_strip_are_kept_as_they_are(tmp_path: Path) -> None:
    folder = tmp_path / "source"
    folder.mkdir()
    for name in ("1.png", "2.png"):
        Image.new("RGB", (100, 140), "white").save(folder / name)

    pages = laid_out(tmp_path / "work", sorted(folder.iterdir()))

    assert [p.name for p in pages] == ["1.png", "2.png"]
    assert not (tmp_path / "work" / LAYOUT).exists()


def test_a_strip_chapter_packs_back_into_its_own_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run, "session_of", fake_session)
    sources = strips(tmp_path / "source", (220, 280))
    archive = tmp_path / "chapter.zip"
    with zipfile.ZipFile(archive, "w") as packed:
        for path in sources:
            packed.write(path, path.name)
    out = io.StringIO()
    assert run.main(["detect", str(archive)], out) == 0
    work = Path(json.loads(out.getvalue())["work"])
    for notes in (work / "notes").glob("*.json"):
        notes.write_text("[]")

    out = io.StringIO()
    code = run.main(["pack", str(work), str(tmp_path / "chapter-english.zip")], out)

    assert code == 0
    with zipfile.ZipFile(tmp_path / "chapter-english.zip") as packed:
        assert packed.namelist() == ["1.png", "2.png", "3.png"]
        first = Image.open(io.BytesIO(packed.read("1.png"))).convert("RGB")
    assert np.array_equal(np.asarray(first), np.asarray(Image.open(sources[0]).convert("RGB")))


def test_a_banner_after_the_strip_stays_its_own_page_and_packs_back(tmp_path: Path) -> None:
    sources = strips(tmp_path / "source", (220, 280))
    banner = tmp_path / "source" / "4.png"
    Image.new("RGB", (60, 30), "red").save(banner)
    work = tmp_path / "work"

    pages = laid_out(work, [*sources, banner])
    back = cut_back(work, pages)

    assert json.loads((work / LAYOUT).read_text())["pages"][-1]["extra"] == "4.png"
    assert [name for name, _ in back] == ["1.png", "2.png", "3.png", "4.png"]
    assert back[-1][1].size == (60, 30)
