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
| Recording | a transcript with timestamps instead of pages |

`derived/text/<ID>.meta.json` remembers what is not text yet: images not
downloaded, embedded videos and documents, scanned pages without OCR.
`udb sources` lists them with the command that fixes each one.

## 2. Claude cites through the tools only

1. `vault_search("inverso multiplicativo", subject="AVM")` returns chunks with
   their source, page and section.
2. `vault_quote(chunk_id, substring="...")` checks the substring is literally in
   the chunk, finds the page where it really is, and returns the anchor:

```
[^c1]: SRC-AVM-0012 | page=4 | quote="El inverso multiplicativo de z es..."
[^c2]: SRC-IRD-0007 | t=00:41:12-00:41:25 | quote="lo que dijo el profesor"
[^c3]: MODEL | reason="el material no da un ejemplo numérico" | basis=SRC-AVM-0012
```

Claude cannot open `sources/` or `derived/` directly (a hook blocks it), so it
cannot paste text it did not get from `vault_quote`. Claude's own explanations
go in `> [!model]` blocks with a `MODEL` anchor that says why and on what basis,
at most 30% of the words.

## 3. `udb verify` checks every anchor

| Check | Result |
|---|---|
| The source exists and was not replaced by a newer one | error |
| The quote is on that page (or across the next page break), or in that time window (±20 s) | error if it is nowhere |
| The quote is in the source but on another page | warning, repaired by `udb verify --fix` |
| The quote is a word or two | warning: it proves nothing |
| The quote and its sentence share no word | warning: probably the wrong quote |
| Every paragraph has a citation; model content under 30% | error / warning |

Quotes are compared after folding accents, case, curly and straight quotes,
whitespace, and the `[Figura N]` markers the extractor writes where images were.

## What it cannot prove

That the sentence means what the quote means. The support warning catches
quotes that share no words with the sentence; reading the note is still the
final check.
