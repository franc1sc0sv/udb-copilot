"""Paths inside the data home, and the subject list."""
from __future__ import annotations

from pathlib import Path

import yaml

from . import schema, settings


def home() -> Path:
    return settings.get().home


def vault() -> Path:
    return settings.get().vault


def config_dir() -> Path:
    return settings.get().config


def index_dir() -> Path:
    path = settings.get().index
    path.mkdir(parents=True, exist_ok=True)
    return path


def cycles() -> Path:
    return settings.get().cycles


def subject_dir(code: str) -> Path:
    return vault() / code.upper()


def sources_dir(code: str) -> Path:
    return subject_dir(code) / "sources"


def derived_dir(code: str) -> Path:
    return subject_dir(code) / "derived"


def classes_dir(code: str) -> Path:
    return subject_dir(code) / "classes"


def methods_dir(code: str) -> Path:
    return subject_dir(code) / "methods"


def registry_path(code: str) -> Path:
    return subject_dir(code) / "registry.jsonl"


def load_yaml(name: str) -> dict:
    path = config_dir() / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def save_yaml(name: str, data: dict) -> Path:
    path = config_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def load_subjects() -> list[dict]:
    return [schema.normalize_subject(s) for s in load_yaml("subjects.yaml").get("subjects", [])]


def get_subject(code: str) -> dict:
    for s in load_subjects():
        if s["code"].upper() == code.upper():
            return s
    raise KeyError(f"unknown subject: {code}")


def subject_codes() -> list[str]:
    configured = [s["code"].upper() for s in load_subjects()]
    if configured:
        return configured
    return sorted(p.name for p in vault().glob("*") if p.is_dir())


def relative(path: Path) -> str:
    """Path as shown in findings: relative to the data home when possible."""
    try:
        return str(Path(path).resolve().relative_to(home()))
    except ValueError:
        return str(path)


PROTECTED_PARTS = ("sources", "derived")


def is_protected(path: str | Path, cwd: Path | None = None) -> bool:
    """True for files under vault/<SUBJECT>/sources or derived.

    Relative paths resolve against `cwd` (the hook passes the session's
    directory), so `vault/AVM/sources/x.pdf` is caught from any folder.
    """
    raw = Path(path).expanduser()
    if not raw.is_absolute():
        raw = (cwd or Path.cwd()) / raw
    try:
        resolved = raw.resolve()
    except (OSError, RuntimeError):
        resolved = raw
    try:
        rel = resolved.relative_to(vault())
    except ValueError:
        return False
    return len(rel.parts) >= 2 and rel.parts[1] in PROTECTED_PARTS


def subject_of_path(path: Path) -> str | None:
    try:
        rel = Path(path).resolve().relative_to(vault())
    except ValueError:
        return None
    return rel.parts[0] if rel.parts else None
