#!/usr/bin/env python3
"""pdf-renderer/scripts/render.py — render Markdown to PDF and upload.

Usage (called by `run_skill_script`):
    python render.py "<markdown>" [filename] [title]

The first positional arg is the Markdown body (or `-` to read from
stdin). `filename` defaults to `document.pdf`; `title` defaults to the
filename's stem.

The script:

  1. Parses Markdown to an AST via `markdown-it-py`.
  2. Walks the token stream and emits `reportlab` Platypus
     Flowables (Paragraph / Spacer / Table / Preformatted /
     ListFlowable). PDF is built in-process — no native deps.
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
`uv pip install --system markdown-it-py reportlab httpx`):
  markdown-it-py, reportlab, httpx

No apt-level deps: reportlab is pure Python (no Cairo/Pango/etc.).
This mirrors Anthropic's own `anthropics/skills/skills/pdf` choice.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx
from markdown_it import MarkdownIt
from markdown_it.token import Token
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ---- Styles -----------------------------------------------------------------

def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        spaceAfter=6,
        alignment=TA_LEFT,
    )
    return {
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=20, leading=24, spaceBefore=8, spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=16, leading=20, spaceBefore=10, spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "H3", parent=base["Heading3"], fontName="Helvetica-Bold",
            fontSize=13, leading=17, spaceBefore=8, spaceAfter=4,
        ),
        "h4": ParagraphStyle(
            "H4", parent=base["Heading4"], fontName="Helvetica-Bold",
            fontSize=11, leading=15, spaceBefore=6, spaceAfter=4,
        ),
        "body": body,
        "blockquote": ParagraphStyle(
            "Blockquote", parent=body, leftIndent=18, textColor=colors.HexColor("#555"),
            borderPadding=0,
        ),
        "code_inline": "Courier",
    }


_TABLE_STYLE = TableStyle([
    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbb")),
    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#ddd")),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 10),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ("TOPPADDING", (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
])


# ---- Inline rendering -------------------------------------------------------

_RL_TAG_OPEN = {"strong": "<b>", "em": "<i>", "s": "<strike>"}
_RL_TAG_CLOSE = {"strong": "</b>", "em": "</i>", "s": "</strike>"}


def _escape_inline(text: str) -> str:
    """Escape characters that reportlab's mini-HTML treats specially."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _render_inline(children: Iterable[Token]) -> str:
    """Walk the inline token stream and produce reportlab-compatible
    mini-HTML (a subset that `Paragraph` understands)."""
    parts: list[str] = []
    for token in children:
        t = token.type
        if t == "text":
            parts.append(_escape_inline(token.content))
        elif t == "softbreak":
            parts.append(" ")
        elif t == "hardbreak":
            parts.append("<br/>")
        elif t == "code_inline":
            parts.append(
                f'<font face="Courier" size="10" backColor="#f5f5f5">'
                f'{_escape_inline(token.content)}</font>',
            )
        elif t == "link_open":
            href = token.attrGet("href") or ""
            parts.append(f'<link href="{_escape_inline(href)}" color="#1155cc">')
        elif t == "link_close":
            parts.append("</link>")
        elif t in _RL_TAG_OPEN:
            parts.append(_RL_TAG_OPEN[t])
        elif t in _RL_TAG_CLOSE:
            parts.append(_RL_TAG_CLOSE[t])
        elif t == "image":
            alt = token.content or "image"
            parts.append(f"[{_escape_inline(alt)}]")
        # Unknown inline tokens fall through silently — keeps the
        # renderer robust to markdown-it extensions we don't model.
    return "".join(parts)


# ---- Block rendering --------------------------------------------------------

_PAGE_BREAK_RE = re.compile(
    r'^\s*<div\s+class=["\']page-break["\']>\s*</div>\s*$',
    re.IGNORECASE,
)


