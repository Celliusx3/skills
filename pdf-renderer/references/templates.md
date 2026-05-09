# Document templates

Concrete skeletons you can adapt. Pick the closest shape, fill it in, then
adjust headings/voice/density to match the user's brief.

## Contents

- [Generic structured document](#generic-structured-document)
- [Memo](#memo)
- [Brief / one-pager](#brief--one-pager)
- [Report](#report)
- [Letter](#letter)

These are scaffolds, not rules. Drop sections you don't need; add ones the
brief calls for. The H1 is the document title — keep exactly one.

---

## Generic structured document

Use when the brief is open-ended ("write me a doc about X").

```markdown
# {{ Title }}

**Date:** {{ ISO date }}
**Author:** {{ name or role }}

## Summary

One paragraph stating the headline conclusion.

## Background

Two or three short paragraphs of context.

## Detail

Subsections as needed. Use H3 for subsections, H4 sparingly.

## Open questions

- Anything the brief left unspecified
```

## Memo

Use when the brief is "memo / internal note / status update". Tighter and
more directive than a report.

```markdown
# Memo: {{ subject }}

**To:** {{ audience }}
**From:** {{ author }}
**Date:** {{ ISO date }}
**Re:** {{ one-line subject }}

## TL;DR

One sentence. The reader should be able to stop here and act.

## Context

A short paragraph of background.

## Proposal

What you're recommending or announcing. Bullet list works well here.

## Next steps

- Owner — action — due
- Owner — action — due
```

## Brief / one-pager

Use when the user asked for "a one-pager" or "a brief" — fits on one
printed page, prioritises scanning over reading.

```markdown
# {{ Headline / project name }}

**One-line pitch:** {{ what & why in a sentence }}

## Problem

Two or three bullets — what's broken or unmet.

## Approach

Two or three bullets — what we're going to do.

## Why now

One paragraph — what changed that makes this the right moment.

## What success looks like

- Concrete metric or outcome
- Concrete metric or outcome
```

## Report

Use when the brief asks for analysis or findings. Longer, more sectioned,
page breaks between major parts.

```markdown
# {{ Report title }}

**Period:** {{ start — end }}
**Prepared by:** {{ author }}
**Date:** {{ ISO date }}

## Executive summary

A paragraph plus 3–5 bullets. The reader should be able to stop here.

## Methodology

How the analysis was done. Sources, tools, assumptions.

<div class="page-break"></div>

## Findings

### Finding 1

Discussion + supporting table or chart.

### Finding 2

Discussion + supporting table or chart.

<div class="page-break"></div>

## Recommendations

Numbered list of actions with rationale.

1. Action — rationale.
2. Action — rationale.

## Appendix

Tables, raw data, or supporting detail.
```

## Letter

Use when the brief is "write a letter to {{ recipient }}".

```markdown
# {{ Title — usually omit the H1 for short letters; if omitted, the rendered PDF starts with the date }}

{{ ISO date }}

{{ Recipient name }}
{{ Recipient address line 1 }}
{{ Recipient address line 2 }}

Dear {{ recipient }},

Body — three or four short paragraphs. No headings inside a letter unless
it's very long.

Sincerely,

{{ Sender name }}
{{ Sender title }}
```
