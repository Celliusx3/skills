---
name: comic-translator
description: Translates the text in comic, manga or webtoon pages into another language, in place, erasing the original lettering and lettering the translation. Use when the person shares comic pages, an image or a .zip/.cbz chapter, and asks for a translation.
compatibility: Requires running shell commands with uv, viewing image files, internet access once to fetch its models (about 215 MB), and about 1.5 GB of free memory while rendering.
---

# Comic translator

## Available scripts

- **`scripts/run.py`**: `detect` finds the text on every page and writes a work
  folder; `render` erases each entry's text and letters its translation.
  `--help` shows both. Each prints one JSON object, or one line starting
  `error:` that says what to fix.

Run each command below exactly as written, from this skill's folder. Do not
modify it, read the scripts, or copy them: the folder may be read-only, and
`uv run scripts/run.py` writes nothing there.

The scripts run with `uv`. If `uv` is not found, ask the person whether to
install it, and only on their yes run
`curl -LsSf https://astral.sh/uv/install.sh | sh`. It installs to
`~/.local/bin/uv`, which is not on the search path, so in every command
below write `~/.local/bin/uv` where it says `uv`.

## Workflow

Progress:
- [ ] 1. Detect
- [ ] 2. Read and edit the notes, one page at a time
- [ ] 3. Render and check
- [ ] 4. Hand over

1. **Detect**, giving the image or the `.zip`/`.cbz` as it is:
   ```bash
   cd "<this skill's folder>" && uv run scripts/run.py detect "<page image or archive>"
   ```
   It makes a work folder beside the input holding, for each page:
   - `notes/<page>.json`: the entries to edit, one per piece of text found;
   - `overview/<page>.jpg`: the whole page small, every entry in a numbered
     red box;
   - `boxes/<page>-<n>.jpg`: each entry's box cut out, with a little of what
     is round it, enlarged and numbered;
   - `review/<page>-<n>.jpg`: the page in full-size stretches, with a ruler
     along the top and left whose numbers are page pixels, as the boxes are.

   Running it again keeps notes already in the work folder.
2. **Read and edit**, one page at a time: the overview for where each box
   sits, then the page's `boxes` sheets to read the text. The number on a box
   is the entry with that `id` in the page's notes. Open a `review` stretch
   only for a closer look round a box, or to find text no box holds. Finish a
   page's notes before opening the next page's images. In each entry:
   - `original`: the text in the box exactly as it reads;
   - `translation`: it in the language the person asked for (English when
     they don't say), punctuated as that language does;
   - keep the entry for what sits in a speech bubble, a burst or a caption,
     sounds too, with `translation` the same as `original` when it already
     reads right, so it is lettered like the rest of the page;
   - delete the entry to leave its text as it is: sound effects drawn
     straight on the art, outlined or not, signs, watermarks, credits, or a
     box with no text;
   - text no box holds: add an entry with a new `id`;
   - text written in columns, or a right-to-left target language: add
     `"direction": "vertical"` or `"rtl"`.

   An entry before and after editing; only `original` and `translation`
   change, and `box` stays as detect wrote it:
   ```json
   {"id": 2, "box": {"left": 330, "top": 50, "right": 470, "bottom": 120}, "original": "", "translation": ""}
   {"id": 2, "box": {"left": 330, "top": 50, "right": 470, "bottom": 120}, "original": "...y el toque final.", "translation": "...and the final touch."}
   ```
3. **Render and check**:
   ```bash
   cd "<this skill's folder>" && uv run scripts/run.py render "<work folder>"
   ```
   It checks every notes file, then translates each page from its original.
   Each page's `warnings` name a box now far from where detect found its
   text, with the box detect found: fix those first. Then look at the
   `result-boxes/<page>-<n>.jpg` sheets, each box cut from the translated
   page (a `result` stretch for a closer look). Where text is left over, a
   box reached onto the art, or a translation reads badly, edit the notes and
   render again, until every page is clean. A piece of text still not clean
   after you changed its entry twice: delete its entry, and say so in your
   answer.
4. **Hand over**, in two steps:
   - zip the translated pages in page order next to the input, named as it
     with the target language's English name before its extension, as
     `chapter.zip` translated to English becomes `chapter-english.zip`:
     ```bash
     cd "<work folder>/translated" && python3 -m zipfile -c "<input's folder>/<input's name>-<language>.zip" *
     ```
   - send that zip to the person with your tool for giving them a file, then
     write your answer.

## Gotchas

- Detect and render take minutes on a long chapter. When your shell says a
  command is still running, wait for it the way your shell says to; sending
  it again changed (as with a longer timeout) starts a second copy.
- A translation keeps the original's case: words in capitals stay in
  capitals (`¡NO! Ni se te ocurra.` is `NO! Don't even think about it.`).
- A sound inside a bubble is translated (`¡COF, COF!` is `COUGH, COUGH!`). A
  sound effect drawn on the art (`SHH SHH`, `PLOP`) is left alone by deleting
  its entry: an entry kept, even with the same text, is erased and lettered
  again in plain type.
- Read the text yourself from the `boxes` sheets. Do not install OCR or other
  packages to read it: they are large downloads, and the sheets are enlarged
  for reading.
- A box must hold every mark of its text, the dots of `!` and `?` too, and
  stay on the bubble except where a letter crosses its outline. Change a
  box's numbers only to fix it, reading them off the ruler.
- A translation uses letters and common punctuation only: the lettering font
  cannot draw symbols such as ♥ or emoji. The box still covers a symbol in
  the original, so it is erased.
- An empty `translation` erases the text and letters nothing; on artwork that
  can leave a smudge, so delete the entry there instead.

## Answer

- How many pages and pieces of text are translated.
- What you left untranslated on purpose (sound effects, signs).
