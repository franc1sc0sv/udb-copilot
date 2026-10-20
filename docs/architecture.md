# Architecture

```
src/udb/
  core/          settings (data home), paths, schema (canonical keys + legacy aliases),
                 lang (words matched inside notes), notes, anchors, text, findings
  vault/         registry, index (SQLite FTS5), ingest, classes, methods, ledger,
                 scaffold (templates), figures
  checks/        citations, clarity, coverage, exercises (method conformance)
  integrations/  moodle/ (client, sync) · mail/ (base, gmail, outlook, imap)
                 google/ (oauth, calendar, drive) · recordings/ (catalog, download,
                 frames, radar, asr)
  planning/      agenda, tasks, status, digest
  rendering/     jinja, lesson, exercise, math_svg (+ vendor/render_math.cjs), diagrams,
                 templates/
  agent/         prompts (rules + subagents), guards (hooks), runner (Agent SDK)
  server/        app (the `vault` MCP server)
  cli/           the `udb` command, one module per area
  assets/claude/ skills and CLAUDE.md copied into the data home by `udb setup claude`
```

## Rules

- **Layers point down.** `cli` and `server` call `planning`, `checks`, `vault` and
  `integrations`; those call `core`. Nothing in `core` imports upward.
- **CLI and MCP share functions.** A tool and a command never re-implement each
  other; both format what one function returns.
- **No model in the facts.** Search, citations, checks, status, agenda and digest
  are deterministic. A model only writes prose on top of them.
- **Code is English, content is the student's language.** Keys, commands, tool
  names and identifiers are English. Note text, section titles and generated
  pages are Spanish; the words the checks match live in `core/lang.py`.
- **Old data keeps working.** `core/schema.py` reads the pre-0.1 Spanish keys;
  `udb migrate` rewrites them.
- **Heavy dependencies are extras.** The core install has no torch, no browser
  automation and no Agent SDK, so a cloud session installs in seconds.
- **Fail closed.** The pre-tool hook blocks when `udb` is missing.

## The citation contract

`vault_quote` is the only way to cite. It returns an anchor:

```
[^c1]: SRC-IRD-0003 | page=14 | quote="exact text"
[^c2]: SRC-IRD-0007 | t=00:41:12-00:41:25 | quote="what the teacher said"
[^c3]: MODEL | reason="why the material does not cover it" | basis=SRC-IRD-0003
```

`udb verify` checks that the source exists and is current, that the quote is in
the derived text at that page (or the next one, for quotes across a page break)
or time window, that quotes are not trivially short, that every paragraph is
cited, and that model content stays under 30% of the words. It warns when a
sentence and its quote share no word.
