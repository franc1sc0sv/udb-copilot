---
name: udb-status
description: Shows the state of every class of a subject (material, recording, explanation, method, exercises, assignment, lesson, citation errors) and the next step. Use it at the start of any study session or when the student asks how a subject is going.
---

# /udb-status

Run `udb status [SUBJECT]` (or the `status` MCP tool). It is offline and fast.

Show one short table per subject, then say in one sentence the next step and the command that does it.
If a class has a method in `conflict`, say it first: it blocks that class's exercises.
If a subject has sources but no classes, offer to create the class folders (`udb class new`).
`index/status.html` is the full board; offer it as a file when the student is on a computer.
