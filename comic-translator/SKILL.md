---
name: comic-translator
description: Translates the speech bubbles and captions of comic, manga or webtoon pages into another language, in place, erasing the original lettering and lettering the translation. Use when the person shares comic pages, as images or a .zip/.cbz chapter, and asks for them translated, even if they only say "translate this page". Not for photos, documents or screenshots that are not comics.
compatibility: Requires running shell commands with uv, viewing image files, internet access once to fetch its models (about 215 MB), and about 1 GB of free memory while rendering.
---

# Comic translator

## Available scripts

- **`scripts/run.py`**: `detect` finds the text on every page and writes a work
  folder; `names-jobs`, `names` and `jobs` write the per-page model calls to
  jobs files; `apply` turns the saved answers into notes; `render` erases each
  entry's text and letters its translation; `pack` puts the translated pages
  into one archive; `parts` splits a chapter for several workers. `--help`
  shows them all. Each prints one JSON object, or one line starting `error:`
  that says what to fix.

Run each command below exactly as written, from this skill's folder. Do not
modify it, read the scripts, or copy them: the folder may be read-only, and
`uv run scripts/run.py` writes nothing there.

The scripts run with `uv`. If `uv` is not found, ask the person whether to
install it, and only on their yes run
`curl -LsSf https://astral.sh/uv/install.sh | sh`. It installs to
`~/.local/bin/uv`, which is not on the search path, so in every command
below write `~/.local/bin/uv` where it says `uv`.

`<language>` is the one the person asked for, English when they don't say.

## Workflow

Your task may give you a role: Prepare, Part or Combine. A task that names
no role is the whole job.

Progress:
- [ ] 1. Detect
- [ ] 2. Translate the pages
- [ ] 3. Hand over

