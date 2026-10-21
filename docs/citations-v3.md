# Citations v3 (design, not built yet)

Goal: notes a student can read and trust. Every idea of the teacher is there,
every claim can be checked in one tap, and the reader always knows who is
talking: the teacher, the book, or Claude.

## What v2 got right and wrong

Right, and kept:

- A citation cannot be invented. Claude never opens the material; it cites only
  through `vault_search` → `vault_quote`, and `udb verify` proves, without any
  model, that the quoted words are on that page. The Claude Citations API makes
  the same promise ("valid pointers to the provided documents").
- Pages, slides, sections and transcript windows as locations; `--fix` moves
  quotes after re-extraction.

Wrong:

- **Density.** The checker asks for one citation per paragraph, but the writing
  rules said "a citation for every claim" and `weak-support` compared each
  citation with the sentence just before it. Agents learned to cite every
  sentence. Measured on the vault: 859 cited paragraphs, 1346 references,
  146 of them the same anchor repeated inside one paragraph.
- **Quotes too short.** A 6-word quote proves the words exist, not that the
  paragraph is faithful. Short quotes forced many references per paragraph.
- **Nothing says what was skipped.** Coverage checks topics of the learning
  route, not "did this class note use every slide the teacher gave".
- **Provenance is not visible.** In a page, a paraphrase of the teacher and an
  example made up by Claude look the same unless the `[!model]` box is noticed.

## What others do

| System | Unit of citation | Idea taken |
|---|---|---|
| APA style guides | Cite at first use in a paragraph; again only when the source could be unclear or changes | One reference per paragraph per source |
| Wikipedia (WP:CITE) | "Text–source integrity": the reader must tell which text each source supports; bundling many sources in one footnote breaks it | Several references only when the paragraph mixes sources, each right after its part |
| ALCE benchmark | Per sentence; *recall* = cited text entails the statement, *precision* = no needless citation | Over-citation is an error, not safety; measure both |
| AutoAIS / TRUE (NLI) | Entailment model judges "does the passage support the claim" | High precision, low recall: use as a warning, never as proof |
| Claude Citations API | Sentence chunks; one citation may chain consecutive sentences into a passage | Quote a passage, not a phrase |
| W3C Web Annotation / Hypothesis | `exact` + `prefix`/`suffix` + position; fuzzy re-anchoring (Bitap, diff-match-patch) when the document changes | Exact for the proof, fuzzy only to propose a fix |
| NotebookLM | Number in the text; hover shows the passage, click opens the source there | The page shows the passage on tap; the text stays clean |
| Note-taking research (Mueller & Oppenheimer 2014) | Generative notes (summary, paraphrase) beat verbatim copying for conceptual questions | Paraphrase plus one anchor beats a wall of quotes |

## The v3 rules

### 1. The unit is the paragraph

- One reference at the **end** of a paragraph that comes from one source.
- A paragraph that mixes sources gets one reference right after each part.
- The same anchor twice in one paragraph is `repeated-citation` (warning);
  `udb verify --fix` keeps the last one.
- The quote is a **passage**: one to three consecutive sentences that together
  back the whole paragraph. `vault_quote` returns the passage around the match.
  Quotes under 8 words are `trivial-quote` unless they are a definition.

### 2. Three voices, always visible

| Voice | How it is written | How it is checked | How the page shows it |
|---|---|---|---|
| Teacher, literal | `"..."` inside the text + reference | the quoted words must be in the source, exactly | quote style |
| Teacher, explained | plain paragraph + reference | quote exists; passage and paragraph share the key terms | normal text, small number at the end |
| Claude | `> [!model]` (claims), `> [!example]` (worked example), `> [!analogy]` | `basis=` must exist; budget counts only `[!model]` | coloured box labelled "Explicación de Claude" |

Examples and analogies adapted to the student are welcome and do not count
against the 30% budget, because the box tells the reader they are not the
teacher's. A claim of fact by Claude still goes in `[!model]` with a basis.

### 3. Nothing of the teacher is skipped

New checks per class note, against the sources assigned to that class:

- `source-not-used` (error): a class source is never cited.
- `pages-not-covered` (warning): pages or slides of a class source that no
  paragraph cites, as ranges (`SRC-IRD-0012 p.12–18`). Title, agenda and
  blank pages are skipped automatically (under 15 words).
- `status` shows "material cubierto 87%" per class, and the list of gaps.
- Teacher messages, forum posts and assignment instructions (read through the
  `moodle` MCP) can be registered as sources, so "the teacher said in the
  forum" is citable too.

### 4. Faithfulness checks, cheap first

1. Always, no model: the quote is in the source (exact, after folding quotes
   and stripping figure markers).
2. Always, no model: `weak-support` compares the paragraph (not one sentence)
   with the passage, using word stems and formulas stripped.
3. On demand, `udb verify --deep`: a small Claude model reads each paragraph
   with its passage and answers supported / partial / unsupported, with the
   reason. Cached by hash, so a note is judged once until it changes. Warnings
   only: research shows these judges miss real support often.

### 5. Re-anchoring

