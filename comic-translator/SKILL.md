---
name: comic-translator
description: Translates the text in comic, manga or webtoon pages into another language, in place, erasing the original lettering and lettering the translation. Use when the person shares comic pages, an image or a .zip/.cbz chapter, and asks for a translation.
compatibility: Requires running shell commands with uv, viewing image files, internet access once to fetch its models (about 215 MB), and about 1.5 GB of free memory while rendering.
---

# Comic translator

## Available scripts

- **`scripts/run.py`**: `detect` finds the text on every page and writes a work
  folder; `render` erases each entry's text and letters its translation; `pack`
  puts the translated pages into one archive. `--help` shows all three. Each prints one JSON object, or one line starting
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

A chapter with many pages can be split across several workers: see
[Long chapters](#long-chapters) before you start one.

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

   Then count the pages in `<work folder>/pages`. When your task names no
   role and there are at least 3 pages for each worker your bot can run, you
   are Prepare: go to [Long chapters](#long-chapters) now, and do not start
   step 2.
2. **Read and edit**, one page at a time: the overview for where each box
   sits, then the page's `boxes` sheets to read the text. The number on a box
   is the entry with that `id` in the page's notes. Open a `review` stretch
   only for a closer look round a box, or to find text no box holds. Finish a
   page's notes before opening the next page's images. In each entry:
   - `original`: the text in the box exactly as it reads;
   - `translation`: it in the language the person asked for (English when
     they don't say), punctuated as that language does;
   - keep the entry only for text inside a speech bubble, a thought bubble or
     a caption box, sounds in a bubble too, with `translation` the same as
     `original` when it already reads right, so it is lettered like the rest
     of the page;
   - delete every other entry, to leave its text as it is: text drawn as part
     of the picture is never translated. That is a banner (`BIENVENIDOS`), a
     shop or street sign (`FLORISTA`, `PANADERÍA`), a label on a box or a
     building (`TORNILLOS`), a note, bill or coin (`1 DÓLAR`), writing carved
     or painted on a thing, a title or logo, a poster, a chart's labels, a
     sound effect drawn on the art, outlined or not, credits, a watermark, or
     a box with no text. When in doubt, ask whether the text sits in a bubble
     or a caption box: if not, delete it;
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
   It checks the notes of the pages it renders, then translates each page
   from its original. Name pages after the work folder to render only those,
   such as `render "<work folder>" 005 006 007`. It refuses while a page it
   renders still has an entry with no translation, and names those pages:
   translate each entry, or delete it to leave its text as it is.
   It refuses a translation holding a symbol the font cannot draw, such as
   `♪` or an emoji, and names the entry: write it in words or leave it out.
   Each page's `warnings` name a box now far from where detect found its
   text, with the box detect found: fix those first. They also name a box
   holding more lines than its `translation` reads: read the whole box again. Each page's
   `left as it is` lists the ids of text detect found whose entry was
   deleted. Find each by its box in `detected/<page>.json` on the ruled
   `review` images: one in a speech bubble or a caption, however short
   (`¡FUERON TIEMPOS LOCOS!`, `EE, ESTÁ BIEN.`), was deleted by mistake, so
   copy its entry back into the notes, translate it, and render that page. Then look at the
   `result-boxes/<page>-<n>.jpg` sheets, each box cut from the translated
   page (a `result` stretch for a closer look). Where text is left over, a
   box reached onto the art, or a translation reads badly, edit the notes and
   render only those pages again, naming them after the work folder, such as
   `render "<work folder>" 005 012`, until every page is clean. A piece of text still not clean
   after you changed its entry twice: delete its entry, and say so in your
   answer.
4. **Hand over**, in two steps:
   - pack the translated pages next to the input, named as it with the
     target language's English name before its extension, as `chapter.zip`
     translated to English becomes `chapter-english.zip`:
     ```bash
     cd "<this skill's folder>" && uv run scripts/run.py pack "<work folder>" "<input's folder>/<input's name>-<language>.zip"
     ```
     It refuses while a page is untranslated, or its notes changed after it
     was rendered, and names those pages: render them and check them, as in
     step 3, before packing again.
   - send that zip to the person with your tool for giving them a file, then
     write your answer.

## Long chapters

Your task says which of these you are. A task that names no role and gives
a chapter is the first one.

**Prepare.** Run step 1, Detect. Count the pages in `<work folder>/pages`.
Your task says how many workers your bot can run at once. When it does not,
take 3. With fewer than 3 pages for each worker, carry on alone with steps 2
to 4. Otherwise:
- Write `{}` to `<work folder>/names.json`.
- Split the pages into that many runs of pages, in order, as even as they go.
- Call `ticket_report` with the state `ready` and this summary, every path
  in full:

  ```text
  The chapter has <pages> pages, so it is translated in <parts> parts.
  Start now one worker for each line below, with the line as its whole task:
  - Part: translate and render pages <first>-<last> of the chapter in <work folder> with the comic-translator skill.
  - (one line for each part)
  Only after every one of those reports ready, start one worker with this task:
  - Combine: pack the chapter in <work folder> with the comic-translator skill, and hand over <input's folder>/<input's name>-<language>.zip.
  ```

- Stop there. Those lines are for your bot, which starts each one as its
  own worker, so the person sees every part. Do not read a page yourself.

**Part.** Do step 2, Read and edit, then step 3, Render and check, for the
pages your task names and no others. Page names are the notes files' names,
such as `012`. Render only your pages, naming each of them after the work
folder, and fix your own pages until each is clean: no one renders or checks
them after you.

Before each page, read `<work folder>/names.json`. It maps each name or term,
as it reads in the original, to its translation. Translate every one it
holds the way it says. When a page has a new name or term, read the file
again, then add the new one and write it back. Other parts write to it too.

When your pages are rendered and clean, report `ready` with how many pages
and entries you translated, and any text you could not get clean.

**Combine.** Do step 4, Hand over, only. Do not read, translate or render a
page. When pack refuses, report `blocked` with the pages it names and why,
and which part's task names them, so your bot sends them back to that part.

## Gotchas

- Renders in one work folder take turns: while another part renders, yours
  waits, then runs.
- Detect and render take minutes on a long chapter. When your shell says a
  command is still running, call it again with exactly the same command: that
  call waits, and the one that finishes hands back the JSON report. Do not
  watch it with `sleep`, `ps` or `kill -0`: you never get the report, and
  running the command again to see it redoes every page. Sending it changed
  (as with a longer timeout) starts a second copy.
- A translation keeps the original's case: words in capitals stay in
  capitals (`¡NO! Ni se te ocurra.` is `NO! Don't even think about it.`).
- A sound inside a bubble is translated (`¡COF, COF!` is `COUGH, COUGH!`). A
  sound effect drawn on the art (`SHH SHH`, `PLOP`) is left alone by deleting
  its entry: an entry kept, even with the same text, is erased and lettered
  again in plain type, and erasing it damages the picture round it.
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
