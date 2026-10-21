"""Model-free checks over the vault. `udb verify` and the write hook call these."""
import json
from datetime import datetime
from pathlib import Path

from udb.config.paths import index_dir, relative
from udb.domain.checks import citations, clarity, coverage, exercises
from udb.domain.notes.findings import Finding


def check_file(path: Path) -> list[Finding]:
    """Everything that applies to one file."""
    path = Path(path)
    findings: list[Finding] = []
    if path.suffix == ".md":
        findings += citations.check_paths([path]) + clarity.check_paths([path])
    findings += exercises.check_path(path)
    return findings


def check_subject(code: str | None = None) -> list[Finding]:
    return (citations.check_subject(code)
            + clarity.check_paths(citations.note_paths(code))
            + exercises.check_paths(exercises.exercise_paths(code))
            + exercises.check_methods(code)
            + coverage.check_subject(code))


def write_report(findings: list[Finding], scope: str) -> Path:
    """`index/verify.json`: error and warning counts per file, read by `udb status`."""
    out = index_dir() / "verify.json"
    data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"files": {}}
    if scope == "all":
        data["files"] = {}
    else:
        data["files"] = {k: v for k, v in data["files"].items() if not k.startswith(scope)}
    for f in findings:
        entry = data["files"].setdefault(f.path, {"errors": 0, "warnings": 0, "codes": []})
        entry["errors" if f.level == "error" else "warnings"] += 1
        if f.code not in entry["codes"]:
            entry["codes"].append(f.code)
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def counts_for(path: Path) -> dict:
    out = index_dir() / "verify.json"
    if not out.exists():
        return {}
    return json.loads(out.read_text(encoding="utf-8"))["files"].get(relative(path), {})


def apply_fixes(findings: list[Finding]) -> list[str]:
    """Apply the automatic repairs (moved quotes) in place. Returns what changed."""
    from udb.config.paths import home

    changed = []
    by_file: dict[str, list[Finding]] = {}
    for f in findings:
        if f.fix:
            by_file.setdefault(f.path, []).append(f)
    for rel, items in by_file.items():
        path = Path(rel) if Path(rel).is_absolute() else home() / rel
        lines = path.read_text(encoding="utf-8").split("\n")
        for f in items:
            line = lines[f.line - 1]
            if f.fix["old"] in line:
                lines[f.line - 1] = line.replace(f.fix["old"], f.fix["new"], 1)
                changed.append(f"{rel}:{f.line}  {f.fix['old']} -> {f.fix['new']}")
        path.write_text("\n".join(lines), encoding="utf-8")
    return changed
