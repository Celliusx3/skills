"""Models: fetched once, and only ever the file whose digest was pinned."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from comic_translator.models import Model, ModelError, fetched


def served(tmp_path: Path, content: bytes) -> str:
    source = tmp_path / "served.onnx"
    source.write_bytes(content)
    return source.as_uri()


def test_a_model_matching_its_pin_is_kept_and_not_fetched_again(tmp_path: Path) -> None:
    content = b"model"
    model = Model("m.onnx", served(tmp_path, content), hashlib.sha256(content).hexdigest())

    first = fetched(model, tmp_path / "cache")
    (tmp_path / "served.onnx").unlink()

    assert fetched(model, tmp_path / "cache") == first
    assert first.read_bytes() == content


def test_a_model_not_matching_its_pin_is_refused_and_removed(tmp_path: Path) -> None:
    model = Model("m.onnx", served(tmp_path, b"other"), hashlib.sha256(b"model").hexdigest())

    with pytest.raises(ModelError, match="not the file pinned"):
        fetched(model, tmp_path / "cache")

    assert not any((tmp_path / "cache").iterdir())
