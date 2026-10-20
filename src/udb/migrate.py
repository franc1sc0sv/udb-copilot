"""`udb migrate`: rewrite pre-0.1 Spanish keys to the canonical English ones.

Reading already accepts the old keys, so migrating is not urgent; it makes the
files match the docs. Every rewrite is idempotent.
"""
import json
from pathlib import Path

import yaml

from .core import notes, schema
from .core.paths import config_dir, cycles, index_dir, subject_codes, subject_dir

RECORDINGS_CONFIG = {"navegador": "browser", "formato": "format", "modelo": "model",
                     "calidad": "quality", "cookies_archivo": "cookies_file",
                     "umbral_escena": "scene_threshold", "ancho_frame": "frame_width"}
QUALITY = {"maxima": "max", "rapida": "fast"}
TASK_STATUS = {"pending": "todo", "done": "submitted"}


def _dump_front(front: dict) -> str:
    return yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=100).strip()


def migrate_note(path: Path, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    raw, body, _ = notes.split_front_matter(text)
    if not raw:
        return False
    front = schema.normalize_front(raw)
    if path.name == "TASK.md":
        method = front.pop("method", None)
        if "methods" not in front:
            front["methods"] = [] if method in (None, "-", "") else [method]
        front["status"] = TASK_STATUS.get(front.get("status"), front.get("status", "todo"))
        front.setdefault("repos", [])
    if front == raw:
        return False
    if not dry_run:
        path.write_text(f"---\n{_dump_front(front)}\n---\n{body}", encoding="utf-8")
    return True


def migrate_registry(code: str, dry_run: bool) -> bool:
    path = subject_dir(code) / "registry.jsonl"
    if not path.exists():
        return False
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    records = [json.loads(ln) for ln in lines]
    fixed = [schema.normalize_record(r) for r in records]
    if fixed == records:
        return False
    if not dry_run:
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in fixed),
                        encoding="utf-8")
    return True


def _rewrite_yaml(path: Path, change, dry_run: bool) -> bool:
    if not path.exists():
        return False
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    new = change(json.loads(json.dumps(data, default=str)))
    if new == json.loads(json.dumps(data, default=str)):
        return False
    if not dry_run:
        path.write_text(yaml.safe_dump(new, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return True


def _subjects(data: dict) -> dict:
    data["subjects"] = [schema.normalize_subject(s) for s in data.get("subjects", [])]
    return data


def _recordings_cfg(data: dict) -> dict:
    out = {RECORDINGS_CONFIG.get(k, k): v for k, v in data.items()}
    if out.get("quality") in QUALITY:
        out["quality"] = QUALITY[out["quality"]]
    return out


def _agenda(data: dict) -> dict:
    kinds = {"entrega": "assignment", "prueba": "exam", "foro": "forum", "proyecto": "project"}
    for spec in (data.get("subjects") or {}).values():
        if "avisos" in spec:
            spec["notices"] = spec.pop("avisos")
        for item in spec.get("items", []):
            item["kind"] = kinds.get(item.get("kind"), item.get("kind"))
    return data


def _overrides(data: dict) -> dict:
    for fix in (data.get("overrides") or {}).values():
        if fix.get("state") == "entregada":
            fix["state"] = "submitted"
    return data


def migrate_recordings_catalog(dry_run: bool) -> bool:
    from .integrations.recordings import catalog
    path = index_dir() / "recordings.json"
    if not path.exists():
        return False
    raw = json.loads(path.read_text(encoding="utf-8"))
    fixed = catalog.load()
    if fixed == raw:
        return False
    if not dry_run:
        catalog.save(fixed)
    return True


def run(dry_run: bool = False) -> list[str]:
    changed = []
    folders = ("classes", "concepts", "methods", "exercises", "notes")
    for code in subject_codes():
        for folder in folders:
            for path in sorted((subject_dir(code) / folder).rglob("*.md")):
                if migrate_note(path, dry_run):
                    changed.append(str(path))
        if migrate_registry(code, dry_run):
            changed.append(f"vault/{code}/registry.jsonl")
    for path in sorted(cycles().glob("*/*/tasks/*/TASK.md")):
        if migrate_note(path, dry_run):
            changed.append(str(path))
    for name, fn in (("subjects.yaml", _subjects), ("recordings.yaml", _recordings_cfg),
                     ("agenda.yaml", _agenda), ("agenda_overrides.yaml", _overrides)):
        if _rewrite_yaml(config_dir() / name, fn, dry_run):
            changed.append(f"config/{name}")
    if migrate_recordings_catalog(dry_run):
        changed.append("index/recordings.json")
    return changed
