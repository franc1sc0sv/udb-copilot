"""Class recordings that cannot be downloaded: what the student can see in Stream.

Teams recordings on SharePoint are usually view-only for students, so the video
file is out of reach and udb does not rebuild it from the stream. What the
student can see while watching is used instead, in their own browser (Claude
in Chrome, on the Stream page):

- `EXTRACT_JS` saves Stream's transcript panel as JSON; `import_transcript`
  turns it into a citable source with `t=` anchors.
- `BOARDS_JS` steps through the player and keeps a still of every complete
  board (the last state before the teacher erases or changes slide), like
  screenshots taken while watching; `import_boards` stores them as the
  recording's frames, read later by `vision.read_frames`.
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
// Each entry's React props carry ISO durations (PT1M1S); headers only show a time
// when the speaker changes, so they are the fallback.
const iso = d => { const m = /PT(?:([\d.]+)H)?(?:([\d.]+)M)?(?:([\d.]+)S)?/.exec(d || '');
  return m ? (+(m[1] || 0)) * 3600 + (+(m[2] || 0)) * 60 + (+(m[3] || 0)) : null; };
const props = el => { const k = Object.keys(el).find(x => x.startsWith('__reactFiber'));
  for (let f = k && el[k], i = 0; f && i < 8; f = f.return, i++)
    if (f.memoizedProps?.entry?.timestamp) return f.memoizedProps.entry;
  return null; };
const grab = () => document.querySelectorAll('[id^="sub-entry-"]').forEach(el => {
  const n = +el.id.split('-').pop();
  if (rows.has(n)) return;
  const e = props(el);
  const ts = document.getElementById('Header-timestamp-' + n)?.innerText.trim();
  const sp = document.getElementById('itemHeader-' + n)?.innerText.split('\n')[0].trim();
  rows.set(n, {n, start: e ? iso(e.timestamp) : (ts ? secs(ts) : null),
               end: e ? iso(e.endTime) : null, speaker: sp || null, text: el.innerText.trim()});
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

# Steps through the player every STEP seconds. Ink is measured only inside the light
# (board) area, so Teams' black background and webcam tiles do not count, and moments
# with no shared screen are skipped. Saves udb-boards-<ID>.json (JPEG stills).
BOARDS_JS = r"""
const RID = '__RID__', STEP = __STEP__, DROP = 0.15, GROW = 0.30;
const v = document.querySelector('video');
if (!v) throw new Error('no video on this page');
v.muted = true; v.pause();
const W = 320, H = 180;
const sm = document.createElement('canvas'); sm.width = W; sm.height = H;
const sx = sm.getContext('2d', {willReadFrequently: true});
const big = document.createElement('canvas'); big.width = v.videoWidth; big.height = v.videoHeight;
const bx = big.getContext('2d');
const seek = t => new Promise(r => { v.addEventListener('seeked', r, {once: true}); v.currentTime = t; });
// Background tabs clamp setTimeout to 1 s; a MessageChannel hop is not throttled.
const tick = () => new Promise(r => { const c = new MessageChannel(); c.port1.onmessage = () => r(); c.port2.postMessage(0); });
const settle = async () => { await tick(); await tick(); };
const measure = () => {
  sx.drawImage(v, 0, 0, W, H);
  const d = sx.getImageData(0, 0, W, H).data;
  const gray = new Uint8Array(W * H);
  let x0 = W, y0 = H, x1 = -1, y1 = -1, light = 0;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const i = (y * W + x) * 4, g = (d[i] + d[i + 1] + d[i + 2]) / 3;
    gray[y * W + x] = g;
    if (g > 200) { light++; if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  }
  if (light < W * H * 0.2) return null;
  let ink = 0, area = 0;
  for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) { area++; if (gray[y * W + x] < 150) ink++; }
  return {ink: ink / area, gray};
};
// Share of pixels that changed a lot: a new slide, even with the same amount of ink.
const changed = (a, b) => { let n = 0; for (let i = 0; i < a.length; i++) if (Math.abs(a[i] - b[i]) > 60) n++; return n / a.length; };
const kept = [];
const snap = (t, why) => { bx.drawImage(v, 0, 0); kept.push({t, why, jpg: big.toDataURL('image/jpeg', 0.88)}); };
const keepPrev = async (why, t) => { await seek(prevT); await settle(); snap(prevT, why); await seek(t); };
let prev = null, prevT = 0, lastKept = null;
const end = Math.floor(v.duration);
for (let t = 0; t <= end; t += STEP) {
  await seek(t); await settle();
  const cur = measure();
  if (cur === null) { if (prev) await keepPrev('before-change', t); prev = null; lastKept = null; continue; }
  if (prev && prev.ink > 0.003 && cur.ink < prev.ink * (1 - DROP)) {
    await keepPrev('before-erase', t); lastKept = null;
  } else if (prev && prev.ink > 0.003 && cur.ink < prev.ink * 1.1 && changed(prev.gray, cur.gray) > 0.06) {
    await keepPrev('before-change', t); lastKept = null;
  } else if (cur.ink > 0.003 && lastKept !== null && cur.ink > lastKept * (1 + GROW)) {
    snap(t, 'growth'); lastKept = cur.ink;
  }
  if (lastKept === null) lastKept = cur.ink;
  prev = cur; prevT = t;
}
if (prev !== null) { await seek(prevT); await settle(); snap(prevT, 'end'); }
const blob = new Blob([JSON.stringify({recording: RID, title: document.title, duration: end, frames: kept})],
  {type: 'application/json'});
