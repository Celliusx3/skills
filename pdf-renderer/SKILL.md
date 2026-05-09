---
name: pdf-renderer
description: Author Markdown that will be rendered to PDF by the cellstudio canvas MARKDOWN_TO_PDF node (markdown-it-py + WeasyPrint). Use whenever the user asks for a memo, brief, report, one-pager, letter, or any printable document and the downstream node is MARKDOWN_TO_PDF. The skill provides patterns for headings, tables, page breaks, and a few document skeletons; it does not render the PDF itself. Output is plain Markdown only.
---

# pdf-renderer

The user asked for a printable document. Downstream a `MARKDOWN_TO_PDF` node
will pipe whatever Markdown you emit through markdown-it-py → HTML →
WeasyPrint → a PDF file. Your job is to produce the Markdown.

## Quick start

1. Read the user's brief and pick a shape from `references/templates.md`
   (memo, brief, report, letter, generic). When in doubt, use *generic*.
2. Skim `references/recipes.md` for the specific Markdown patterns you need
   (tables, page breaks, footnotes). Most short documents only need
   headings + paragraphs + lists.
3. Emit Markdown directly. No preamble like *"Here is your document"*. No
   triple-backtick wrapper around the whole thing.

## When to read each reference

| File | Read when |
|---|---|
| `references/templates.md` | The user didn't specify a structure and you need a starting skeleton. |
| `references/recipes.md` | You need a specific Markdown construct — table with right-aligned numbers, forced page break, footnote, page header/footer, image, blockquote. |

## What's fragile (read this even if you skip the references)

- **Page breaks** are the one place HTML is required. WeasyPrint reads
  `<div class="page-break"></div>` (placed on its own line, blank line above
  and below) as a forced break. Other CSS strategies don't work without a
  custom stylesheet — use this sentinel.
- **Don't wrap the whole document in a code fence.** The renderer treats
  triple-backticks as a code block, so a wrapper would render the entire
  output verbatim with monospace font and no formatting.
- **Tone matches the brief.** A "casual one-pager" should not become a
  formal memo. The shape from `templates.md` is a scaffold; adapt voice and
  density to the input.
- **Don't fabricate facts.** If a number/date/name isn't in the brief,
  either ask in an *Open questions* section or omit it.

## Output contract

Plain Markdown, UTF-8, ready to paste into the rendering pipeline. The only
hard constraints are the two bullets above (page-break sentinel; no outer
code fence). Heading hierarchy, table layout, list style — pick whatever
serves the document.
