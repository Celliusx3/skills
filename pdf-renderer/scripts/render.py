#!/usr/bin/env python3
"""pdf-renderer/scripts/render.py — render Markdown to PDF and upload.

Usage (called by `run_skill_script`):
    python render.py "<markdown>" [filename] [title]

The first positional arg is the Markdown body (or `-` to read from
stdin). `filename` defaults to `document.pdf`; `title` defaults to the
filename's stem. The script:

  1. Renders Markdown → HTML via `markdown-it-py` (GFM-like).
  2. Renders HTML → PDF bytes via `weasyprint` (in-process, no
     network call).
  3. POSTs `multipart` to the backend's internal artifact endpoint
     (`$BACKEND_URL/api/v1/internal/artifacts`) with the
     `X-Artifact-Token` header. The backend validates the token,
     stores both the PDF and the source Markdown in MinIO, inserts
     a row in `agent_run_artifact`, and returns metadata.
  4. Prints the response JSON to stdout. The LLM's tool result will
     contain that JSON; the model is expected to extract the
     `download_url` and surface it to the user.

Required env (set by the orchestrator at sandbox spawn time):
  RUN_ID                  — int, the agent_run.id this artifact belongs to
  ARTIFACT_UPLOAD_TOKEN   — short-lived per-run upload token
  BACKEND_URL             — compose-internal URL (e.g. http://backend:4896)

Required pip deps (declared via the skill source's setup_command —
`uv pip install --system markdown-it-py weasyprint httpx`):
  markdown-it-py, weasyprint, httpx

Required apt deps (already in the runner image):
  libcairo2, libpango-1.0-0, libpangoft2-1.0-0,
  libgdk-pixbuf2.0-0, libffi8, shared-mime-info
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from markdown_it import MarkdownIt
from weasyprint import CSS, HTML

_DEFAULT_CSS = """
@page { size: A4; margin: 2cm; }
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif;
       font-size: 11pt; line-height: 1.5; color: #111; }
h1 { font-size: 20pt; }
h2 { font-size: 16pt; margin-top: 1em; }
h3 { font-size: 13pt; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 0.4em 0.6em; }
th { background: #f5f5f5; }
.page-break { page-break-before: always; }
code { background: #f5f5f5; padding: 0.1em 0.3em; border-radius: 3px;
       font-family: ui-monospace, "SF Mono", Menlo, monospace;
       font-size: 0.9em; }
pre { background: #f5f5f5; padding: 0.8em; border-radius: 4px;
      overflow-x: auto; }
blockquote { border-left: 3px solid #ddd; padding-left: 1em;
             color: #555; }
"""


def _read_markdown(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    return arg


def _render_pdf(markdown: str) -> bytes:
    md = MarkdownIt("gfm-like", {"html": True, "breaks": False})
    html_body = md.render(markdown)
    html_doc = (
        "<html><head><meta charset='utf-8'></head>"
        f"<body>{html_body}</body></html>"
    )
    pdf_bytes = HTML(string=html_doc).write_pdf(
        stylesheets=[CSS(string=_DEFAULT_CSS)],
    )
    return pdf_bytes


def _upload(
    *,
    backend_url: str,
    token: str,
    run_id: str,
    filename: str,
    title: str,
    pdf_bytes: bytes,
    source_markdown: str,
) -> dict[str, object]:
    url = f"{backend_url.rstrip('/')}/api/v1/internal/artifacts"
    files = {
        "pdf": (filename, pdf_bytes, "application/pdf"),
        "source_md": ("source.md", source_markdown.encode("utf-8"),
                      "text/markdown"),
    }
    data = {
        "run_id": run_id,
        "node_id": os.environ.get("NODE_ID", "agent"),
        "filename": filename,
        "title": title,
        "mime_type": "application/pdf",
    }
    headers = {"X-Artifact-Token": token}
    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, files=files, data=data, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(
            f"upload failed: HTTP {response.status_code}: {response.text}",
        )
    return response.json()


def main() -> int:
    if len(sys.argv) < 2:
        print(
            json.dumps({"error": "missing markdown arg"}),
            file=sys.stderr,
        )
        return 2
    markdown = _read_markdown(sys.argv[1])
    if not markdown.strip():
        print(
            json.dumps({"error": "markdown is empty"}),
            file=sys.stderr,
        )
        return 2
    filename = sys.argv[2] if len(sys.argv) >= 3 else "document.pdf"
    title = sys.argv[3] if len(sys.argv) >= 4 else Path(filename).stem

    try:
        run_id = os.environ["RUN_ID"]
        token = os.environ["ARTIFACT_UPLOAD_TOKEN"]
        backend_url = os.environ["BACKEND_URL"]
    except KeyError as exc:
        print(
            json.dumps({"error": f"missing required env var {exc.args[0]!r}"}),
            file=sys.stderr,
        )
        return 3

    try:
        pdf_bytes = _render_pdf(markdown)
    except Exception as exc:
        print(
            json.dumps({"error": f"render failed: {type(exc).__name__}: {exc}"}),
            file=sys.stderr,
        )
        return 4

    try:
        result = _upload(
            backend_url=backend_url,
            token=token,
            run_id=run_id,
            filename=filename,
            title=title,
            pdf_bytes=pdf_bytes,
            source_markdown=markdown,
        )
    except Exception as exc:
        print(
            json.dumps({"error": f"upload failed: {type(exc).__name__}: {exc}"}),
            file=sys.stderr,
        )
        return 5

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
