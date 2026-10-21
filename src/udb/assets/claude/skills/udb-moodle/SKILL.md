---
name: udb-moodle
description: The virtual classroom without opening Moodle: what is new, grades, private messages, notifications, forum threads, quizzes, assignment instructions and teacher feedback. Read only. Use it whenever the student asks about anything in Moodle.
---

# /udb-moodle

The `moodle` MCP reads everything the student can see. It cannot submit, post or mark
anything as read: those stay in Moodle, and you say so.

## Which tool

| The student asks | Tool |
|---|---|
| What is new? | `updates` (hours=72), then `notifications` |
| Did a teacher write to me? | `conversations`, then `conversation` |
| My grades | `grades` (one subject or all) |
| What does assignment X ask? | `assignments` for the cmid, then `activity` |
| What did the teacher post in the forum? | `forums`, `discussions`, `discussion` |
| When is the quiz, how long is it? | `quizzes`, then `activity` for my attempts |
| What is in week N? | `course` with `section` |
| Teacher's email | `teachers` |
| A file attached to a post or feedback | `download`, then read it |

## Rules

- Subjects are codes from `config/subjects.yaml` (IRD, AVM...). A course without a code
  still works with its Moodle id from `courses`.
- Quote the teacher literally when the exact wording matters (instructions, rubric,
  dates), and say where it came from: forum, message, assignment or notification.
- Dates are local time. Count days left from today.
- Course material meant for citing in notes goes through `udb sync`, not `download`.
- If the grade column says "-", it is not graded yet; do not guess.
- Show lists as an inline view when there are more than a few rows.
