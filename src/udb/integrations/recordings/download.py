"""Download a recording with yt-dlp, using the browser's Microsoft session.

Local only: it needs a browser where you are logged in to Microsoft (or an
exported cookies.txt). When that fails, download the video by hand and
`udb recording attach` it.
"""
import shutil
import subprocess
from pathlib import Path

from ...core.paths import index_dir
from ...core.text import slugify
from ...vault import registry
from . import catalog

VIDEO_SUFFIXES = (".mp4", ".mkv", ".webm", ".m4a", ".mov", ".mp3")


def download(rid: str, browser: str | None = None, dest: Path | None = None) -> Path:
    g = catalog.find(rid)
    cfg = catalog.config()
    dest = Path(dest or cfg.get("downloads") or (index_dir() / "downloads"))
    dest.mkdir(parents=True, exist_ok=True)
    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp is missing. Install it with: uv tool install yt-dlp")

    # Windows encrypts Edge and Chrome cookies (App-Bound Encryption), so
    # --cookies-from-browser often fails there. An exported cookies.txt works.
    cookies = cfg.get("cookies_file") or cfg.get("cookies_archivo")
    browser = browser or cfg.get("browser") or cfg.get("navegador") or "chrome"
    if cookies and Path(cookies).expanduser().exists():
        auth = ["--cookies", str(Path(cookies).expanduser())]
    else:
        auth = ["--cookies-from-browser", browser]

    template = str(dest / f"{g['id']}-{slugify(g['title'])}.%(ext)s")
    cmd = ["yt-dlp", *auth, "--no-playlist", "--newline",
           "-f", cfg.get("format") or cfg.get("formato") or "bv*+ba/b", "-o", template, g["url"]]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        output = proc.stderr or proc.stdout or ""
        if "cookie database" in output or "could not find" in output.lower():
            raise RuntimeError(
                f"cannot read {browser} cookies. Either export cookies.txt and set "
                f"cookies_file in config/recordings.yaml, or download the video by hand and "
                f"run: udb recording attach {g['id']} <file.mp4>")
        tail = "\n  ".join(output.strip().splitlines()[-4:])
        raise RuntimeError(f"yt-dlp failed (usually the Microsoft session):\n  {tail}\n"
                           f"Fallback: udb recording attach {g['id']} <file.mp4>")

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
    rec = registry.register(g["subject"], path, kind="class", title=g["title"], url=g["url"])
    return catalog.update(rid, status="downloaded", source_id=rec["id"], file=str(path),
                          bytes=path.stat().st_size)
