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
             "text": f.get("text", f.get("texto", ""))} for f in frames]


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
