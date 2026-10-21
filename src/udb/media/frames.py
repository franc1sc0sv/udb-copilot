"""Board stills of a class video: one still per complete board.

A board is complete just before the teacher erases it or changes slide; that
still holds everything written on it. Stills live in `derived/frames/`; they are
read with `vision.read_frames` and looked at through the `recording_frame` MCP
tool, never by opening the files.
"""
import json
import shutil
import subprocess
from pathlib import Path

from ..core.paths import derived_dir
from ..vault import registry
from .asr import ffmpeg_bin


def frames_dir(subject: str, source_id: str) -> Path:
    return derived_dir(subject) / "frames" / source_id


def _index_file(subject: str, source_id: str) -> Path:
    return frames_dir(subject, source_id) / "index.json"


def frame_index(subject: str, source_id: str) -> list[dict]:
    path = _index_file(subject, source_id)
    if not path.exists():
        return []
    frames = json.loads(path.read_text(encoding="utf-8")).get("frames", [])
    return [{"n": f["n"], "file": f["file"], "t": f.get("t"),
             "kind": f.get("kind"), "text": f.get("text", "")} for f in frames]


def _write_index(subject: str, source_id: str, frames: list[dict]) -> None:
    folder = frames_dir(subject, source_id)
    (folder / "index.json").write_text(json.dumps({"source_id": source_id, "frames": frames},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")


BOARD_STEP = 1.0     # seconds between looks
BOARD_DROP = 0.15    # ink falls 15 %: erased or new slide
BOARD_GROW = 0.30    # ink grew 30 % since the last kept still
BOARD_CHANGE = 0.06  # share of pixels that changed a lot: new slide, same ink


def _measure(img) -> tuple[float, object] | None:
    """Ink on the board, whatever its colour: the board is the large area that
    shares the background tone of the centre of the frame (white slide, black or
    green board); ink is what contrasts with it. None when nothing board-like fills
    the frame (a webcam alone)."""
    import numpy as np
    h, w = img.shape
    bg = float(np.median(img[h // 4:3 * h // 4, w // 4:3 * w // 4]))
    board = np.abs(img - bg) < 40
    if board.mean() < 0.35:
        return None
    ys, xs = np.nonzero(board)
    box = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return float((np.abs(box - bg) > 80).mean()), img


BOARD_PERSIST = 3.0  # seconds a drop or change must last (a hand passing is not an erase)


def board_states(samples, step: float = BOARD_STEP) -> list[dict]:
    """Pick stills from (t, gray image) samples. Each board keeps its best moment:
    the one with the most visible ink, i.e. the least covered by a hand."""
    import numpy as np
    persist = max(1, round(BOARD_PERSIST / step))
    kept: list[dict] = []
    best = None                      # (ink, t, img) of the current board
    low = moved = 0
    grown = None
    for t, raw in samples:
        cur = _measure(raw)
        if cur is None:
            if best:
                kept.append({"t": best[1], "kind": "before-change", "img": best[2]})
            best, low, moved, grown = None, 0, 0, None
            continue
        ink, img = cur
        if best is None:
            best, grown = (ink, t, img), ink
            continue
        low = low + 1 if best[0] > 0.003 and ink < best[0] * (1 - BOARD_DROP) else 0
        moved = (moved + 1 if ink < best[0] * 1.1
                 and (np.abs(img - best[2]) > 60).mean() > BOARD_CHANGE else 0)
        if low >= persist or moved >= persist:
            kept.append({"t": best[1], "kind": "before-erase" if low >= persist
                         else "before-change", "img": best[2]})
            best, low, moved, grown = (ink, t, img), 0, 0, ink
            continue
        if ink >= best[0]:
            best = (ink, t, img)
        if grown and ink > grown * (1 + BOARD_GROW):
            kept.append({"t": t, "kind": "growth"})
            grown = ink
    if best:
        kept.append({"t": best[1], "kind": "end", "img": best[2]})
    return _drop_partial(kept)


ERASED = 0.004  # share of the frame whose ink is gone in the next still: something was erased
MIN_GAP = 20.0  # seconds; closer complete stills (paper filmed by a camera) keep the later one


def _ink_mask(img):
    import numpy as np
    h, w = img.shape
    bg = float(np.median(img[h // 4:3 * h // 4, w // 4:3 * w // 4]))
    mask = np.abs(img - bg) > 80
    grown = mask.copy()  # tolerate a 2 px shake of the camera
    for dy in (-2, -1, 1, 2):
        grown |= np.roll(mask, dy, axis=0)
    for dx in (-2, -1, 1, 2):
        grown |= np.roll(mask, dx, axis=1)
    return mask, grown


def _drop_partial(kept: list[dict]) -> list[dict]:
    """A 'complete' still whose writing is all still there in the next complete still
    was the same page before the teacher finished it (or a hand made it look erased).
    Printed parts repeated on every board (the problem statement) do not count."""
    full = [k for k in kept if k["kind"] != "growth"]
    drop = set()
    for a, b in zip(full, full[1:], strict=False):
        if a.get("img") is None or b.get("img") is None:
            continue
        ink_a, _ = _ink_mask(a["img"])
        _, near_b = _ink_mask(b["img"])
        if (ink_a & ~near_b).mean() < ERASED:
            drop.add(id(a))
    full = [k for k in full if id(k) not in drop]
    for a, b in zip(full, full[1:], strict=False):
        if b["t"] - a["t"] < MIN_GAP:
            drop.add(id(a))
    return [{k: v for k, v in x.items() if k != "img"} for x in kept if id(x) not in drop]


def board_times(video: Path, step: float = BOARD_STEP) -> list[dict]:
    """When to take a still: the best moment of every complete board, plus big
    growth steps on long boards so stills line up with what is being said."""
    import numpy as np
    w, h = 320, 180
    proc = subprocess.Popen([ffmpeg_bin(), "-v", "error", "-i", str(video), "-vf",
                             f"fps={1 / step},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                            stdout=subprocess.PIPE)

    def samples():
        i = 0
        while True:
            buf = proc.stdout.read(w * h)
            if len(buf) < w * h:
                return
            yield i * step, np.frombuffer(buf, np.uint8).reshape(h, w).astype(np.int16)
            i += 1

    kept = board_states(samples(), step)
    proc.wait()
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
