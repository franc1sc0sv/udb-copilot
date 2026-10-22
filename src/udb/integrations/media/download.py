"""Download a recording with yt-dlp (YouTube and other public links).

Teams recordings are view-only for students: read them with Claude in Chrome
(`udb recording stream-js`). A video you got some other way is linked with
`udb recording attach`.
"""
import shutil
import subprocess
from pathlib import Path

from udb.config.paths import index_dir
from udb.domain.sources import registry
from udb.domain.text.normalize import slugify
from udb.integrations.media import catalog

VIDEO_SUFFIXES = (".mp4", ".mkv", ".webm", ".m4a", ".mov", ".mp3")


def download(rid: str, dest: Path | None = None) -> Path:
    g = catalog.find(rid)
    cfg = catalog.config()
    dest = Path(dest or cfg.get("downloads") or (index_dir() / "downloads"))
    dest.mkdir(parents=True, exist_ok=True)
    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp is missing. Install it with: uv tool install yt-dlp")

    template = str(dest / f"{g['id']}-{slugify(g['title'])}.%(ext)s")
    cmd = ["yt-dlp", "--no-playlist", "--newline",
           "-f", cfg.get("format") or "bv*+ba/b", "-o", template, g["url"]]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n  ".join((proc.stderr or proc.stdout or "").strip().splitlines()[-4:])
        hint = (f"Teams recordings are view-only: udb recording stream-js {g['id']} "
                "(Claude in Chrome)" if "sharepoint" in g["url"] or "meetingrecap" in g["url"]
                else f"udb recording attach {g['id']} <file.mp4>")
        raise RuntimeError(f"yt-dlp failed:\n  {tail}\nInstead: {hint}")

    videos = [p for p in sorted(dest.glob(f"{g['id']}-*"), key=lambda p: p.stat().st_mtime)
              if p.suffix.lower() in VIDEO_SUFFIXES]
    if not videos:
        raise RuntimeError(f"yt-dlp finished but left no video in {dest}")
    attach(rid, videos[-1])
    return videos[-1]


def attach(rid: str, file: str | Path) -> dict:
    """Link a video you downloaded yourself to its catalog entry."""
    g = catalog.find(rid)
    path = Path(file).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")
    if path.suffix.lower() not in VIDEO_SUFFIXES:
        raise ValueError(f"not a video or audio file: {path.name}")
    rec = registry.register(g["subject"], path, kind="class", title=g["title"], url=g["url"],
                            class_number=g.get("class"))
    return catalog.update(rid, status="downloaded", source_id=rec["id"], file=str(path),
                          bytes=path.stat().st_size)
