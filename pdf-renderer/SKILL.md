---
name: pdf-renderer
description: Render a Markdown document to PDF and store it in the current agent run's artifact bucket. Use whenever the user asks for a memo, brief, report, one-pager, letter, poster, or any printable document. The skill ships a `scripts/render.py` that renders Markdown via markdown-it-py + weasyprint and uploads the PDF to the backend so the run-detail page can list it under Files. Output of the script is JSON containing `download_url` — surface that URL in your final answer.
---

# pdf-renderer

The user asked for a printable document. Two steps:

1. **Author Markdown** that follows this skill's style guidance (see
   `references/templates.md` for document skeletons and
   `references/recipes.md` for Markdown patterns that render well in PDF).
2. **Call the renderer**:

   ```
   run_skill_script(
     name="pdf-renderer",
     script_path="scripts/render.py",
     args=["<your full markdown>", "<filename.pdf>", "<short title>"]
   )
   ```

   The script renders the Markdown to PDF in the sandbox via
   `weasyprint`, uploads the bytes to the backend's per-run artifact
   bucket, and prints a JSON envelope with `download_url`. Include
   that URL in your reply so the user can find the file.

The runtime infrastructure (per-run upload token, MinIO storage, etc.)
is handled by the runtime — you only need to write good Markdown and
call the script.

## When to read each reference

| File | Read when |
|---|---|
| `references/templates.md` | The user didn't specify a structure and you need a starting skeleton (memo / brief / report / letter / generic). |
| `references/recipes.md` | You need a specific Markdown construct — GFM table with right-aligned numbers, forced page break, footnote, blockquote, image, front-matter block. |

## What's fragile

- **Page breaks** are the one place HTML is required. WeasyPrint reads
  `<div class="page-break"></div>` (placed on its own line, blank line
  above and below) as a forced break. Other CSS strategies don't work
  without a custom stylesheet — use this sentinel.
- **Don't wrap the whole document in a code fence.** The renderer
  treats triple-backticks as a code block, so a wrapper would render
  the entire output verbatim with monospace font and no formatting.
- **Tone matches the brief.** A "casual one-pager" should not become a
  formal memo. The shape from `templates.md` is a scaffold; adapt
  voice and density to the input.
- **Don't fabricate facts.** If a number/date/name isn't in the brief,
  either ask in an *Open questions* section or omit it.

## Script env (FYI — already set by the runtime)

`scripts/render.py` reads three env vars the runtime injects at
sandbox spawn time:

- `RUN_ID` — the agent_run.id this artifact attaches to
- `ARTIFACT_UPLOAD_TOKEN` — short-lived upload token
- `BACKEND_URL` — internal URL the sandbox uses to reach the backend
  (e.g. `http://backend:4896`)

You don't need to set these — they're populated by the orchestrator
before the script runs. If the script returns a `missing required env
var` error, the runtime is misconfigured (raise it with the operator).

## Pip dependencies

The skill source's `setup_command` installs:

```
uv pip install --system markdown-it-py weasyprint httpx
```

The system libs WeasyPrint depends on (Cairo / Pango / GDK-Pixbuf /
libffi) are baked into the runner image so `pip install weasyprint`
works without root.
