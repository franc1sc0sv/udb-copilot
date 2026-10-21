"""Class note (markdown) to a lesson page with a clickable source sidebar."""
import re
from pathlib import Path
from urllib.parse import quote

import markdown as md

from ..core import anchors, lang, notes
from ..vault import registry
from . import math_svg
from .jinja import env

CALLOUT_RE = re.compile(r"^>\s*\[!(\w+)\]\s*(.*)$")
REF_HTML_RE = re.compile(r"\[\^([A-Za-z0-9_-]+)\]")
DEF_LINE_RE = re.compile(r"^\[\^[A-Za-z0-9_-]+\]:")
MERMAID_RE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
MATH_RE = re.compile(r"\\\[.*?\\\]|\\\(.*?\\\)|\$\$.*?\$\$|\$[^$\n]+?\$", re.DOTALL)


def callouts_to_html(text: str) -> str:
    labels = lang.get()["callouts"]
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = CALLOUT_RE.match(lines[i].strip())
        if not m:
            out.append(lines[i])
            i += 1
            continue
        kind = m.group(1).lower()
        # The text after [!kind] is the box title, not its body.
        title = (m.group(2) or "").strip()
        body: list[str] = []
        i += 1
        while i < len(lines) and lines[i].lstrip().startswith(">"):
            body.append(lines[i].lstrip()[1:].lstrip())
            i += 1
        out += [f'<div class="callout {kind}" markdown="1">',
                f'<span class="label">{title or labels.get(kind, kind.title())}</span>', "",
                *body, "", "</div>"]
    return "\n".join(out)


def _protect(pattern: re.Pattern, text: str, tag: str, group: int) -> tuple[str, list[str]]:
    blocks: list[str] = []

    def keep(match: re.Match) -> str:
        blocks.append(match.group(group).strip() if group else match.group(0))
        return f"\n@@{tag}{len(blocks) - 1}@@\n" if tag == "MERMAID" else f"@@{tag}{len(blocks) - 1}@@"

    return pattern.sub(keep, text), blocks


def _restore(html: str, mermaid: list[str], math: list[str]) -> str:
    for i, block in enumerate(mermaid):
        div = f'<div class="mermaid">{block}</div>'
        html = html.replace(f"<p>@@MERMAID{i}@@</p>", div).replace(f"@@MERMAID{i}@@", div)
    for i, block in enumerate(math):
        if block.startswith("$$"):
            block = "\\[" + block[2:-2] + "\\]"
        elif block.startswith("$"):
            block = "\\(" + block[1:-1] + "\\)"
        safe = block.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = html.replace(f"@@MATH{i}@@", safe)
    return html


def refs_to_buttons(html: str, keys: set[str]) -> str:
    def swap(match: re.Match) -> str:
        key = match.group(1)
        if key not in keys:
            return match.group(0)
        return f'<button class="cita" data-key="{key}" title="Ver la fuente">{key}</button>'
    return REF_HTML_RE.sub(swap, html)


def locator(anchor: anchors.Anchor) -> str:
    f = anchor.fields
    if anchor.is_model:
        return f"basado en {f.get('basis', '?')}"
    bits = [f"página {f['page']}" if "page" in f else "", f"minuto {f['t']}" if "t" in f else "",
            f.get("url", ""), f"consultado {f['retrieved']}" if "retrieved" in f else ""]
    return " · ".join(b for b in bits if b) or "sin localizador"


def _prose(quote_text: str) -> str:
    text = re.sub(r"\\[A-Za-z]+|[{}\\^_]", " ", MATH_RE.sub(" ", quote_text))
    best = max((t.strip() for t in re.split(r"\s{2,}|[|]", text)), key=len, default="")
    return re.sub(r"\s+", " ", best).strip(" .,;:")


def deep_link(anchor: anchors.Anchor) -> str:
    """Source URL with a #:~:text= fragment that scrolls to the quote."""
    if anchor.is_model or not anchor.source_id:
        return ""
    url = (registry.lookup(anchor.source_id) or {}).get("url")
    if not url:
        return ""
    text = _prose(anchor.quote)
    if len(text) > 60:
        text = text[:60].rsplit(" ", 1)[0].strip(" .,;:")
    return url if len(text) < 12 else f"{url}#:~:text={quote(text, safe='').replace('-', '%2D')}"


def build_sources(definitions: dict[str, anchors.Anchor]) -> list[dict]:
    return [{"key": key, "source": "Explicación de Claude" if a.is_model else a.source_id,
             "loc": locator(a), "quote": a.quote, "reason": a.fields.get("reason", ""),
             "model": a.is_model, "url": deep_link(a)} for key, a in definitions.items()]


def note_body(raw: str, keys: set[str]) -> str:
    _, body, _ = notes.split_front_matter("\n".join(
        ln for ln in raw.split("\n") if not DEF_LINE_RE.match(ln.strip())))
    body, mermaid = _protect(MERMAID_RE, body, "MERMAID", 1)
    body, math = _protect(MATH_RE, body, "MATH", 0)
    body = re.sub(r"^#\s+.*$", "", callouts_to_html(body), count=1, flags=re.MULTILINE)
    html = md.markdown(body, extensions=["tables", "fenced_code", "attr_list", "md_in_html"])
    html = refs_to_buttons(_restore(html, mermaid, math), keys)
    return html.replace("<table>", '<div class="tablewrap"><table>').replace(
        "</table>", "</table></div>")


def render_note(path: Path, offline_math: bool = True) -> str:
    raw = path.read_text(encoding="utf-8")
    front = notes.front_matter(raw)
    definitions, _ = anchors.parse(raw)
    page = env().get_template("lesson.html.j2").render(
        titulo=front.get("title") or notes.first_heading(raw) or path.stem,
        asignatura=front.get("subject", ""), clase=front.get("class"),
        fecha=front.get("date", ""), contenido=note_body(raw, set(definitions)),
        fuentes=build_sources(definitions))
    return math_svg.render_html(page) if offline_math and MATH_RE.search(raw) else page


def write_lesson(note_path: Path, out_path: Path | None = None) -> Path:
    out_path = out_path or note_path.parent / "lesson.html"
    out_path.write_text(render_note(note_path), encoding="utf-8")
    return out_path
