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

**Show it inline.** Call the `view` tool with kind `status` (and the subject, if one was named). If the `show_widget`
tool (visualize) is available, read its guide once, then pass the HTML unchanged as
`widget_code`. Do not rewrite it and do not open an artifact. Then add two or three
sentences: what is urgent and the next step. Without `show_widget` (phone, terminal),
answer from the JSON tool in a short list instead.
