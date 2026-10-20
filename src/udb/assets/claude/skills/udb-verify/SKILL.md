---
name: udb-verify
description: Checks the whole vault without a model: real citations, plain language, exercises that follow the method, topic coverage.
---

# /udb-verify

Run `udb verify [SUBJECT]` (or `--path <file>`). Group the findings by file, errors first.
Fix the errors yourself when you wrote the file; otherwise list them with the command that
helps (`vault_quote` for a broken quote, `udb method` for a missing method).
