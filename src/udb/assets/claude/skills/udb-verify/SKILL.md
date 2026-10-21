---
name: udb-verify
description: Checks the whole vault without a model: real citations, one citation per paragraph, every class source used, plain language, exercises that follow the method, topic coverage.
---

# /udb-verify

Run `udb verify [SUBJECT]` (or `--path <file>`). Group the findings by file, errors first.
Fix the errors yourself when you wrote the file; otherwise list them with the command that
helps (`vault_quote` for a broken quote, `udb method` for a missing method).

Citations v3 findings:

| Code | Meaning | What to do |
|---|---|---|
| `repeated-citation` | same anchor twice in one paragraph | `udb verify --fix` keeps only the last |
| `many-citations` | 3+ anchors of one source in a paragraph | quote one passage that backs it all |
| `trivial-quote` | quote under 8 words, not shown literally | quote the 1-3 sentences explained |
| `weak-support` | the passage shares no word with its paragraph | probably the wrong quote |
| `source-not-used` | a source of the class is never cited | read it (`vault_search`) and use it |
| `pages-not-covered` | slides of a cited source no paragraph uses | cover them or say why not |
| `figure-description-quoted` | quoted the model's description of a drawing | describe it in a `[!model]` box |

`udb status` shows how much of each class's material the note covers.
