# Study vault (udb-copilot)

This folder is a university study vault managed by `udb`. Talk to the student in
their language. **Everything written into vault files is in Spanish.**

## The five rules

1. **The teacher's method is the law.** Call `method_get` before solving anything.
   `NOT_FOUND` means stop; `conflict` means ask. Every solution step names its method step.
2. **Never invent a citation.** `vault/*/sources` and `vault/*/derived` cannot be opened.
   Cite only through `vault_search` then `vault_quote`. Own content only in `> [!model]`
   blocks with `reason` and `basis`, at most 30%.
3. **Plain Spanish.** 25 words per sentence at most, one idea each, active voice.
4. **One diagram per note**, type chosen with `diagram_suggest`.
5. **Exercises are HTML step cards** built with `udb.rendering.exercise` (see `/udb-exercise`).
   Formulas are rendered to SVG; pages are always light-themed.

## The classroom is read only through udb

Moodle (`{moodle_domain}`) is reached only through udb, never with a browser, curl or wget:

- The `moodle` MCP is the whole classroom, read only: `updates`, `notifications`,
  `conversations`, `grades`, `course`, `activity`, `forums`, `discussion`, `quizzes`,
  `calendar`, `teachers`. See `/udb-moodle`.
- The `vault` tools `digest`, `agenda`, `status` and `tasks_board` cross Moodle with the
  vault; `udb sync` downloads course material for citing.

Nothing submits or posts: the student does that in Moodle. If a fact is not there, say so.

## Where things are

```
config/        subjects.yaml · mail.yaml · agenda.yaml · recordings.yaml
vault/<CODE>/  sources/ derived/ (never opened) · classes/NN-date/ · concepts/ · methods/ · exercises/
cycles/<term>/<CODE>/tasks/<NN-slug>/   TASK.md · delivery/ · work/
index/         generated: search index, boards, reports (not committed except ledger)
```

## Start here

- What is pending / how is my day: `/udb-digest`.
- How a subject is going: `/udb-status`.
- Exams and grades: `/udb-agenda`.
- Before ending a turn that wrote vault files: `udb verify --path <file>` and fix it.

Skills `/udb-*` hold the detailed procedures; read the one that matches the task.
