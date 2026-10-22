# udb-copilot (engine)

Python package `udb`, managed with uv. Lint: `uv run --extra dev ruff check src`.

## Rules

- **No tests.** Do not write, add or restore tests or a `tests/` folder. Verify changes by
  running the real commands against a vault (`udb ...` in `~/projects/udb/study-vault`).
- Code, identifiers and docs in English; text written into vault files is Spanish.
- Keep one way to do each thing: no legacy aliases, no second backend "just in case".
- Install for local use with `uv tool install --editable '.[asr,vision,agent]'`.
