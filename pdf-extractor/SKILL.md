---
name: pdf-extractor
description: Extract text from a born-digital PDF that has already been uploaded to the current run's artifact bucket. The skill ships a `scripts/extract.py` that fetches the PDF by `artifact_id`, parses its text layer with `pdfplumber` (MIT, no native deps), and prints a JSON envelope `{"text": "...", "page_count": N, "has_text_layer": bool}`. Use whenever the LLM needs the textual contents of a PDF (invoices, statements, reports) and a non-vision model is in the loop. Fails loud on scanned PDFs (no text layer) — chain a vision LLM upstream for transcription if you need OCR.
---

# pdf-extractor

The user uploaded a PDF and you need its text content. One step:

```
run_skill_script(
  name="pdf-extractor",
  script_path="scripts/extract.py",
  args=["<artifact_id>"]
)
```

`<artifact_id>` is the UUID returned by an earlier upload (e.g. from
`pdf-renderer` or any node that POSTed to `/api/v1/internal/artifacts`).
The script fetches the PDF bytes from
`${BACKEND_URL}/api/v1/internal/artifacts/<artifact_id>`, sending the
per-run `${ARTIFACT_UPLOAD_TOKEN}` as `X-Artifact-Token`. The backend
307s to a presigned MinIO URL; httpx follows it transparently. The
script then parses the text layer with `pdfplumber` and prints JSON.

## Output shape

On success (stdout, exit 0):

```json
{
  "text": "<concatenated text, page-separated by '\\n\\n--- page 2 ---\\n\\n'>",
  "page_count": 3,
  "has_text_layer": true
}
```

On a scanned PDF (stderr, exit 6):

```json
{"error": "PDF has no text layer — looks like a scan. Convert to a text PDF or chain an LLM_AGENT (configured with a vision-capable model + a transcription prompt + max_turns=1) before this node."}
```

The LLM should surface the extracted `text` to the next reasoning step and
ignore `page_count` / `has_text_layer` unless they're relevant.

## When NOT to use

- **Scanned PDFs / images of text** — pdfplumber only reads embedded text
  layers. For scans, use a vision LLM_AGENT (Anthropic / GPT-4o) with a
  transcription prompt and `max_turns=1`. That's a one-LLM-call OCR step.
- **PDFs that haven't been uploaded as artifacts yet** — the skill only
  fetches by artifact_id. If you have raw bytes from `DRIVE_DOWNLOAD_FILE`,
  upload them first via the internal artifact endpoint (the same path
  `pdf-renderer` uses to upload its own output), then call this skill with
  the resulting id.
- **PDFs you got natively as multimodal blocks** — Anthropic models can
  read PDF content directly. If your LLM_AGENT credential is Anthropic and
  the file is small enough, skip this skill and let the model see the PDF
  natively.

## What's fragile

- **Encrypted / password-protected PDFs.** pdfplumber will refuse them.
  The script surfaces the underlying error verbatim — the LLM can detect
  this in the `error` field and ask the user for an unprotected copy.
- **PDFs with embedded fonts that map characters to glyph indices instead
  of Unicode.** Text comes out garbled. There's no fix at extraction time;
  fall back to a vision LLM transcription.
- **Page-separator format.** Pages are joined by `\n\n--- page N ---\n\n`.
  If you need pages individually, split on that sentinel.

## Script env (FYI — already set by the runtime)

`scripts/extract.py` reads two env vars the runtime injects at sandbox
spawn time:

- `RUN_ID` — the agent_run.id this artifact belongs to
- `BACKEND_URL` — internal URL the sandbox uses to reach the backend
  (e.g. `http://backend:4896`)

You don't need to set these — they're populated by the orchestrator before
the script runs. If the script returns a `missing required env var` error,
the runtime is misconfigured (raise it with the operator).

## Pip dependencies

The skill source's `setup_command` installs:

```
uv pip install --system pdfplumber httpx
```

`pdfplumber` is MIT-licensed and pure-ish Python (depends on `pdfminer.six`
which is also MIT). No system libraries needed.