1. **Detect**, giving the image or the `.zip`/`.cbz` as it is:
   ```bash
   cd "<this skill's folder>" && uv run scripts/run.py detect "<page image or archive>"
   ```
   It makes a work folder beside the input. Its report names the work folder
   and, in `text_pages`, the pages with text: a page with none is done
   already. Running it again keeps notes already in the work folder.

   When you have no role, the chapter has 2 pages or more, and you can start
   2 workers or more, you are Prepare: go to [Several workers](#several-workers)
   now.
2. **Translate the pages**, all of `text_pages`, as
   [Translating pages](#translating-pages) says. First build the names list:
   ```bash
   uv run scripts/run.py names-jobs "<work folder>" <language>
   ```
   Answer its jobs file as [Answering a jobs file](#answering-a-jobs-file)
   says, then run `uv run scripts/run.py names "<work folder>"`. It writes
   `names.json`, which every page's job reads.
3. **Hand over**, in two steps:
   - pack the translated pages next to the input, named as it with the
     target language's English name before its extension, as `chapter.zip`
     translated to English becomes `chapter-english.zip`:
     ```bash
     cd "<this skill's folder>" && uv run scripts/run.py pack "<work folder>" "<input's folder>/<input's name>-<language>.zip"
     ```
     A page with no entries goes in as it is. It refuses while a page is
     untranslated, or its notes changed after it was rendered, and names
     those pages. Working alone, translate and render them, then pack again;
     a Combine reports blocked instead.
   - send that zip to the person with your tool for giving them a file, then
     write your answer.

## Translating pages

For the pages you were given, from this skill's folder:
1. `uv run scripts/run.py jobs "<work folder>" <language> <your pages>`. Answer
   the jobs file it names, as [Answering a jobs file](#answering-a-jobs-file)
   says. Each page's answer gives every box a kind, its original and its
   translation.
2. `uv run scripts/run.py apply "<work folder>" <your pages>`. It writes the
   answers into the notes: it keeps text in bubbles and captions, and leaves
   signs, titles and sounds drawn on the art as they are. Its `flagged` lists
   the pages to look at again, and why.
3. Render your pages, naming them after the work folder:
   ```bash
   cd "<this skill's folder>" && uv run scripts/run.py render "<work folder>" <your pages>
   ```
   When render refuses, fix what it names and render again:
   - an entry with no translation: translate it, or delete it to leave its
     text as it is;
   - a symbol the font cannot draw, such as `♪` or an emoji: write it in
     words or leave it out. The box still covers the symbol in the
     original, so it is erased.
4. Look again only at the pages in `flagged`, and at pages whose render
   report has `warnings` or `left as it is`. Every other page is done. For
   each, fix its notes as [Fixing a page](#fixing-a-page) says and render it
   again, naming it. Stop when no page changed. A piece of text still not
   clean after you changed its entry twice: delete its entry, and say so in
   your answer. Render refuses a page it has drawn 3 times: leave that page
   as it is, and name what is still not clean on it.

## Answering a jobs file

A jobs file is a JSON list. Each job has image `paths`, `instructions`, and
`save_to`. Get every job answered by a model that can see images, sending it
only that job's instructions and images, and save its reply, as it is, to
the job's `save_to`. When one of your tools takes a whole jobs file, give it
the file: it answers each job with no history, which is fastest and
cheapest. Otherwise answer the jobs one at a time. Then name any job whose
answer was not saved, run it again once, and go on: `apply` flags a page
with no answer.

## Fixing a page

Detect wrote, for each page, `boxes/<page>-<n>.jpg`: sheets of boxes, each
box cut out with a little of what is round it, enlarged and numbered with
its entry's `id` in `notes/<page>.json`. Render wrote `result-boxes` sheets
of the same boxes on the translated page. `overview/<page>.jpg` shows where
each box sits; its text is too small to read. A `review` or `result`
stretch is the page full size, with a ruler whose numbers are page pixels.

Open the page's `boxes` and `result-boxes` sheets and edit its notes:
- `original`: the text in the box exactly as it reads on the `boxes` sheet;
- `translation`: it in `<language>`, punctuated as that language does;
- keep an entry only for text in a speech bubble, a thought bubble or a
  caption box, sounds in a bubble too. Delete every other entry, to leave
  its text as it is: a sign, a label, a title or logo, a sound effect drawn
  on the art, credits, or a box with no text. Erasing drawn text damages
  the picture round it;
- text no box holds: add an entry with a new `id`;
- text written in columns, or a right-to-left target language: add
  `"direction": "vertical"` or `"rtl"`.

The render report's `warnings`: a box far from where detect found its text
goes back on its text; a box holding more lines than its `translation` reads
is read again whole. Its `left as it is` names ids of text detect found whose
entry is gone: find each by its box in `detected/<page>.json`, and copy it
back when it sits in a bubble or a caption.

An entry before and after editing; only `original` and `translation`
change, and `box` stays as detect wrote it:
```json
{"id": 2, "box": {"left": 330, "top": 50, "right": 470, "bottom": 120}, "original": "", "translation": ""}
{"id": 2, "box": {"left": 330, "top": 50, "right": 470, "bottom": 120}, "original": "...y el toque final.", "translation": "...and the final touch."}
```

## Several workers

**Prepare.** You have run Detect. Your task says how many workers can run at
once; when it does not, take 3. From this skill's folder:
1. Build the names list as step 2 of the workflow says: `names-jobs`, answer
   its jobs file, then `names`.
2. `uv run scripts/run.py parts "<work folder>" <workers> <language> "<input's folder>/<input's name>-<language>.zip"`.
   Report its `summary` as your result, exactly as printed, and stop. Those
   lines are for whoever started you: each becomes its own worker. Do not
   translate a page yourself.

**Part.** Your task names your pages and the language. Translate those pages
and no others, as [Translating pages](#translating-pages) says. Then report
how many pages you translated, and the pages you looked at again and why.

**Combine.** Do step 3, Hand over, only. Do not read, translate or render a
page. When pack refuses, report blocked with the pages it names and why,
and which Part's task names them, so they go back to that Part.

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
- A sound inside a bubble is translated (`¡COF, COF!` is `COUGH, COUGH!`);
  one drawn on the art (`SHH SHH`, `PLOP`) is left as it is.
- Text is read from the `boxes` sheets, by the jobs or by you. Do not install
  OCR or other packages to read it: they are large downloads, and the sheets
  are enlarged for reading.
- Look only at the images detect and render made: `overview`, `boxes`,
  `review`, `result-boxes` and `result`. Do not crop, zoom or save images of
  your own. Every image you open stays in your conversation, so each extra
  one makes every later step cost more.
- A bubble cut by the top or bottom edge of a page shows only part of its
  text. Translate the part that is there, render it once, and leave it: it
  cannot come out clean, and the rest of the bubble is on the next page.
- A box must hold every mark of its text, the dots of `!` and `?` too, and
  stay on the bubble except where a letter crosses its outline. Change a
  box's numbers only to fix it, reading them off the ruler.
- An empty `translation` erases the text and letters nothing; on artwork that
  can leave a smudge, so delete the entry there instead.

## Answer

- How many pages and pieces of text are translated.
- What you left untranslated on purpose (sound effects, signs).
