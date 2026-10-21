"""Pre-render TeX formulas to inline SVG, so pages show math in any viewer.

Pages must not depend on a CDN or on JavaScript: viewers block them and the
student sees raw `\\(x\\)`. This runs MathJax once, in Node, at build time.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).parent / "static" / "render_math.cjs"
RAW_TEX_RE = re.compile(r"\\\(|\\\[|\\frac|\\sqrt")


class MathError(RuntimeError):
    pass


def mathjax_root() -> Path:
    return Path(os.environ.get("UDB_MATHJAX_ROOT", "~/.cache/udb/mathjax")).expanduser()


def install() -> Path:
    """`npm install mathjax-full` into the cache folder (once per machine)."""
    root = mathjax_root()
    if (root / "node_modules" / "mathjax-full").exists():
        return root
    if not shutil.which("npm"):
        raise MathError("npm is missing; install Node.js to render formulas")
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["npm", "install", "--prefix", str(root), "--no-audit", "--no-fund",
                    "mathjax-full@3"], check=True, capture_output=True)
    return root


def render_html(html: str) -> str:
    if not shutil.which("node"):
        raise MathError("node is missing; install Node.js to render formulas")
    root = install()
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.html", Path(tmp) / "out.html"
        src.write_text(html, encoding="utf-8")
        proc = subprocess.run(["node", str(SCRIPT), str(src), str(dst)], capture_output=True,
                              text=True, env={**os.environ, "MJ_ROOT": str(root)})
        if proc.returncode != 0:
            raise MathError("TeX errors:\n" + proc.stderr.strip())
        out = dst.read_text(encoding="utf-8")
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    if report["errors"]:
        raise MathError(f"{report['errors']} TeX errors")
    return out


def problems(html: str) -> list[str]:
    """What would make a page show raw math or reach the network."""
    body = html[html.find("<body"):]
    text = re.sub(r"<svg.*?</svg>", "", body, flags=re.S)
    text = re.sub(r"<(script|style)\b.*?</\1>", "", text, flags=re.S)
    out = []
    if RAW_TEX_RE.search(text):
        out.append("raw TeX left in the page")
    if re.search(r"<script[^>]+src=[\"']https?://", html):
        out.append("external script")
    if re.search(r"<link[^>]+href=[\"']https?://", html):
        out.append("external stylesheet")
    return out
