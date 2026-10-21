---
name: udb-class
description: Writes or improves the explanation of one class in plain Spanish, one citation per paragraph and every class source used. Use it when the student wants to understand or document a class.
---

# /udb-class

1. `udb status <SUBJECT>` to see the class.
2. Missing folder: `udb class new <SUBJECT> <YYYY-MM-DD>` (it uses the class template).
3. No material: say so and stop. Material comes from `udb sync` or `udb ingest`.
4. Launch the `scribe` subagent to write `class.md`. Fill the front matter: title, unit,
   sources, methods, concepts, tasks, expects_assignment.
5. The scribe starts from `class_sources`: every source of the class must be cited
   (`source-not-used` is an error) and `pages-not-covered` lists slides no paragraph uses.
   Recordings count too: what the teacher said (`t=`) and the boards (`t=` + `frame=`).
6. Finish with `udb verify --path <file>` and fix what fails. `udb verify --fix` removes
   repeated citations inside a paragraph by itself.
