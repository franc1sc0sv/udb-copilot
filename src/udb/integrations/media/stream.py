"""Class recordings that cannot be downloaded: what the student can see in Stream.

Teams recordings on SharePoint are usually view-only for students, so the video
file is out of reach and udb does not rebuild it from the stream (no audio or
video capture). What the student can see while watching is used instead:

- `TRANSCRIPT_FN` reads Stream's transcript panel: speaker, exact start and end
  of every entry. `import_transcript` makes it a citable source with `t=` anchors.
- `BOARDS_FN` steps through the player and keeps a still of every complete board
  (the last state before the teacher erases or changes slide), like screenshots
  taken while watching. Steps are dense (2 s) where the transcript shows the
  teacher solving an exercise and sparse elsewhere. `import_boards` stores them
  as the recording's frames, read later by `vision.read_frames`.

Both run in Claude in Chrome, in the student's own signed-in Chrome, through
`extract_js` / `boards_js`, which save the result to Downloads.
"""
import base64
import json
import re
import tempfile
from datetime import date
from pathlib import Path

from udb.domain.sources import index, registry
from udb.domain.text.normalize import slugify, strip_accents
from udb.integrations.media import catalog

TRANSCRIPT_FN = r"""
async () => {
  const sc = [...document.querySelectorAll('div.ms-FocusZone')]
    .find(d => d.scrollHeight > d.clientHeight + 200);
  if (!sc) throw new Error('transcript panel not found');
  const rows = new Map();
  const secs = s => s.split(':').map(Number).reduce((a, b) => a * 60 + b, 0);
  // Each entry's React props carry ISO durations (PT1M1S); headers only show a
  // time when the speaker changes, so they are the fallback.
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
  const tick = () => new Promise(r => setTimeout(r, 350));
  sc.scrollTop = 0; await tick(); grab();
  for (let y = 0; y <= sc.scrollHeight; y += Math.floor(sc.clientHeight * 0.6)) {
    sc.scrollTop = y; await tick(); grab();
  }
  let last = {start: 0, speaker: null};
  const entries = [...rows.values()].sort((a, b) => a.n - b.n)
    .map(r => { r.start ??= last.start; r.speaker ??= last.speaker; last = r; return r; });
  const v = document.querySelector('video');
  return {title: document.title, duration: Math.round(v?.duration || 0), entries};
}
"""

# Ink is measured only inside the light (board) area, so Teams' black background
# and webcam tiles do not count, and moments with no shared screen are skipped.
BOARDS_FN = r"""
async ({fine, coarse, spans}) => {
  const DROP = 0.15, GROW = 0.30;
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
  // The board is the area sharing the tone of the frame centre (white slide, black
  // or green board); ink is what contrasts with it.
  const measure = () => {
    sx.drawImage(v, 0, 0, W, H);
    const d = sx.getImageData(0, 0, W, H).data;
    const gray = new Uint8Array(W * H);
    for (let i = 0; i < W * H; i++) gray[i] = (d[i * 4] + d[i * 4 + 1] + d[i * 4 + 2]) / 3;
    const centre = [];
    for (let y = H / 4; y < 3 * H / 4; y += 2) for (let x = W / 4; x < 3 * W / 4; x += 2) centre.push(gray[y * W + x]);
    centre.sort((a, b) => a - b);
    const bg = centre[centre.length >> 1];
    let x0 = W, y0 = H, x1 = -1, y1 = -1, board = 0;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      if (Math.abs(gray[y * W + x] - bg) < 40) { board++; if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
    }
    if (board < W * H * 0.35) return null;
    let ink = 0, area = 0;
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) { area++; if (Math.abs(gray[y * W + x] - bg) > 80) ink++; }
    return {ink: ink / area, gray};
  };
  const changed = (a, b) => { let n = 0; for (let i = 0; i < a.length; i++) if (Math.abs(a[i] - b[i]) > 60) n++; return n / a.length; };
  const inSpan = t => spans.some(([a, b]) => t >= a && t <= b);
  const kept = [];
  const snap = (t, why) => { bx.drawImage(v, 0, 0); kept.push({t, why, jpg: big.toDataURL('image/jpeg', 0.9)}); };
  let prev = null, prevT = 0, lastKept = null;
  const keepPrev = async (why, t) => { await seek(prevT); await settle(); snap(prevT, why); await seek(t); };
  const end = Math.floor(v.duration);
  for (let t = 0; t <= end; t += inSpan(t) ? fine : coarse) {
    window.__udbBoardsT = t;
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
  return {title: document.title, duration: end, frames: kept};
}
"""

