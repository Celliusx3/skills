# Celliusx3/skills

Anthropic-format Agent Skills used by the cellstudio investment canvas runtime.

Each subfolder is one skill, following the
[Anthropic Agent Skills](https://docs.anthropic.com/en/docs/agent-skills) layout:

- `SKILL.md` — YAML frontmatter (`name`, `description`) + body (when to use, style rules, examples)
- `references/` — supporting files the skill body links to (templates, data)
- `scripts/` — optional executable Python (run via `run_skill_script`)

## Skills

| Name | Purpose |
|---|---|
| [`comic-translator`](./comic-translator/SKILL.md) | Translate comic, manga, manhwa or webtoon pages in place: `scripts/run.py detect` finds the text and makes enlarged, numbered box sheets to read it from; the agent writes each entry's translation into the page's notes; `render` erases the original lettering and letters the translation. Runs with `uv`; fetches two ONNX models (~215 MB) on first use. |
| [`pdf-renderer`](./pdf-renderer/SKILL.md) | Author Markdown that renders cleanly to PDF via the canvas `MARKDOWN_TO_PDF` node. Provides document templates (memo, brief, report, letter) and Markdown recipes (tables, page breaks, footnotes). The skill does not render the PDF itself — rendering is a separate canvas node. |

## Installing into the canvas

```bash
curl -X POST http://127.0.0.1:4896/api/v1/skills/sources \
  -H "content-type: application/json" \
  -d '{"source_uri":"https://github.com/Celliusx3/skills","subdir":null,"auto_refresh":false}'

```

The response includes the new `source.id` — use that as the `skill_source_id`
on any `AGENT_SKILLS` canvas node.
