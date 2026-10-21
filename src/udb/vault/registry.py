"""Per-subject source registry (`vault/<SUBJECT>/registry.jsonl`)."""
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from ..core.paths import registry_path, sources_dir, subject_dir

KINDS = ("course", "class", "external", "exercise", "moodle")
ID_RE = re.compile(r"^SRC-([A-Z0-9]+)-(\d{4})$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_all(code: str) -> list[dict]:
    path = registry_path(code)
    if not path.exists():
        return []
    return [json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def get(code: str, source_id: str) -> dict | None:
    return next((r for r in read_all(code) if r["id"] == source_id), None)


def lookup(source_id: str) -> dict | None:
    """Record for any source id, whatever its subject."""
    try:
        return get(subject_of(source_id), source_id)
    except ValueError:
        return None


def next_id(code: str) -> str:
    used = [int(m.group(2)) for r in read_all(code) if (m := ID_RE.match(r["id"]))]
    return f"SRC-{code.upper()}-{max(used, default=0) + 1:04d}"


def find_by_hash(code: str, digest: str) -> dict | None:
    return next((r for r in read_all(code)
                 if r.get("sha256") == digest and not r.get("superseded_by")), None)


def append(code: str, record: dict) -> dict:
    path = registry_path(code)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def rewrite(code: str, records: list[dict]) -> None:
    path = registry_path(code)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                    encoding="utf-8")


def ensure_subject(code: str) -> None:
    base = subject_dir(code)
    for sub in ("sources", "derived/text", "derived/transcripts", "classes",
                "concepts", "methods", "exercises"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    registry_path(code).touch()


def register(code: str, path: Path, kind: str, title: str | None = None,
             url: str | None = None, class_number: int | None = None,
             moodle_id: str | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"invalid kind: {kind} (use one of {', '.join(KINDS)})")
    ensure_subject(code)
    path = Path(path).expanduser().resolve()
    digest = sha256(path)
    existing = find_by_hash(code, digest)
    if existing:
        return existing

    source_id = next_id(code)
    dest = sources_dir(code) / f"{source_id}{path.suffix.lower()}"
    if path != dest:
        dest.write_bytes(path.read_bytes())
    return append(code, {
        "id": source_id,
        "subject": code.upper(),
        "kind": kind,
        "title": title or path.stem,
        "path": dest.relative_to(subject_dir(code)).as_posix(),
        "original_name": path.name,
        "url": url,
        "class": class_number,
        "moodle_id": moodle_id,
        "sha256": digest,
        "retrieved_at": date.today().isoformat(),
        "superseded_by": None,
    })


def source_file(code: str, source_id: str) -> Path:
    rec = get(code, source_id)
    if not rec:
        raise KeyError(f"unknown source: {source_id}")
    return subject_dir(code) / rec["path"]


def subject_of(source_id: str) -> str:
    m = ID_RE.match(source_id)
    if not m:
        raise ValueError(f"invalid source id: {source_id}")
    return m.group(1)


CLASS_FILE_RE = re.compile(r"\bclase[_ -]?(\d{1,2})\.html?$", re.I)
CLASS_TITLE_RE = re.compile(r"^\s*(?:clase|material|semana|sesi[oó]n)\s*(\d{1,2})\b", re.I)


def guess_class(title: str | None, filename: str | None) -> int | None:
    """The class a course file belongs to, from how Moodle names it ("Material 3",
    "Clase 3 - ...", clase3.html). Learning routes, guides and exam instructions
    belong to the whole subject and get None."""
    for text, pattern in ((filename or "", CLASS_FILE_RE), (title or "", CLASS_TITLE_RE)):
        m = pattern.search(text)
        if m and 0 < int(m.group(1)) < 60:
            return int(m.group(1))
    return None


def assign_classes(code: str) -> list[tuple[str, int]]:
    """Fill `class` where it is missing; a class set by hand is never changed."""
    records = read_all(code)
    changed = []
    for r in records:
        if r.get("class") or r.get("kind") not in ("course", "exercise"):
            continue
        n = guess_class(r.get("title"), r.get("original_name"))
        if n:
            r["class"] = n
            changed.append((r["id"], n))
    if changed:
        rewrite(code, records)
    return changed


def add_alias(code: str, source_id: str, moodle_id: str) -> None:
    """Another Moodle link to a file already registered (same content)."""
    records = read_all(code)
    for r in records:
        if r["id"] == source_id and moodle_id != r.get("moodle_id"):
            aliases = r.setdefault("moodle_aliases", [])
            if moodle_id not in aliases:
                aliases.append(moodle_id)
    rewrite(code, records)


def register_version(code: str, path: Path, kind: str, moodle_id: str, **fields) -> tuple[dict, str]:
    """Register what Moodle shows under `moodle_id`, keeping versions: unchanged content is
    skipped, edited content becomes a new source and the old one is `superseded_by` it,
    so notes citing the old text get told. Returns (record, "new" | "updated" | "same")."""
    current = [r for r in read_all(code)
               if r.get("moodle_id") == moodle_id and not r.get("superseded_by")]
    digest = sha256(Path(path))
    if current and current[-1].get("sha256") == digest:
        return current[-1], "same"
    rec = register(code, path, kind, moodle_id=moodle_id, **fields)
    if not current:
        return rec, "new"
    records = read_all(code)
    for r in records:
        if r["id"] in {c["id"] for c in current}:
            r["superseded_by"] = rec["id"]
    rewrite(code, records)
    return rec, "updated"