def _build_flowables(markdown: str) -> list[Any]:
    md = MarkdownIt("gfm-like", {"html": True, "breaks": False})
    tokens = md.parse(markdown)
    styles = _build_styles()
    flowables: list[Any] = []

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            level = int(tok.tag[1])  # h1..h6
            inline = tokens[i + 1]
            style_name = (
                "h1" if level == 1
                else "h2" if level == 2
                else "h3" if level == 3
                else "h4"
            )
            text = _render_inline(inline.children or [])
            flowables.append(Paragraph(text, styles[style_name]))
            i += 3  # heading_open, inline, heading_close
        elif tok.type == "paragraph_open":
            inline = tokens[i + 1]
            text = _render_inline(inline.children or [])
            # Look for the page-break sentinel and emit a real PageBreak.
            if _PAGE_BREAK_RE.match(inline.content or ""):
                flowables.append(PageBreak())
            elif text.strip():
                flowables.append(Paragraph(text, styles["body"]))
            i += 3  # paragraph_open, inline, paragraph_close
        elif tok.type == "bullet_list_open":
            consumed, list_flowable = _consume_list(
                tokens, i, styles, ordered=False,
            )
            flowables.append(list_flowable)
            flowables.append(Spacer(1, 4))
            i = consumed
        elif tok.type == "ordered_list_open":
            consumed, list_flowable = _consume_list(
                tokens, i, styles, ordered=True,
            )
            flowables.append(list_flowable)
            flowables.append(Spacer(1, 4))
            i = consumed
        elif tok.type == "fence" or tok.type == "code_block":
            content = tok.content.rstrip()
            flowables.append(Preformatted(
                content, ParagraphStyle(
                    "Code", fontName="Courier", fontSize=9, leading=12,
                    leftIndent=8, rightIndent=8,
                    backColor=colors.HexColor("#f5f5f5"),
                    borderPadding=4, spaceBefore=4, spaceAfter=8,
                ),
            ))
        elif tok.type == "blockquote_open":
            consumed, quote_flowable = _consume_blockquote(tokens, i, styles)
            flowables.append(quote_flowable)
            i = consumed
            continue
        elif tok.type == "table_open":
            consumed, table = _consume_table(tokens, i)
            flowables.append(table)
            flowables.append(Spacer(1, 6))
            i = consumed
            continue
        elif tok.type == "hr":
            flowables.append(Spacer(1, 6))
            flowables.append(Paragraph(
                '<hr width="100%" thickness="0.5" color="#ccc"/>',
                styles["body"],
            ))
            flowables.append(Spacer(1, 6))
        elif tok.type == "html_block":
            # Recognise the page-break sentinel inside an HTML block too.
            if _PAGE_BREAK_RE.match((tok.content or "").strip()):
                flowables.append(PageBreak())
        # Unknown block tokens fall through silently.
        i += 1

    return flowables


def _consume_list(
    tokens: list[Token],
    start: int,
    styles: dict[str, Any],
    *,
    ordered: bool,
) -> tuple[int, ListFlowable]:
    """Walk `bullet_list_open` … `bullet_list_close` (or ordered) and
    return the matching ListFlowable + the index *after* the close."""
    items: list[ListItem] = []
    i = start + 1
    while i < len(tokens) and tokens[i].type not in (
        "bullet_list_close", "ordered_list_close",
    ):
        if tokens[i].type == "list_item_open":
            # Capture inline content of the first paragraph inside the
            # list item. Nested blocks are simplified to a single
            # Paragraph for now.
            j = i + 1
            text = ""
            while j < len(tokens) and tokens[j].type != "list_item_close":
                if tokens[j].type == "paragraph_open":
                    inline = tokens[j + 1]
                    text = _render_inline(inline.children or [])
                    j += 3
                    continue
                j += 1
            items.append(ListItem(
                Paragraph(text, styles["body"]),
                leftIndent=14,
            ))
            i = j
        i += 1

    bullet_type = "1" if ordered else "bullet"
    flowable = ListFlowable(
        items, bulletType=bullet_type, leftIndent=18,
        bulletFontName="Helvetica", bulletFontSize=11,
    )
    return i + 1, flowable


def _consume_blockquote(
    tokens: list[Token],
    start: int,
    styles: dict[str, Any],
) -> tuple[int, Paragraph]:
    """Walk `blockquote_open` … `blockquote_close` and produce a
    single indented paragraph (joined by line breaks)."""
    parts: list[str] = []
    i = start + 1
    while i < len(tokens) and tokens[i].type != "blockquote_close":
        if tokens[i].type == "paragraph_open":
            inline = tokens[i + 1]
            parts.append(_render_inline(inline.children or []))
            i += 3
            continue
        i += 1
    text = "<br/>".join(parts) or "&nbsp;"
    return i + 1, Paragraph(text, styles["blockquote"])


def _consume_table(
    tokens: list[Token],
    start: int,
) -> tuple[int, Table]:
    """Walk `table_open` … `table_close` and produce a reportlab Table."""
    rows: list[list[str]] = []
    current: list[str] = []
    i = start + 1
    while i < len(tokens) and tokens[i].type != "table_close":
        t = tokens[i].type
        if t == "tr_open":
            current = []
        elif t in ("td_open", "th_open"):
            inline = tokens[i + 1]
            current.append(_render_inline(inline.children or []))
            i += 3
            continue
        elif t == "tr_close":
            rows.append(current)
            current = []
        i += 1

    # Wrap each cell in a Paragraph so the cell can wrap on width.
    body_style = ParagraphStyle(
        "Cell", fontName="Helvetica", fontSize=10, leading=12,
    )
    paragraph_rows = [
        [Paragraph(cell or "&nbsp;", body_style) for cell in row]
        for row in rows
    ]
    table = Table(paragraph_rows, hAlign="LEFT")
    table.setStyle(_TABLE_STYLE)
    return i + 1, table


# ---- Build + upload ---------------------------------------------------------

def _render_pdf(markdown: str, title: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=title,
    )
    flowables = _build_flowables(markdown)
    if not flowables:
        flowables = [Paragraph("(empty document)", _build_styles()["body"])]
    doc.build(flowables)
    return buffer.getvalue()


def _read_markdown(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    return arg


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
        pdf_bytes = _render_pdf(markdown, title)
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
