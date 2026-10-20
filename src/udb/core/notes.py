"""Markdown notes: front matter plus content blocks grouped by section."""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import schema
from .anchors import DEF_RE, REF_RE

FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
CALLOUT_RE = re.compile(r"^>\s*\[!(\w+)\]")
MIN_CONTENT_WORDS = 12


@dataclass
class Block:
    section: str
    start_line: int
    lines: list[str]
    is_callout: bool = False
    callout_kind: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def refs(self) -> list[str]:
        return REF_RE.findall(self.text)

    @property
    def is_table(self) -> bool:
        return all(line.strip().startswith("|") for line in self.lines if line.strip())

    @property
    def is_list(self) -> bool:
        return bool(re.match(r"^\s*([-*+]|\d+\.)\s", self.lines[0]))


@dataclass
class Note:
    path: str
    front: dict
    body: str
    blocks: list[Block]
    sections: list[str]

    def section_text(self, name: str) -> str:
        wanted = name.strip().lower()
        return "\n".join(b.text for b in self.blocks if b.section.strip().lower() == wanted)

    def has_section(self, name: str) -> bool:
        return any(s.strip().lower() == name.strip().lower() for s in self.sections)


def split_front_matter(text: str) -> tuple[dict, str, int]:
    """Raw front matter (keys as written), body and the body's first line."""
    if not text.startswith("---"):
        return {}, text, 0
    parts = text.split("\n")
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            raw = "\n".join(parts[1:i])
            try:
                front = yaml.safe_load(raw) or {}
            except yaml.YAMLError:
                front = _loose(raw)
            return (front if isinstance(front, dict) else {}), "\n".join(parts[i + 1:]), i + 1
    return {}, text, 0


def _loose(raw: str) -> dict:
    """`key: value` lines read as plain strings, for hand-written front matter that is
    not valid YAML (`method: -`, an unquoted colon in a title...)."""
    out = {}
    for line in raw.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and not key.startswith((" ", "\t", "-")):
            out[key.strip()] = value.strip().strip("'\"")
    return out


def front_matter(text: str) -> dict:
    """Front matter with canonical (English) keys and values."""
    return schema.normalize_front(split_front_matter(text)[0])


def content_words(text: str) -> int:
    _, body, _ = split_front_matter(text)
    lines = [ln for ln in body.split("\n")
             if ln.strip() and not ln.strip().startswith(("#", "<!--", "-->", "<!"))]
    return len(" ".join(lines).split())


def is_stub(path: Path) -> bool:
    """A note that still holds only the template comments."""
    return content_words(Path(path).read_text(encoding="utf-8")) < MIN_CONTENT_WORDS


def parse(path: str, text: str) -> Note:
    raw_front, body, offset = split_front_matter(text)
    blocks: list[Block] = []
    sections: list[str] = []
    section = ""
    in_fence = False
    in_comment = False
    current: list[str] = []
    start = 0

    def flush():
        nonlocal current
        if current:
            callout = CALLOUT_RE.match(current[0].strip())
            blocks.append(Block(section=section, start_line=start, lines=current,
                                is_callout=bool(callout),
                                callout_kind=callout.group(1).lower() if callout else None))
            current = []

    for i, line in enumerate(body.split("\n"), start=offset + 1):
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue
        if FENCE_RE.match(line):
            in_fence = not in_fence
            if not in_fence:
                current = []
            continue
        if in_fence:
            continue
        if DEF_RE.match(stripped):
            flush()
            continue
        heading = HEADING_RE.match(line)
        if heading:
            flush()
            section = heading.group(2).strip()
            sections.append(section)
            continue
        if not stripped:
            flush()
            continue
        if not current:
            start = i
        current.append(line)

    flush()
    return Note(path=path, front=schema.normalize_front(raw_front), body=body,
                blocks=blocks, sections=sections)


def load(path: Path) -> Note:
    from .paths import relative
    return parse(relative(path), Path(path).read_text(encoding="utf-8"))


def first_heading(raw: str) -> str | None:
    for line in raw.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return None
