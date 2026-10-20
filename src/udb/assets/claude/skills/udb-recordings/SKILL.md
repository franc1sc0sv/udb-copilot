---
name: udb-recordings
description: Class recordings: find them in Moodle, download, transcribe, extract frames and scan for exam mentions. Download and transcription run only on the student's computer.
---

# /udb-recordings

`udb recording board` says what is missing.

```
udb recording discover            # finds the links in Moodle
udb recording download IRD-001    # needs the browser's Microsoft session (local only)
udb recording transcribe IRD-001  # GPU, local only
udb recording frames IRD-001      # one frame per screen change, plus OCR
udb recording radar IRD-001       # what was said about exams and dates
udb recording process IRD-001     # all of the above
```

The radar uses no model: it finds and quotes, so it cannot invent an exam, but it does not
understand irony. Frames are looked at with `recording_frame`, never opened directly.
