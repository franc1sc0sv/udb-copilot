"""Class folders: `vault/<SUBJECT>/classes/NN-YYYY-MM-DD/`."""
import re
from dataclasses import dataclass
from pathlib import Path

from ..core import notes
from ..core.paths import classes_dir, get_subject
from . import methods, registry

FOLDER_RE = re.compile(r"^(\d{2})-(\d{4}-\d{2}-\d{2})$")


@dataclass
class ClassFolder:
    number: int
    date: str
    path: Path

    @property
    def slug(self) -> str:
        return f"{self.number:02d}-{self.date}"

    def has(self, name: str) -> bool:
        """True when the file exists and is more than an empty template."""
        target = self.path / name
        if not target.exists():
            return False
        if target.suffix != ".md":
            return target.stat().st_size > 0
        return not notes.is_stub(target)

    @property
    def front(self) -> dict:
        target = self.path / "class.md"
        return notes.front_matter(target.read_text(encoding="utf-8")) if target.exists() else {}

    @property
    def diagrams(self) -> int:
        folder = self.path / "diagrams"
        return len(list(folder.glob("*"))) if folder.exists() else 0


def list_classes(code: str) -> list[ClassFolder]:
    folder = classes_dir(code)
    if not folder.exists():
        return []
    out = []
    for child in sorted(folder.iterdir()):
        m = FOLDER_RE.match(child.name)
        if child.is_dir() and m:
            out.append(ClassFolder(int(m.group(1)), m.group(2), child))
    return out


def get_class(code: str, number: int) -> ClassFolder | None:
    return next((c for c in list_classes(code) if c.number == number), None)


def create(code: str, number: int, date: str) -> ClassFolder:
    folder = classes_dir(code) / f"{number:02d}-{date}"
    (folder / "diagrams").mkdir(parents=True, exist_ok=True)
    return ClassFolder(number, date, folder)


def next_number(code: str) -> int:
    return max((c.number for c in list_classes(code)), default=0) + 1


def sources_for(code: str, number: int) -> list[dict]:
    return [r for r in registry.read_all(code)
            if r.get("class") == number and not r.get("superseded_by")]


def methods_for(code: str, folder: ClassFolder) -> list[methods.Method]:
    """Methods taught in this class: declared in class.md or pointing back to it."""
    declared = folder.front.get("methods") or []
    if isinstance(declared, str):
        declared = [s.strip() for s in declared.split(",") if s.strip()]
    found = {m.slug: m for m in methods.list_all(code) if folder.number in m.classes}
    for slug in declared:
        m = methods.read(code, slug)
        if m:
            found[slug] = m
    return list(found.values())


def subject_kind(code: str) -> str:
    try:
        return get_subject(code).get("kind", "general")
    except KeyError:
        return "general"
