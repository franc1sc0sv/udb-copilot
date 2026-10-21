---
name: udb-note
description: Writes one atomic concept note in plain Spanish, with citations and a diagram. Use it when the student wants to understand a term or idea.
---

# /udb-note

Launch the `scribe` subagent. One note, one idea, every section the subject kind requires
(`udb note new <SUBJECT> <term>` writes the template). One citation per paragraph (a
passage from `vault_quote` that backs it all); examples and analogies in
`> [!example]` / `> [!analogy]` boxes. At least one mermaid diagram. Finish with `udb verify --path <file>`.
