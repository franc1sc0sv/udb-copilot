---
name: udb-agenda
description: Assessment agenda: what was graded last week and what comes next, crossing the learning route, Moodle, mail, Calendar and recordings. Use it when the student asks about exams, deadlines or grades.
---

# /udb-agenda

1. Run `udb agenda [SUBJECT]` (or the `agenda` MCP tool). It writes `index/agenda.html` and `index/agenda.json`.
2. Summarise per subject: grade breakdown (graded, waiting, ahead) and what is needed to pass;
   upcoming activities with state and days; route notices (`bad` first); Moodle announcements.
3. Read the sources block. A failed mail or calendar source is reported, never hidden.
4. If an alert says the route changed or no longer backs a date, check it with
   `vault_search`/`vault_quote`, fix `config/agenda.yaml`, and run again.
5. "Route dates the plan does not explain" are candidate missing activities.

The passing grade does not come from the route: say so when computing what is needed.
A submission uploaded by a teammate goes in `config/agenda_overrides.yaml`.
The route decides what is graded and its weight; Moodle decides when it closes. If they differ, give both dates.

**Show it inline.** Call the `view` tool with kind `agenda` (and the subject, if one was named). If the `show_widget`
tool (visualize) is available, read its guide once, then pass the HTML unchanged as
`widget_code`. Do not rewrite it and do not open an artifact. Then add two or three
sentences: what is urgent and the next step. Without `show_widget` (phone, terminal),
answer from the JSON tool in a short list instead.