SAVE_JS = """
const blob = new Blob([JSON.stringify({recording: '__RID__', ...out})], {type: 'application/json'});
const a = document.createElement('a');
a.href = URL.createObjectURL(blob); a.download = 'udb-__KIND__-__RID__.json';
document.body.appendChild(a); a.click(); a.remove();
"""

FILE_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})_\d{6}")
SYSTEM_RE = re.compile(r"(empezó|detuvo|started|stopped) la transcripción|transcription", re.I)
# What a teacher says while solving an exercise on the board.
SOLVING_RE = re.compile(
    r"ejercicio|problema|resolv|sustitu|despej|reemplaz|calcul|encontr|apliqu|ecuacion|formula"
    r"|datos|tenemos que|nos queda|igual a|multiplic|divid|sumamos|restamos|configur|comando")
SOLVING_PAD = 20.0


def extract_js(rid: str) -> str:
    """For Claude in Chrome: read the transcript and save udb-stream-<ID>.json."""
    save = SAVE_JS.replace("__RID__", rid.upper()).replace("__KIND__", "stream")
    return (f"const out = await ({TRANSCRIPT_FN})();\n{save}"
            "({entries: out.entries.length, duration: out.duration})")


def boards_js(rid: str, fine: int = 2, coarse: int = 6, spans: list | None = None) -> str:
    """For Claude in Chrome: capture boards and save udb-boards-<ID>.json."""
    args = json.dumps({"fine": fine, "coarse": coarse, "spans": spans or []})
    save = SAVE_JS.replace("__RID__", rid.upper()).replace("__KIND__", "boards")
    return (f"const out = await ({BOARDS_FN})({args});\n{save}"
            "({frames: out.frames.length, duration: out.duration})")


def solving_spans(segments: list[dict], pad: float = SOLVING_PAD) -> list[list[float]]:
    """Time spans where the transcript sounds like an exercise being solved."""
    spans: list[list[float]] = []
    for s in segments:
        if not SOLVING_RE.search(strip_accents(s.get("text", "").lower())):
            continue
        a, b = max(0.0, s["start"] - pad), s.get("end", s["start"]) + pad
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    return spans


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


def import_transcript_data(rid: str, data: dict) -> dict:
    """Register a Stream transcript as the recording's source and transcript."""
    g = catalog.find(rid)
    segments = segments_from(data.get("entries", []), int(data.get("duration") or 0))
    if not segments:
        raise ValueError(f"{rid}: the transcript has no entries")
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
        rec = registry.register(g["subject"], tmp, kind="class", title=title, url=g["url"],
                                class_number=g.get("class"))
    out = index.transcript_file(g["subject"], rec["id"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"language": "es", "engine": "stream", "quality": "stream",
                               "segments": segments}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    index.reindex_subject(g["subject"])
    return catalog.update(rid, status="transcribed", source_id=rec["id"], title=title,
                          date=when, transcript="stream", segments=len(segments))


def import_transcript(rid: str, file: str | Path) -> dict:
    return import_transcript_data(rid, json.loads(Path(file).expanduser().read_text("utf-8")))


def import_boards_data(rid: str, data: dict) -> dict:
    """Store board stills as the recording's frames (needs the transcript first)."""
    from udb.integrations.media.frames import _write_index, frames_dir
    g = catalog.find(rid)
    if not g.get("source_id"):
        raise ValueError(f"{rid}: import the transcript first")
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


def import_boards(rid: str, file: str | Path) -> dict:
    return import_boards_data(rid, json.loads(Path(file).expanduser().read_text("utf-8")))


def class_day(g: dict) -> date | None:
    try:
        return date.fromisoformat((g.get("date") or "")[:10])
    except ValueError:
        return None
