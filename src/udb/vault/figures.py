"""Figures from the course material (PDF pages, HTML images) as PNG files.

Text is cited with `vault_quote`; images are looked at. They land in
`vault/<SUBJECT>/figures/<SOURCE-ID>/`, which may be opened, plus an
`index.json` with source, page and caption. Originals in `sources/` are not
touched.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urljoin

from ..core.paths import subject_dir
from . import registry

CAPTION_RE = re.compile(r"(?i)^(figura|gr[aá]fic[oa]|imagen|tabla|figure)\s*\d+")


def figures_dir(code: str) -> Path:
    return subject_dir(code) / "figures"


def pdf_pages(src: Path, out: Path, dpi: int = 110) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(src), str(out / "page")],
                   check=True)
    return [{"file": p.name, "page": int(re.search(r"(\d+)\.png$", p.name).group(1))}
            for p in sorted(out.glob("page-*.png"))]


def _caption(img) -> str:
    """Nearest 'Figura N. ...' text around the image, or its alt text."""
    for node in [img, *img.parents]:
        for sib in (node.find_next_sibling(), node.find_previous_sibling()):
            if sib is not None:
                txt = sib.get_text(" ", strip=True)
                if CAPTION_RE.match(txt):
                    return txt[:200]
        alt = node.attrs.get("alt") if hasattr(node, "attrs") else None
        if alt:
            return alt[:200]
    return ""


def html_images(src: Path, out: Path, base_url: str = "", fetch=None
                ) -> tuple[list[dict], list[dict]]:
    """(saved, pending). `data:` images are saved; URLs need a `fetch` callable."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(src.read_text(encoding="utf-8", errors="replace"), "html.parser")
    saved, pending = [], []
    out.mkdir(parents=True, exist_ok=True)
    for n, img in enumerate(soup.find_all("img"), 1):
        s = img.get("src") or ""
        item = {"n": n, "caption": _caption(img),
                "src": "data:..." if s.startswith("data:") else s[:120]}
        if s.startswith("data:"):
            m = re.match(r"data:image/(\w+);base64,(.*)", s, re.S)
            if not m:
                pending.append({**item, "why": "data URI is not base64"})
                continue
            ext = "jpg" if m.group(1) == "jpeg" else m.group(1)
            name = f"img-{n:03d}.{ext}"
            (out / name).write_bytes(base64.b64decode(m.group(2)))
            saved.append({**item, "file": name})
        elif fetch is not None and s:
            try:
                data, ext = fetch(urljoin(base_url, s) if base_url else s)
            except Exception as exc:  # noqa: BLE001 - a broken image is reported, not fatal
                pending.append({**item, "why": f"{type(exc).__name__}: {exc}"[:160]})
                continue
            name = f"img-{n:03d}.{ext}"
            (out / name).write_bytes(data)
            saved.append({**item, "file": name})
        else:
            pending.append({**item, "why": "URL not downloaded"})
    return saved, pending


def extract(code: str, only: str | None = None, fetch=None, base_url: str = "",
            dpi: int = 110) -> dict:
    root = figures_dir(code)
    prev = root / "index.json"
    index: dict = json.loads(prev.read_text(encoding="utf-8")) if prev.exists() else {}
    for rec in registry.read_all(code):
        if only and rec["id"] != only:
            continue
        src = subject_dir(code) / rec["path"]
        if not src.exists():
            continue
        out = root / rec["id"]
        info = {"title": rec.get("title"), "class": rec.get("class"),
                "kind": src.suffix.lower(), "sha256": rec.get("sha256")}
        if src.suffix.lower() == ".pdf":
            info["pages"] = pdf_pages(src, out, dpi)
        elif src.suffix.lower() in {".html", ".htm"}:
            info["images"], info["pending"] = html_images(src, out, base_url, fetch)
            if not info["images"] and out.exists() and not any(out.iterdir()):
                out.rmdir()
        index[rec["id"]] = info
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    return index


def http_fetch(url: str) -> tuple[bytes, str]:
    import httpx

    r = httpx.get(url, timeout=30, follow_redirects=True)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    if not ctype.startswith("image/"):
        raise ValueError(f"not an image ({ctype or 'no content type'})")
    sub = ctype.split("/")[1].split(";")[0]
    return r.content, {"jpeg": "jpg", "svg+xml": "svg"}.get(sub, sub)
