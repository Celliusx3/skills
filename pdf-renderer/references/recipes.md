# Markdown recipes for PDF rendering

Pattern reference for the constructs that need attention when the output
is going through markdown-it-py → HTML → WeasyPrint.

## Contents

- [Headings](#headings)
- [Tables](#tables)
- [Forced page breaks](#forced-page-breaks)
- [Lists](#lists)
- [Code blocks](#code-blocks)
- [Blockquotes and callouts](#blockquotes-and-callouts)
- [Footnotes](#footnotes)
- [Links](#links)
- [Images](#images)
- [Front-matter blocks](#front-matter-blocks)

---

## Headings

```markdown
# Title (one per document)

## Major section

### Subsection

#### Sub-subsection (use sparingly)
```

H1 once at the top. H2 for major sections. H3 for subsections. H4 only when
the document is long enough to warrant a fourth level (rare).

## Tables

GitHub-flavored Markdown tables work as expected. Right-align numeric
columns with `---:` so figures line up:

```markdown
| Account              | Debit       | Credit      |
|----------------------|------------:|------------:|
| Cash                 |   12,500.00 |           — |
| Trade receivables    |    3,400.00 |           — |
| Sales                |           — |   15,900.00 |
```

Keep tables to ~6 columns wide so they fit a portrait page. For wider
data, either split into two tables or use landscape orientation (requires
a custom CSS via the `css` field on `MARKDOWN_TO_PDF`).

## Forced page breaks

WeasyPrint's reliable trigger is an inline `<div>` with the `page-break`
class. The default stylesheet shipped by `pdf-service` maps that to
`page-break-before: always`.

```markdown
... end of section A ...

<div class="page-break"></div>

## Section B starts on a new page
```

Place the sentinel on its own line with blank lines above and below.
Between H2 sections in long documents, not before the first or after the
last section.

## Lists

```markdown
- Unordered with hyphens
- Don't mix `*` and `-` in the same list

1. Ordered with `1. `
2. Markdown auto-numbers, so all items can be `1. ` if you prefer
```

Nest with two-space indents:

```markdown
- Parent item
  - Child item
  - Another child
```

## Code blocks

Triple-backtick fenced blocks with a language tag render as monospace
with a light background:

```markdown
```python
def main(inputs):
    return inputs[0].value
```
```

For inline code, use single backticks: `` `inputs[0].value` ``.

## Blockquotes and callouts

```markdown
> A regular blockquote — renders as left-bordered indented italic-ish text.
> Continue with `> ` on each line.
```

For a callout-style block, prefix with bold marker:

```markdown
> **Note** — the marker text is your callout label; the rest is the body.
```

## Footnotes

markdown-it-py supports `[^id]` reference-style footnotes:

```markdown
This claim has a citation.[^src]

[^src]: Source of the citation, page 3.
```

Footnotes render at the bottom of the page (or end of document, depending
on stylesheet). Use sparingly — long inline references are usually
clearer.

## Links

```markdown
[anchor text](https://example.com)
```

Render as clickable in the PDF. Auto-linked bare URLs work too
(`https://example.com`) but explicit anchor text reads better.

## Images

Only if the user provided a URL or upstream payload supplies one:

```markdown
![alt text](https://example.com/image.png)
```

Don't invent placeholder URLs — broken images render as a missing-image
icon.

## Front-matter blocks

A short paragraph of `**Key:** value` lines after the H1 substitutes for
YAML front matter (Markdown YAML doesn't render):

```markdown
# Document title

**Date:** 2026-05-09
**Author:** Engineering
**Status:** Draft

## First section ...
```

Trailing two spaces force a `<br>` line break inside the paragraph so each
key/value lands on its own line in the PDF.
