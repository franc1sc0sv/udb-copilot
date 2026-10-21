"""One still frame per screen change, plus the text on each slide (OCR).

A new slide is a scene change, so this captures what the teacher showed and
did not say out loud. Frames live in `derived/`; read them through the
`recording_frame` MCP tool, not by opening the files.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

from ...core.paths import derived_dir
from ...vault import registry
from .asr import ffmpeg_bin


def frames_dir(subject: str, source_id: str) -> Path:
    return derived_dir(subject) / "frames" / source_id


def _index_file(subject: str, source_id: str) -> Path:
    folder = frames_dir(subject, source_id)
    legacy = folder / "indice.json"
    return legacy if legacy.exists() and not (folder / "index.json").exists() else folder / "index.json"


def frame_index(subject: str, source_id: str) -> list[dict]:
    path = _index_file(subject, source_id)
    if not path.exists():
        return []
    frames = json.loads(path.read_text(encoding="utf-8")).get("frames", [])
    return [{"n": f["n"], "file": f.get("file", f.get("archivo")), "t": f.get("t"),
             "kind": f.get("kind"), "text": f.get("text", f.get("texto", ""))} for f in frames]


def _write_index(subject: str, source_id: str, frames: list[dict]) -> None:
    folder = frames_dir(subject, source_id)
    (folder / "index.json").write_text(json.dumps({"source_id": source_id, "frames": frames},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "indice.json").unlink(missing_ok=True)


def extract(subject: str, source_id: str, threshold: float = 0.35, every: int | None = None,
            width: int = 1280) -> dict:
    video = registry.source_file(subject, source_id)
    if not video.exists():
        raise FileNotFoundError(f"{video} does not exist")
    out = frames_dir(subject, source_id)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    times = out / "times.txt"
    if every:
        vf = f"fps=1/{every},scale={width}:-2"
    else:
        vf = f"select=gt(scene\\,{threshold}),metadata=print:file={times.as_posix()},scale={width}:-2"
    subprocess.run([ffmpeg_bin(), "-y", "-i", str(video), "-vf", vf, "-vsync", "vfr",
                    "-q:v", "3", str(out / "f%04d.jpg")], check=True, capture_output=True)
    images = sorted(out.glob("f*.jpg"))
    if every:
        stamps = [i * every for i in range(len(images))]
    else:
        body = times.read_text(encoding="utf-8", errors="replace") if times.exists() else ""
        stamps = [float(m) for m in re.findall(r"pts_time:([\d.]+)", body)]
    frames = [{"n": n + 1, "file": img.name, "t": stamps[n] if n < len(stamps) else None,
               "text": ""} for n, img in enumerate(images)]
    _write_index(subject, source_id, frames)
    return {"source_id": source_id, "total": len(frames), "dir": str(out)}


BOARD_STEP = 1.0     # seconds between looks
BOARD_DROP = 0.15    # ink falls 15 %: erased or new slide
BOARD_GROW = 0.30    # ink grew 30 % since the last kept still
BOARD_CHANGE = 0.06  # share of pixels that changed a lot: new slide, same ink


def _measure(img) -> tuple[float, object] | None:
    """Ink inside the light (board) area; None when nothing board-like is shown
    (Teams black background, webcam only)."""
    import numpy as np
    light = img > 200
    if light.mean() < 0.2:
        return None
    ys, xs = np.nonzero(light)
    box = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return float((box < 150).mean()), img


def board_times(video: Path, step: float = BOARD_STEP) -> list[dict]:
    """When to take a still: the last moment of every complete board, plus big
    growth steps on long boards so stills line up with what is being said."""
    import numpy as np
    w, h = 320, 180
    proc = subprocess.Popen([ffmpeg_bin(), "-v", "error", "-i", str(video), "-vf",
                             f"fps={1 / step},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                            stdout=subprocess.PIPE)
    kept: list[dict] = []
    prev = prev_t = last = None
    i = 0
    while True:
        buf = proc.stdout.read(w * h)
        if len(buf) < w * h:
            break
        t = i * step
        i += 1
        cur = _measure(np.frombuffer(buf, np.uint8).reshape(h, w).astype(np.int16))
        if cur is None:
            if prev:
                kept.append({"t": prev_t, "kind": "before-change"})
            prev = last = None
            continue
        ink, img = cur
        if prev and prev[0] > 0.003 and ink < prev[0] * (1 - BOARD_DROP):
            kept.append({"t": prev_t, "kind": "before-erase"})
            last = None
        elif (prev and prev[0] > 0.003 and ink < prev[0] * 1.1
              and (np.abs(img - prev[1]) > 60).mean() > BOARD_CHANGE):
            kept.append({"t": prev_t, "kind": "before-change"})
            last = None
        elif ink > 0.003 and last is not None and ink > last * (1 + BOARD_GROW):
            kept.append({"t": t, "kind": "growth"})
            last = ink
        if last is None:
            last = ink
        prev, prev_t = cur, t
    proc.wait()
    if prev:
        kept.append({"t": prev_t, "kind": "end"})
    return kept


def extract_boards(subject: str, source_id: str, step: float = BOARD_STEP,
                   width: int = 1920) -> dict:
    """One full-resolution still per complete board (the default for class videos)."""
    try:
        import numpy  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("board stills need numpy: uv tool install 'udb-copilot[vision]'") from exc
    video = registry.source_file(subject, source_id)
    if not video.exists():
        raise FileNotFoundError(f"{video} does not exist")
    out = frames_dir(subject, source_id)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    frames = []
    for n, k in enumerate(board_times(video, step), 1):
        name = f"b{n:04d}.jpg"
        subprocess.run([ffmpeg_bin(), "-v", "error", "-ss", f"{k['t']:.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", f"scale='min({width},iw)':-2", "-q:v", "2", "-y",
                        str(out / name)], check=True)
        frames.append({"n": n, "file": name, "t": k["t"], "kind": k["kind"], "text": ""})
    _write_index(subject, source_id, frames)
    return {"source_id": source_id, "total": len(frames),
            "complete": sum(f["kind"] != "growth" for f in frames), "dir": str(out)}


def frame_path(subject: str, source_id: str, n: int) -> Path:
    for f in frame_index(subject, source_id):
        if int(f["n"]) == int(n):
            return frames_dir(subject, source_id) / f["file"]
    raise KeyError(f"frame {n} of {source_id} does not exist")


def ocr(subject: str, source_id: str) -> int:
    """Read the text on each frame. Optional: needs the `ocr` extra."""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise RuntimeError("OCR engine missing: uv tool install 'udb-copilot[ocr]'") from exc
    engine = RapidOCR()
    folder = frames_dir(subject, source_id)
    frames = frame_index(subject, source_id)
    read = 0
    for f in frames:
        result, _ = engine(str(folder / f["file"]))
        lines = [r[1].strip() for r in (result or []) if r[1].strip()]
        f["text"] = "\n".join(lines)
        read += 1 if lines else 0
    _write_index(subject, source_id, frames)
    return read
