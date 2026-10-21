# Architecture

```
src/udb/
  core/          settings (data home), paths, schema, lang (words matched inside notes),
                 notes, anchors, text, chunking, findings, secrets
  vault/         registry (sources, versions, classes), ingest (extract text, OCR, figures),
                 index (SQLite FTS5), sources (health), classes, methods, ledger, scaffold
  checks/        citations (anchors, paragraph rule, drift), coverage (topics, material),
                 clarity, exercises (method conformance), deep (optional model judge)
  moodle/        client (transport, read-only guard), reader (everything readable),
                 sync (files and the teacher's words into the vault)
  mail/          base, gmail, outlook, imap
  google/        oauth, calendar, drive
  media/         catalog (Teams + YouTube), download, asr (Whisper), frames (board stills),
                 vision (Qwen3-VL), stream (Teams via the browser), browser, radar
  planning/      agenda, tasks, status, digest
  rendering/     jinja, lesson (citation cards, coverage strip), exercise, math_svg,
                 diagrams, views, templates/
  claude/        setup (wires .claude/ and .mcp.json), prompts (rules + subagents),
                 hooks (PreToolUse/PostToolUse/session/prompt), runner (Agent SDK)
  server/        app (the `vault` MCP), moodle (the `moodle` MCP)
  cli/           the `udb` command, one module per area
  assets/claude/ skills and CLAUDE.md copied into the data home by `udb setup claude`
```

## Rules

- **Layers point down.** `cli` and `server` call `planning`, `checks`, `vault`, `moodle`,
  `mail`, `google` and `media`; those call `core`. Nothing in `core` imports upward.
- **CLI and MCP share functions.** A tool and a command never re-implement each
  other; both format what one function returns.
- **One way per thing.** No legacy aliases, no second backend kept "just in case".
- **No model in the facts.** Search, citations, checks, status, agenda and digest
  are deterministic. A model writes prose, reads boards and, on request
  (`verify --deep`), judges faithfulness as a warning.
- **Code is English, content is the student's language.** Note text, section
  titles and generated pages are Spanish; the words the checks match live in
  `core/lang.py`.
- **Moodle is read only.** `moodle.client` refuses any web-service call that is
  not a pure read, for every caller.
- **Heavy dependencies are extras** (`asr`, `vision`, `browser`, `agent`, `outlook`),
  so a cloud session installs fast. OCR is in the base install.
- **Fail closed.** The pre-tool hook blocks when `udb` is missing.
- **No test suite.** Changes are checked by running `udb` against a real vault.

## The citation contract

`vault_quote` is the only way to cite. See [references.md](references.md).
