---
name: udb-sources
description: What to do when a source seems unreadable (scanned PDF, images, embedded video, odd format). Use it before ever telling the student that a PDF, image or page cannot be read.
---

# /udb-sources

Never answer "I can't read this PDF" or "I can't see the images". Instead:

1. Call `source_status` (subject or source id). It says how each source was read:
   `ok`, `needs-ocr`, `images` (figures not read yet), `no-text`, `unsupported`, `missing`,
   `stale`, and the exact command that fixes it.
2. Fixable states (`needs-ocr`, `images`, `stale`): run `udb sources fix <SRC>` and search again.
3. A figure you need to look at (diagram, table, formula as image): `source_figure(source_id, n)`.
   The page text marks where each one is: `[Figura 7: caption]`. Its OCR text is searchable
   and citable like any page (the result of `vault_search` shows `section: Figura 7`).
4. `no-text` and `unsupported`: tell the student what the source is (title, type) and ask for
   the content or another format. Embedded videos and documents appear in the text as
   `[Contenido incrustado: ...]` with their link.