const a = document.createElement('a');
a.href = URL.createObjectURL(blob); a.download = 'udb-boards-' + RID + '.json';
document.body.appendChild(a); a.click(); a.remove();
({frames: kept.length, complete: kept.filter(k => k.why !== 'growth').length, duration: end})
"""

FILE_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})_\d{6}")
SYSTEM_RE = re.compile(r"(empezó|detuvo|started|stopped) la transcripción|transcription", re.I)


def extract_js(rid: str) -> str:
    return EXTRACT_JS.replace("__RID__", rid.upper())


def boards_js(rid: str, step: int = 3) -> str:
    return BOARDS_JS.replace("__RID__", rid.upper()).replace("__STEP__", str(int(step)))


def import_boards(rid: str, file: str | Path) -> dict:
    """Store the board stills as the recording's frames (needs the transcript first)."""
    import base64

    from .frames import _write_index, frames_dir
    g = catalog.find(rid)
    if not g.get("source_id"):
        raise ValueError(f"{rid}: import the transcript first (udb recording import-stream {rid})")
    data = json.loads(Path(file).expanduser().read_text(encoding="utf-8"))
    out = frames_dir(g["subject"], g["source_id"])
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("b*.jpg"):
        old.unlink()
    frames = []
    for n, f in enumerate(sorted(data.get("frames", []), key=lambda f: f["t"]), 1):
        name = f"b{n:04d}.jpg"
        (out / name).write_bytes(base64.b64decode(f["jpg"].split(",", 1)[1]))
        frames.append({"n": n, "file": name, "t": float(f["t"]), "kind": f.get("why"),
                       "text": ""})
    _write_index(g["subject"], g["source_id"], frames)
    return catalog.update(rid, frames=len(frames))


def segments_from(entries: list[dict], duration: int) -> list[dict]:
    """Stream entries to transcript segments; system lines are dropped."""
    rows = [e for e in entries if e.get("text") and not SYSTEM_RE.search(e["text"])
            and e.get("start") is not None]
    out = []
    for i, e in enumerate(rows):
        end = e.get("end") or (rows[i + 1]["start"] if i + 1 < len(rows)
                               else (duration or e["start"] + 30))
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
    if g.get("source_id") and registry.get(g["subject"], g["source_id"]):
        # Re-import (better timings, edited transcript): same source, new text.
        rec = registry.get(g["subject"], g["source_id"])
        registry.source_file(g["subject"], rec["id"]).write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
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
