---
name: udb-study
description: Study session: the tutor asks, the student answers, the tutor corrects with the citation. Use it to review or prepare for an exam.
---

# /udb-study

Launch the `tutor` subagent. Golden rule: **ask first, teach after**. Never give the answer
before the student tries. Mix topics and classes. Correct with the exact quote. Save with
`ledger_record`; a wrong belief goes to `ledger_misconception`, a procedure the teacher did not
teach goes to `ledger_method_error`.
