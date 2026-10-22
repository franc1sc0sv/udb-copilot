# Architecture

```
src/udb/
  __main__.py          python -m udb
  config/              settings (data home), paths, secrets, schema
  domain/              the study logic
    text/              normalize (folding, passages), lang (words matched in notes), chunking
    notes/             document (note parser), anchors, findings
    sources/           registry (sources, versions, classes), ingest, ocr, figures,
                       index (SQLite FTS5), health (`udb sources`)
    study/             classes, methods, ledger, scaffold
    checks/            citations, coverage, clarity, exercises, deep (optional model judge)
    planning/          agenda, digest, status, tasks
  integrations/        everything that talks to the outside
    moodle/            client (transport, read-only guard), reader, sync
    mail/              base, gmail, imap
    google/            oauth, calendar, drive
    media/             catalog, download, asr (Whisper), frames (board stills),
                       vision (Qwen3-VL), stream (Teams, via Claude in Chrome), radar
  interfaces/          how udb is used
    cli/               app.py (the `udb` command), common.py, commands/ (one module per area)
    mcp/               vault.py (the `vault` MCP), moodle.py (the `moodle` MCP)
    claude/            setup (.claude/ and .mcp.json), prompts, hooks, runner (Agent SDK)
  rendering/           lesson, exercise, views, math_svg, diagrams; templates/, static/
  assets/claude/       skills and CLAUDE.md copied into the data home by `udb setup claude`
```

## Rules

- **Layers point down.** `interfaces` calls `domain`, `integrations` and `rendering`;
  `domain` and `integrations` may call each other but never `interfaces`; `config`
  imports nothing from the rest. Imports are absolute (`from udb.domain.notes import anchors`).
- **CLI and MCP share functions.** A tool and a command never re-implement each
  other; both format what one function returns.
- **One way per thing.** No legacy aliases, no second backend kept "just in case".
- **No model in the facts.** Search, citations, checks, status, agenda and digest
  are deterministic. A model writes prose, reads boards and, on request
  (`verify --deep`), judges faithfulness as a warning.
- **Code is English, content is the student's language.** Note text, section
  titles and generated pages are Spanish; the words the checks match live in
  `domain/text/lang.py`.
- **Moodle is read only.** `integrations.moodle.client` refuses any web-service call that is
  not a pure read, for every caller.
- **Heavy dependencies are extras** (`asr`, `vision`, `agent`),
  so a cloud session installs fast. OCR is in the base install.
- **Fail closed.** The pre-tool hook blocks when `udb` is missing.
- **No test suite.** Changes are checked by running `udb` against a real vault.

## The citation contract

`vault_quote` is the only way to cite. See [references.md](references.md).
