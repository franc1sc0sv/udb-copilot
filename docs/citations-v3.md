# Citations v3 (design, not built yet)

## Status (2026-10-21)

Built and tested: the paragraph rule (`repeated-citation` with `--fix`,
`many-citations`), passage quotes from `vault_quote` (whole sentences, `exact=True`
for literal definitions), `trivial-quote` under 8 words, `weak-support` against the
whole paragraph, the three voices (`[!example]` and `[!analogy]` need no citation and
sit outside the 30 % budget), material coverage (`source-not-used`,
`pages-not-covered`, "material cubierto" in `udb status`), and board stills as
citable chunks (`t=` + `frame=`, descriptions after `Figura:` not quotable).
First run on the real vault removed 432 repeated references with no text change.

Not built yet: re-anchoring with fuzzy match (`quote-drifted`), `udb verify --deep`,
the citation card and coverage strip in lesson pages, `/udb-tidy`, and the
ingestion items of section 7 (Moodle-native sources, class assignment, HTML
cleanup, versions).

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

## 8. Microsoft 365 (UDB account)

Class recordings live on the teachers' OneDrive/SharePoint (Stream), and the
UDB mailbox is Outlook. Facts checked on 2026-10-20:

- The UDB tenant (`f9afe020-…`) is **Managed** (cloud identities, no ADFS):
  the Microsoft sign-in page handles the login directly.
- Reading a shared link (`GET /shares/{u!base64url}/driveItem/content`) needs
  delegated `Files.ReadWrite` at least (Graph docs). Plain `Files.ReadWrite` and
  `Mail.Read` are user-consentable by default; `*.All` and `Sites.*` need an
  admin. Whether UDB restricts user consent (e.g. verified publishers only) is
  **unknown until the first login**. If it does, the student sees "Need admin
  approval" and can request it; the fallback is downloading by hand.
- Stream transcripts have no documented Graph endpoint. An internal
  `_api/v2.1/…/media/transcripts` route is reported to work; udb may try it
  as a bonus, never rely on it.

Design, mirroring Google:

- **One Entra app owned by the student** (multi-tenant + personal accounts,
  public client). Login is OAuth **authorization code + PKCE**: on the PC the
  browser returns to `http://localhost`; from a phone or the cloud the student
  pastes the final URL back (the rclone/gcloud "no browser" pattern). Device
  code is only a fallback: since 2025 Microsoft ships a managed Conditional
  Access policy that blocks it in tenants that never used it.
- **Where to register it:** first try inside the UDB tenant with the student
  account (an app registered in the tenant passes even the stricter consent
  policies); otherwise a free Entra directory of the student's own. Scopes: `User.Read`, `Mail.Read`, `Files.ReadWrite`,
  `offline_access`. udb never writes files; `ReadWrite` is only what `/shares`
  demands.
- **udb owns the login** (MSAL cache under `secrets_dir`, packed into
  `UDB_SECRETS`), so it works in the cloud too. Several Microsoft accounts are
  fine, like Gmail.
- **Optional Microsoft 365 MCP**: Softeria `ms-365-mcp-server` (open source,
  `--org-mode --read-only`, presets for mail, calendar, files, Teams) launched
  by `udb ms365-mcp`, which passes a fresh access token from udb's cache
  (`MS365_MCP_OAUTH_TOKEN`) so there is one login, not two. Off unless
  `mcp.ms365: true`.

## 9. Videos: the media pipeline (local GPU)

Sources measured: 22 class recordings (21 Stream/SharePoint, 1 Teams), all
pending; at least 41 YouTube videos embedded in course pages. Goal: every
video becomes a citable document with what was **said** and what was
**shown** (slides, formulas, diagrams, whiteboard).

```
acquire ─▶ audio ─▶ speech-to-text ──────────────┐
   │                                              ├─▶ timeline ─▶ index + citations
   └────▶ frames ─▶ dedup ─▶ read each slide ─────┘        └─▶ match against course PDFs
```

