"""The models the skill runs: each fetched once, pinned by its digest, and run on the CPU."""

from __future__ import annotations

import hashlib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

DOWNLOAD_SECONDS = 600
CHUNK = 1 << 20
THREADS = 2


class ModelError(RuntimeError):
    """A model that could not be fetched, or was not the file pinned."""


@dataclass(frozen=True)
class Model:
    name: str
    url: str
    sha256: str


TEXT_FINDER = Model(
    name="ppocr-v4-det.onnx",
    url="https://huggingface.co/SWHL/RapidOCR/resolve/1cfba2e90fc938db55889873735088de210cc173/PP-OCRv4/ch_PP-OCRv4_det_infer.onnx",
    sha256="d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9",
)

INPAINTER = Model(
    name="lama-fp32.onnx",
    url="https://huggingface.co/Carve/LaMa-ONNX/resolve/c3c0c9e468934d62e79c329e35d82dd09ff8c444/lama_fp32.onnx",
    sha256="1faef5301d78db7dda502fe59966957ec4b79dd64e16f03ed96913c7a4eb68d6",
)


class Session(Protocol):
    def run(
        self, outputs: None, feeds: dict[str, NDArray[np.generic]]
    ) -> list[NDArray[np.generic]]: ...


def cache_folder() -> Path:
    return Path.home() / ".cache" / "comic-translator"


def fetched(model: Model, folder: Path) -> Path:
    """The model's file in `folder`, fetched the first time; refused unless its digest matches."""
    path = folder / model.name
    if path.is_file():
        return path
    folder.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    digest = hashlib.sha256()
    with (
        urllib.request.urlopen(model.url, timeout=DOWNLOAD_SECONDS) as reply,
        partial.open("wb") as out,
    ):
        for chunk in iter(lambda: reply.read(CHUNK), b""):
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest() != model.sha256:
        partial.unlink()
        raise ModelError(f"{model.url} is not the file pinned for {model.name}; not used")
    partial.replace(path)
    return path


def session_of(model: Model, folder: Path) -> Session:
    """The model ready to run on this machine's CPU with THREADS threads."""
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = THREADS
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False
    options.enable_mem_pattern = False
    path = fetched(model, folder)
    return onnxruntime.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
