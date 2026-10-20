---
name: udb-tasks
description: Homework folders and project repos: create a task, see the task board, find linked project repos. Use it when the student starts a new assignment or asks about their projects.
---

# /udb-tasks

- Board: `udb tasks [SUBJECT]` joins Moodle with `cycles/<term>/<SUBJECT>/tasks/*/TASK.md`.
- New task: `udb task new <SUBJECT> <slug> --moodle-url <url>` (the board joins on that URL).
  `delivery/` holds exactly what gets uploaded; `work/` holds drafts and scripts.
- Project code lives in its own repo, linked from TASK.md `repos:`. `udb projects` lists them
  with branch and last commit; `udb projects --clone` clones the missing ones into `work/`.
- When a task is submitted, set `status: submitted` in TASK.md.
