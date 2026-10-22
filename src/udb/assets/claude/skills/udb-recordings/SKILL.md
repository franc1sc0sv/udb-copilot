---
name: udb-recordings
description: Class recordings: find them in Moodle, read Teams/Stream transcripts with the student's browser, transcribe downloadable videos, and catch what the teacher said about exams, dates, grading and announcements. Use it after every class or when the student asks what was said in a recording.
---

# /udb-recordings

`udb recording board` says what is missing.

## Teams recordings (SharePoint / Stream): usually view-only

Students cannot download them, and udb does not try to work around that (no stream
capture). What the student can see is Stream's transcript. Local only, with Claude in
Chrome and the student's own UDB session:

1. `udb recording url <ID>` prints the address of Stream's player; open it in a new tab.
2. Open the **Transcripción** panel if it is closed.
3. `udb recording stream-js <ID>` prints a script; run it with `javascript_tool` on that
   tab. It saves `udb-stream-<ID>.json` to the Downloads folder (text only).
4. `udb recording import-stream <ID>`: the transcript becomes a citable source with
   `t=` anchors, and the radar runs.
5. Boards: `udb recording stream-js <ID> --boards` on the same tab, then
   `udb recording import-stream <ID> --boards` (stills, board reading on the GPU).
6. Close the tab.

udb has no Microsoft login of its own: if the tab asks to sign in, the student
signs in themselves.

If the teacher allows downloads (or shares the file), use the downloadable path below
instead: Whisper is more accurate than Stream's transcript.

## Downloadable videos (YouTube embeds, shared files)

```
udb recording download IRD-001    # local only
udb recording transcribe IRD-001  # GPU, local only
udb recording frames IRD-001      # board states + text on each
udb recording process IRD-001     # all of the above + radar
```

## The radar: what must not be missed

`udb recording radar <ID>` (or the `recording_radar` tool) finds exams, deadlines, date
changes, grading rules, "esto viene en el examen" and announcements, and resolves
"el próximo jueves" against the class day. No model: it quotes, it cannot invent.

- Show every hit as **"dicho en clase, por confirmar"** with the minute and the quote.
- Check it against Moodle (`moodle` MCP: `calendar`, `assignments`) and mail. If they
  disagree, say so; never overwrite an official date with a spoken one.
- The daily digest lists hits from the last 14 days under "Dicho en clase".

Frames are looked at with `recording_frame`, never opened directly.
