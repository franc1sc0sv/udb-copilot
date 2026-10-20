"""The teacher's method for a topic: an ordered list of steps, each one cited."""
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..core import lang, notes
from ..core.paths import methods_dir
from ..core.schema import METHOD_STATES

STEP_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")


@dataclass
class Method:
    slug: str
    path: Path
    subject: str
    status: str
    steps: list[str] = field(default_factory=list)
    front: dict = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return self.status in ("confirmed", "provisional") and bool(self.steps)

    @property
    def classes(self) -> list[int]:
        raw = self.front.get("classes", self.front.get("class"))
        if raw is None:
            return []
        values = raw if isinstance(raw, list) else [raw]
        return [int(v) for v in values if str(v).isdigit()]


def path_for(code: str, slug: str) -> Path:
    return methods_dir(code) / f"{slug}.md"


def read(code: str, slug: str) -> Method | None:
    path = path_for(code, slug)
    if not path.exists():
        return None
    note = notes.load(path)
    table = lang.get()
    heading = re.compile(table["method_steps_heading"])
    bold = re.compile(table["step_bold"], re.IGNORECASE)
    steps = []
    for block in note.blocks:
        if not heading.match(block.section.strip().lower()):
            continue
        for line in block.lines:
            m = STEP_RE.match(line) or bold.match(line)
            if m:
                steps.append(m.group(2).strip())
    status = str(note.front.get("status", "provisional")).lower()
    return Method(slug=slug, path=path, subject=code.upper(), status=status, steps=steps,
                  front=note.front)


def list_all(code: str) -> list[Method]:
    folder = methods_dir(code)
    if not folder.exists():
        return []
    return [m for p in sorted(folder.glob("*.md")) if (m := read(code, p.stem))]


def valid_status(status: str) -> bool:
    return status in METHOD_STATES
