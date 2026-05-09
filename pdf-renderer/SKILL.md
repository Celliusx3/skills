---
name: pdf-renderer
description: Render a Markdown document to PDF and store it in the current agent run's artifact bucket. Use whenever the user asks for a memo, brief, report, one-pager, letter, or any printable document. The skill ships a `scripts/render.py` that parses Markdown via markdown-it-py and renders to PDF via reportlab (pure Python, no native deps — same library Anthropic's `anthropics/skills/skills/pdf` uses). The script uploads the PDF to the backend so the run-detail page can list it under Files. Output of the script is JSON containing `download_url` — surface that URL in your final answer.
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

What the script supports (markdown-it-py → reportlab Platypus):
- H1–H4 headings with proportional sizes
- Paragraphs, soft + hard line breaks
- **bold**, *italic*, ~~strike~~, `inline code`, [links](url)
- Bullet and numbered lists
- Code blocks (triple-backtick fenced blocks; rendered in monospace)
- Blockquotes (indented + greyed)
- GFM tables (header row + body, auto-wrapping cells)
- Horizontal rules
- The `<div class="page-break"></div>` sentinel (forces a new page)

Things reportlab handles less well than the WeasyPrint family used to:
- Complex CSS layouts (flexbox, grid) — N/A; the script renders
  Markdown to a flowing layout, not arbitrary HTML.
- Inline images by URL — not implemented; alt text is shown bracketed.
  If you need an image, embed via reportlab Canvas in a custom skill.

## When to read each reference

| File | Read when |
|---|---|
| `references/templates.md` | The user didn't specify a structure and you need a starting skeleton (memo / brief / report / letter / generic). |
| `references/recipes.md` | You need a specific Markdown construct — GFM table with right-aligned numbers, forced page break, footnote, blockquote, image, front-matter block. |

## What's fragile

- **Page breaks**: emit `<div class="page-break"></div>` on its own
  line (blank line above and below) when you need a forced break.
  The script recognises this sentinel and emits a `PageBreak`
  Flowable. Don't use other HTML or CSS for breaks — the renderer
  doesn't process arbitrary HTML.
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
uv pip install --system markdown-it-py reportlab httpx
```

All three are pure Python — no apt-level system libs needed. The
runner image stays a generic Python sandbox; future skills that want
different libraries declare their own `setup_command` without
touching the image.
