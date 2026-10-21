# How references work

Every claim in a note points at the exact place of the course material it comes
from, and `udb verify` proves the quote is really there. No model takes part in
the proof.

## 1. A source becomes citable text

```
course file ──register──▶ SRC-AVM-0012 (registry.jsonl: title, class, sha256, url)
            ──extract───▶ derived/text/SRC-AVM-0012.pages.jsonl   one record per "page"
            ──index─────▶ index/vault.db                          220-word chunks, full-text search
```

What a "page" is depends on the file:

| File | Page |
|---|---|
| PDF | each page; a scanned page gets OCR text |
| Slides (pptx) | each slide, with its speaker notes |
| Word (docx) | each heading block |
| HTML course page | each section (h1–h3), with its title |
| Figure of an HTML page | the OCR text of the image, once downloaded (`udb sources fix`) |
| Teacher's words in Moodle | a course page, assignment instructions, a teacher forum post or private message (kind `moodle`, versioned: an edit makes a new source and supersedes the old) |
| Recording | a transcript with timestamps instead of pages, plus one chunk per complete board still |

Lines repeated on most HTML pages of a subject (menus, footers) are left out of
the index.

`derived/text/<ID>.meta.json` remembers what is not text yet: images not
downloaded, embedded videos and documents, scanned pages without OCR.
`udb sources` lists them with the command that fixes each one.

## 2. Claude cites through the tools only

1. `vault_search("inverso multiplicativo", subject="AVM")` returns chunks with
   their source, page and section.
2. `vault_quote(chunk_id, substring="...")` checks the substring is literally in
   the chunk, finds the page where it really is, widens it to the 1-3 whole
   sentences around it (the passage; `exact=True` keeps a literal definition as
   is), and returns the anchor:

```
[^c1]: SRC-AVM-0012 | page=4 | quote="El inverso multiplicativo de z es..."
[^c2]: SRC-IRD-0007 | t=00:41:12-00:41:25 | quote="lo que dijo el profesor"
[^c4]: SRC-IRD-0007 | t=00:52:10 | frame=f0031 | quote="lo escrito en la pizarra"
[^c3]: MODEL | reason="el material no da un ejemplo numérico" | basis=SRC-AVM-0012
```

Claude cannot open `sources/` or `derived/` directly (a hook blocks it), so it
cannot paste text it did not get from `vault_quote`. One citation per paragraph:
a passage that backs the whole paragraph. Claude's own words are labelled:
`> [!model]` (explanation, with a `MODEL` anchor that says why and on what basis,
at most 30% of the words), `> [!example]` and `> [!analogy]` (no citation, outside
the 30%).

## 3. `udb verify` checks every anchor

| Code | Check | Level |
|---|---|---|
| `unknown-source`, `superseded-source` | the source exists and was not replaced by a newer one | error |
| `quote-not-found`, `quote-not-in-window` | the quote is on that page (or across the next page break), or in that time window (±20 s) | error |
| `quote-drifted` | the text changed a little after re-extraction; `--fix` writes the new wording (≥ 88 % alike) | warning |
| `quote-moved` | the quote is in the source but on another page; `--fix` moves it | warning |
| `trivial-quote` | under 8 words and not shown literally in quotes | warning |
| `weak-support` | the passage shares no word with its paragraph | warning |
| `repeated-citation`, `many-citations` | one anchor twice in a paragraph (`--fix` removes it); 3+ anchors of one source | warning |
| `figure-description-quoted` | a board's `Figura:` text is the vision model's, not the teacher's | error |
| `uncited-paragraph`, `model-content-over-budget` | every paragraph has a citation; `[!model]` under 30% | error / warning |
| `source-not-used`, `pages-not-covered` | every source of the class, and every slide with text, is used | warning |
| `deep-partial`, `deep-unsupported` | only with `--deep`: a small model reads paragraph and passages | warning |

Quotes are compared after folding accents, case, curly and straight quotes,
whitespace, and the `[Figura N]` markers the extractor writes where images were.

## What it cannot prove

That the paragraph means what the passage means. `weak-support` catches passages
that share no words with the paragraph and `--deep` asks a model, but a judge
misses real support often, so both are warnings; reading the note is still the
final check.
