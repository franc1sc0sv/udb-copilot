"""Class recordings that cannot be downloaded: read Stream's own transcript.

Teams recordings on SharePoint are usually view-only for students, so the video
file is out of reach and udb does not try to work around that. What the student
can see is the transcript panel. `EXTRACT_JS` runs in the student's browser
(Claude in Chrome, on the Stream page) and saves the transcript as a JSON file;
`import_transcript` turns that file into a citable source with `t=` anchors.
"""
import json
import re
import tempfile
from datetime import date
from pathlib import Path

from ...core.text import slugify
from ...vault import index, registry
from . import catalog

# Run on the Stream page with the transcript panel open. Scrolls the virtual
# list, keeps speaker and start time per entry, and saves udb-stream-<ID>.json.
EXTRACT_JS = r"""
const RID = '__RID__';
const sc = [...document.querySelectorAll('div.ms-FocusZone')]
  .find(d => d.scrollHeight > d.clientHeight + 200);
if (!sc) throw new Error('open the Transcript panel first');
const rows = new Map();
const secs = s => s.split(':').map(Number).reduce((a, b) => a * 60 + b, 0);
const grab = () => document.querySelectorAll('[id^="sub-entry-"]').forEach(el => {
  const n = +el.id.split('-').pop();
  if (rows.has(n)) return;
  const ts = document.getElementById('Header-timestamp-' + n)?.innerText.trim();
  const sp = document.getElementById('itemHeader-' + n)?.innerText.split('\n')[0].trim();
  rows.set(n, {n, start: ts ? secs(ts) : null, speaker: sp || null, text: el.innerText.trim()});
});
sc.scrollTop = 0; await new Promise(r => setTimeout(r, 700)); grab();
for (let y = 0; y <= sc.scrollHeight; y += Math.floor(sc.clientHeight * 0.6)) {
  sc.scrollTop = y; await new Promise(r => setTimeout(r, 400)); grab();
}
let last = {start: 0, speaker: null};
const entries = [...rows.values()].sort((a, b) => a.n - b.n)
  .map(r => { r.start ??= last.start; r.speaker ??= last.speaker; last = r; return r; });
const v = document.querySelector('video');
const blob = new Blob([JSON.stringify({recording: RID, title: document.title,
  duration: Math.round(v?.duration || 0), entries})], {type: 'application/json'});
const a = document.createElement('a');
a.href = URL.createObjectURL(blob); a.download = 'udb-stream-' + RID + '.json';
document.body.appendChild(a); a.click(); a.remove();
({entries: entries.length, duration: Math.round(v?.duration || 0)})
"""

FILE_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})_\d{6}")
SYSTEM_RE = re.compile(r"(empezó|detuvo|started|stopped) la transcripción|transcription", re.I)


def extract_js(rid: str) -> str:
    return EXTRACT_JS.replace("__RID__", rid.upper())


def segments_from(entries: list[dict], duration: int) -> list[dict]:
    """Stream entries to transcript segments; system lines are dropped."""
    rows = [e for e in entries if e.get("text") and not SYSTEM_RE.search(e["text"])
            and e.get("start") is not None]
    out = []
    for i, e in enumerate(rows):
        end = rows[i + 1]["start"] if i + 1 < len(rows) else (duration or e["start"] + 30)
        out.append({"start": float(e["start"]), "end": float(max(end, e["start"])),
                    "text": e["text"].strip(), "speaker": e.get("speaker")})
    return out


def class_date(title: str) -> str | None:
    found = FILE_DATE_RE.search(title or "")
    return f"{found[1]}-{found[2]}-{found[3]}" if found else None


def import_transcript(rid: str, file: str | Path) -> dict:
    """Register a Stream transcript JSON as the recording's source and transcript."""
    g = catalog.find(rid)
    data = json.loads(Path(file).expanduser().read_text(encoding="utf-8"))
    segments = segments_from(data.get("entries", []), int(data.get("duration") or 0))
    if not segments:
        raise ValueError(f"{file} has no transcript entries")
    title = re.sub(r"\.mp4$", "", data.get("title") or g["title"])
    when = class_date(title) or g.get("date")
    tmp = Path(tempfile.mkdtemp(prefix="udb-stream-")) / f"{g['id']}-{slugify(title)}.json"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    rec = registry.register(g["subject"], tmp, kind="class", title=title, url=g["url"])
    out = index.transcript_file(g["subject"], rec["id"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"language": "es", "engine": "stream", "quality": "stream",
                               "segments": segments}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    index.reindex_subject(g["subject"])
    return catalog.update(rid, status="transcribed", source_id=rec["id"], title=title,
                          date=when, transcript="stream", segments=len(segments))


def class_day(g: dict) -> date | None:
    try:
        return date.fromisoformat((g.get("date") or "")[:10])
    except ValueError:
        return None
