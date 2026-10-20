---
name: udb-digest
description: Morning summary and 'what is pending': classes today, days left to every evaluation, what is due in 72 hours, new classroom activity and teacher mail. Use it when the student asks what is pending, how their day looks, or from the phone.
---

# /udb-digest

1. Call the `digest` MCP tool (or `udb digest --json`). It uses no model: every fact is real.
2. Answer in the student's language, short, phone-friendly:
   - Today's classes.
   - What is due in the next 72 hours, in bold.
   - The countdown: days to each evaluation, with weight when known.
   - New in the classroom: assignments created or changed, announcements.
   - Teacher mail, one line each.
3. If a source failed (`sources` with ok=false), say which one. Never hide it.
4. For one subject in depth, follow with `status <SUBJECT>` or `agenda <SUBJECT>`.

Scheduled runs (06:00 routine): build the email from the JSON, Spanish, warm and brief,
subject "Mañanita: tu día <fecha>". In alert mode (`alerts=true`), send nothing when `empty` is true.

**Show it inline.** Call the `view` tool with kind `digest`. If the `show_widget`
tool (visualize) is available, read its guide once, then pass the HTML unchanged as
`widget_code`. Do not rewrite it and do not open an artifact. Then add two or three
sentences: what is urgent and the next step. Without `show_widget` (phone, terminal),
answer from the JSON tool in a short list instead.