When material is re-extracted, an exact quote may stop matching (OCR fixed a
letter, a slide was edited). v3 finds the closest passage with a fuzzy match
near the old page and proposes it as a `quote-drifted` fix. It is never
accepted silently: the fixed quote must again be exact.

### 6. Reading the result

- Markdown: one footnote number per paragraph. The footnote shows source title,
  page and the passage.
- Lesson HTML: the number opens a small card with the passage and a link that
  opens the material at that page (NotebookLM style).
- The class page starts with a coverage strip: which material, how much of it
  the note covers, and any gap.

## 7. Getting the classroom content right (ingestion)

Citations are only as good as the text under them. Measured on the vault on
2026-10-20:

| Fact | Number | Risk |
|---|---|---|
| Sources | 106: 90 HTML pages, 14 PDF, 1 md, 1 rar | |
| HTML pages | 513 sections, 542 figures read by OCR | good |
| Embedded videos and iframes in HTML | 127 markers, at least 41 YouTube | their content is **not** in the vault |
| Sources with no class assigned | 32 of 106 | per-class coverage cannot see them |
| Scanned PDF pages read by OCR | 12 | the installed `udb` lacks the `ocr` extra, so new scans would be empty |
| Forum posts, teacher messages, assignment instructions | 0 registered | "the teacher said in the forum" cannot be cited |
| Unsupported (rar) | 1 | must be extracted by hand |

Changes:

1. **One record per Moodle activity, not per file.** `udb sync` walks the course
   outline (the `moodle` MCP reader) and registers every activity with its
   cmid, section and dates: files, pages, labels, books, url targets, assignment
   instructions and their attachments, and forum posts by teachers. Each gets a
   type (`moodle-page`, `moodle-forum-post`, `moodle-assign`, `moodle-message`),
   so a quote can say "foro de avisos, 12 oct" instead of a file name.
2. **Class assignment from the outline.** The Moodle section ("Semana 5",
   "Clase 3") and the learning route set `class` automatically. Anything left
   without a class is listed by `udb sources` as `unassigned`, and coverage
   reports it instead of hiding it.
3. **Versions, not overwrites.** `updates` tells when a teacher edits an
   activity. The new text becomes a new version; the old one is
   `superseded_by`, and notes citing it get `superseded-source` with a fix.
4. **HTML cleanup checks.** Before indexing, drop navigation, footers and
   repeated boilerplate shared by many pages (seen on more than half of a
   course's pages), and keep tables as tables. A section shorter than 80 chars
   still merges into the previous one.
5. **Embeds become sources.** Every `[Contenido incrustado]` marker is
   resolved: YouTube → its captions; Stream or SharePoint → the recordings
   pipeline; H5P or Genially → its text if reachable, otherwise a visible
   `embed-unread` warning in `udb sources` and in coverage.
6. **OCR always on.** `ocr` joins the default install (local and cloud), and
   `udb cloud check` reports whether OCR works.

## 8. Videos

Two kinds, measured: 22 class recordings in the catalog (21 on the teachers'
SharePoint/Stream, 1 on Teams), all `pending`; and at least 41 YouTube videos
embedded in course pages.

| Video | How to get it | How to get the text | Status |
|---|---|---|---|
| YouTube embed | no download needed | captions with yt-dlp (`--write-auto-subs`), Spanish first | to build, cheap, works in the cloud |
| Stream / SharePoint recording | Microsoft Graph with the student's UDB account (`/shares/{url}/driveItem/content`, `Files.Read.All`), no browser cookies | Stream's own transcript if Graph exposes it; otherwise Whisper on the RTX 5080 | **untested**: needs the UDB Microsoft account set up as an Outlook account first |
| Fallback | yt-dlp with browser cookies, or download by hand + `udb recording attach` | Whisper locally | built in v2, never run on a real recording |

Every transcript is a source with `t=HH:MM:SS-HH:MM:SS` anchors (already
verified by v2), and `frames` adds one image per slide change with its OCR
text, citable as a figure. `recording_radar` keeps scanning for exams, dates
and grades said out loud.

Plan: test one recording end to end before building more: discover → download
through Graph → transcript → frames → a cited note → `udb verify`. If Graph
cannot read teacher-owned videos, the fallback stays manual and the docs say so.

## 9. What is proven today and what is not

| Claim | Status |
|---|---|
| A quote in a note is literally in the source at that page | proven by `udb verify`, no model |
| 1015 anchors re-located after re-extraction | done in v2 |
| Paragraph says what the passage says | heuristic only (`weak-support`); `--deep` judge proposed |
| Every page of the teacher's material is used | **not checked yet** (section 3) |
| Forum posts and messages are citable | **not yet** (section 7) |
| Embedded videos are read | **no** (section 8) |
| Class recordings can be downloaded and transcribed | **untested** |

## Migration

1. `udb verify --fix` collapses repeated anchors (mechanical, safe).
2. `/udb-tidy <file>`: the scribe merges sentence-level references into one
   passage per paragraph and re-runs verify. One note at a time, diff shown.
3. Rules, skills and agent prompts change to the paragraph rule.