| Stage | How | Notes |
|---|---|---|
| Acquire | Stream/Teams: Graph `/shares` with the UDB login. YouTube: `yt-dlp` (video ≤720p + auto captions). Fallback: download by hand + `udb recording attach` | videos stay on local disk, **not** in git (size); only text and frames are committed |
| Audio | ffmpeg to 16 kHz mono; voice activity detection drops silence | silence is where Whisper invents text |
| Speech to text | Whisper large-v3 (faster-whisper, CTranslate2 ≥ 4.5 with CUDA 12.8, `float16`: `int8` crashes on RTX 50); transformers fallback (already in v2). Prompt seeded with the subject's own terms (VLAN, subred, determinante) | YouTube captions only as a quick preview or in the cloud |
| Frames | ffmpeg scene change + perceptual dedup; keep the **last** frame before each change so build-up slides and whiteboards are complete | v2 has scene frames; dedup and "last frame" are new |
| Read slides | tier 1: RapidOCR (text, fast, already used). tier 2: **PaddleOCR-VL** (0.9 B, Apache-2.0, top of OmniDocBench incl. formulas and tables) → Markdown + LaTeX. tier 3: **Qwen3-VL-8B** quantised, only on frames that look like diagrams, handwriting or code → structured description or mermaid | LaTeX is compiled with udb's offline MathJax; a formula that does not compile is flagged |
| Timeline | one "page" per slide interval: slide text/LaTeX, diagram description, and the words said meanwhile | citable with `t=` (v2) and `frame=` |
| Match | slide OCR compared with course PDFs/slides already in the vault (the Interspeech 2024 study found OCR the strongest signal for frame↔slide matching) | a note can cite the PDF page **and** what the teacher said about it |
| Radar | exams, dates, grades said out loud (v2 `recording_radar`) | now over the full timeline |

Voices still apply: OCR and transcript text is the teacher's (exact-quote
checked); a diagram description written by a model is **not** the teacher's
words, so it is cited as a figure (`frame=`) and shown as "descripción
automática", never quoted as if the teacher said it.

Quality gates per video, shown in `udb recording board`: speech confidence
(mean log-prob), share of no-speech, repeated-phrase alarms, frames read,
formulas that failed to compile. Anything below threshold is `needs-review`
instead of silently indexed.

Compute: runs only on the student's PC (RTX 5080, 16 GB), queued with
`udb media process --all`. Speech and slide reading can share the GPU
(Whisper fp16 and PaddleOCR-VL together fit in 16 GB); Qwen3-VL runs alone.

Speed and quality are chosen by benchmark, not guessed:

| Stage | Candidates | Measured on |
|---|---|---|
| Speech | large-v3 vs large-v3-turbo; beam 1 vs 5; batched (`BatchedInferencePipeline`) vs sequential; VAD on/off | a Spanish class clip with a hand-corrected reference: word error rate, technical-term accuracy, real-time factor, VRAM |
| Slides | RapidOCR vs PaddleOCR-VL (vs Qwen3-VL) | 50 frames with formulas, tables, diagrams: LaTeX that compiles, text accuracy, seconds per frame |
| Frames | scene threshold, dedup threshold | frames kept vs slides really shown |

Published hint, not our number: on English audio turbo ran 2.7× faster than
large-v3 with no WER loss (faster-whisper issue #1030). Spanish and technical
vocabulary may differ, so both are tested.

First proof before building the rest: one Stream class (IRD) and one YouTube
embed, end to end: acquire → transcript → frames → slide reading → a note
with `t=` and `frame=` citations → `udb verify`.

## 10. What is proven today and what is not

| Claim | Status |
|---|---|
| A quote in a note is literally in the source at that page | proven by `udb verify`, no model |
| 1015 anchors re-located after re-extraction | done in v2 |
| Paragraph says what the passage says | heuristic only (`weak-support`); `--deep` judge proposed |
| Every page of the teacher's material is used | **not checked yet** (section 3) |
| Forum posts and messages are citable | **not yet** (section 7) |
| Embedded videos are read | **no** (section 9) |
| Class recordings can be downloaded and transcribed | **untested** |
| UDB lets a student consent to an own app | **unknown until first login** |
| PaddleOCR-VL and Qwen3-VL run well on the RTX 5080 | **untested** |

## Migration

1. `udb verify --fix` collapses repeated anchors (mechanical, safe).
2. `/udb-tidy <file>`: the scribe merges sentence-level references into one
   passage per paragraph and re-runs verify. One note at a time, diff shown.
3. Rules, skills and agent prompts change to the paragraph rule.
