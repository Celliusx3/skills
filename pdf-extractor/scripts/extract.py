#!/usr/bin/env python3
"""pdf-extractor/scripts/extract.py — fetch a PDF artifact and extract text.

Usage (called by `run_skill_script`):
    python extract.py <artifact_id>

The single positional arg is the artifact_id (UUID) of a PDF previously
uploaded to the current run's artifact bucket. The script:

  1. GETs `${BACKEND_URL}/api/v1/agent-runs/${RUN_ID}/artifacts/<id>` to
     stream the PDF bytes back.
  2. Opens it with `pdfplumber` and concatenates `page.extract_text()`
     across pages, joined by a `--- page N ---` sentinel.
  3. Detects scanned PDFs (every page extracts to whitespace) and exits
     non-zero with the canonical "chain a vision LLM" hint.
  4. Prints a JSON envelope to stdout. The LLM's tool result will
     contain that JSON.

Required env (set by the orchestrator at sandbox spawn time):
  RUN_ID      — the agent_run.id this artifact belongs to
  BACKEND_URL — compose-internal URL (e.g. http://backend:4896)

Required pip deps (declared via the skill source's setup_command):
  pdfplumber, httpx

No apt-level deps — pdfplumber is pure-ish Python (depends on
pdfminer.six, also pure Python).
"""
from __future__ import annotations

import io
import json
import os
import sys

import httpx
import pdfplumber

_SCANNED_HINT = (
    "PDF has no text layer \u2014 looks like a scan. Convert to a text PDF "
    "or chain an LLM_AGENT (configured with a vision-capable model + a "
    "transcription prompt + max_turns=1) before this node."
)


def _fetch_pdf(*, backend_url: str, run_id: str, artifact_id: str) -> bytes:
    url = (
        f"{backend_url.rstrip('/')}/api/v1/agent-runs/{run_id}"
        f"/artifacts/{artifact_id}"
    )
    with httpx.Client(timeout=60.0) as client:
        response = client.get(url)
    if response.status_code != 200:
        raise RuntimeError(
            f"artifact fetch failed: HTTP {response.status_code}: "
            f"{response.text}",
        )
    return response.content


def _extract_text(pdf_bytes: bytes) -> tuple[str, int, bool]:
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    page_count = len(pages)
    has_text_layer = any(p.strip() for p in pages)
    if not has_text_layer:
        return "", page_count, False
    body = "\n\n".join(
        f"--- page {i + 1} ---\n\n{text.rstrip()}"
        for i, text in enumerate(pages)
    )
    return body, page_count, True


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing artifact_id arg"}), file=sys.stderr)
        return 2
    artifact_id = sys.argv[1].strip()
    if not artifact_id:
        print(json.dumps({"error": "artifact_id is empty"}), file=sys.stderr)
        return 2

    try:
        run_id = os.environ["RUN_ID"]
        backend_url = os.environ["BACKEND_URL"]
    except KeyError as exc:
        print(
            json.dumps({"error": f"missing required env var {exc.args[0]!r}"}),
            file=sys.stderr,
        )
        return 3

    try:
        pdf_bytes = _fetch_pdf(
            backend_url=backend_url,
            run_id=run_id,
            artifact_id=artifact_id,
        )
    except Exception as exc:
        print(
            json.dumps({"error": f"fetch failed: {type(exc).__name__}: {exc}"}),
            file=sys.stderr,
        )
        return 4

    try:
        text, page_count, has_text_layer = _extract_text(pdf_bytes)
    except Exception as exc:
        print(
            json.dumps(
                {"error": f"extract failed: {type(exc).__name__}: {exc}"},
            ),
            file=sys.stderr,
        )
        return 5

    if not has_text_layer:
        print(json.dumps({"error": _SCANNED_HINT}), file=sys.stderr)
        return 6

    print(json.dumps({
        "text": text,
        "page_count": page_count,
        "has_text_layer": True,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
