"""`udb status`: the real state of every class, one row each, and the next step.

Offline: reads the vault, the registry, the recordings catalog, the last
verify report and the local TASK.md folders. No Moodle call, so it runs in
under a second and works anywhere.
"""
import json
from datetime import date

from udb.config.paths import get_subject, index_dir, subject_codes, subject_dir
from udb.domain import checks
from udb.domain.checks import coverage
from udb.domain.notes import document as notes
from udb.domain.planning import tasks
from udb.domain.sources import figures, registry
from udb.domain.study import classes
from udb.domain.text import lang

STAGES = ("no material", "write explanation", "method in conflict", "extract method",
          "fix verify errors", "solve assignment", "render lesson", "complete")


def _verify(path) -> dict:
    return checks.counts_for(path) if path.exists() else {}


def _recordings(code: str) -> dict[int, str]:
    from udb.integrations.media import catalog

    by_source = {}
    for r in catalog.board():
        if r["subject"] == code and r["source_id"]:
            by_source[r["source_id"]] = "transcribed" if r["transcribed"] else r["status"]
    out: dict[int, str] = {}
    for rec in registry.read_all(code):
        if rec.get("kind") == "class" and rec.get("class") is not None:
            out[rec["class"]] = by_source.get(rec["id"], "registered")
    return out


def _exercises_by_class(code: str) -> dict[int, list[str]]:
    from udb.domain.checks.exercises import exercise_paths, read_meta

    out: dict[int, list[str]] = {}
    for path in exercise_paths(code):
        if path.name == "assignment.md":
            continue
        if path.suffix == ".md":
            numbers = notes.front_matter(path.read_text(encoding="utf-8")).get("class")
        else:
            meta = read_meta(path) or {}
            numbers = meta.get("classes") or meta.get("class")
        for n in numbers if isinstance(numbers, list) else [numbers]:
            if str(n).isdigit():
                out.setdefault(int(n), []).append(path.name)
    return out


def class_rows(code: str) -> list[dict]:
    figure_index = figures.figures_dir(code) / "index.json"
    figs = json.loads(figure_index.read_text(encoding="utf-8")) if figure_index.exists() else {}
    recordings = _recordings(code)
    exercises = _exercises_by_class(code)
    task_by_id = {t["id"]: t for t in tasks.local_tasks(code)}
    rows = []
    for folder in classes.list_classes(code):
        front = folder.front
        sources = classes.sources_for(code, folder.number)
        methods = classes.methods_for(code, folder)
        note = folder.path / "class.md"
        verify = _verify(note)
        linked_tasks = [task_by_id[t] for t in front.get("tasks") or [] if t in task_by_id]
        expects = front.get("expects_assignment", None)
        row = {
            "class": folder.number, "date": folder.date, "title": front.get("title") or "",
            "material": len(sources),
            "recording": recordings.get(folder.number, "-"),
            "explanation": "written" if folder.has("class.md") else (
                "template" if note.exists() else "missing"),
            "methods": [{"slug": m.slug, "status": m.status} for m in methods],
            "exercises": exercises.get(folder.number, []),
            # Only a class that says it has an assignment can be missing one.
            "assignment": ("written" if folder.has("assignment.md")
                           else "missing" if expects is True else "n/a"),
            "tasks": [{"id": t["id"], "status": t["status"]} for t in linked_tasks],
            "lesson": folder.has("lesson.html"),
            "figures": sum(1 for s in sources if s["id"] in figs),
            "material_covered": coverage.material_coverage(code, folder.number, note)["percent"],
            "verify_errors": verify.get("errors", 0),
            "verify_warnings": verify.get("warnings", 0),
            "path": str(folder.path),
        }
        row["stage"] = stage(row)
        rows.append(row)
    return rows


def stage(row: dict) -> str:
    if not row["material"]:
        return "no material"
    if row["explanation"] != "written":
        return "write explanation"
    if any(m["status"] == "conflict" for m in row["methods"]):
        return "method in conflict"
    if row["verify_errors"]:
        return "fix verify errors"
    if row["assignment"] == "missing" and not row["exercises"]:
        return "solve assignment"
    if not row["lesson"]:
        return "render lesson"
    return "complete"


NEXT = {
    "no material": "udb sync {code}",
    "write explanation": "udb class write {n} {code}",
    "method in conflict": "ask the teacher, then edit vault/{code}/methods/",
    "fix verify errors": "udb verify {code}",
    "solve assignment": "udb exercise <file>",
    "render lesson": "udb class lesson {n} {code}",
}


def subject_status(code: str) -> dict:
    info = get_subject(code)
    rows = class_rows(code)
    unclassified = [r["id"] for r in registry.read_all(code)
                    if r.get("class") is None and not r.get("superseded_by")]
    todo = next((r for r in rows if r["stage"] != "complete"), None)
    return {
        "code": code, "name": info.get("name", code), "kind": info.get("kind", "general"),
        "classes": rows,
        "summary": {s: sum(1 for r in rows if r["stage"] == s) for s in STAGES},
        "sources": len(registry.read_all(code)),
        "unclassified_sources": len(unclassified),
        "concepts": len(list((subject_dir(code) / "concepts").glob("*.md"))),
        "next": NEXT[todo["stage"]].format(code=code, n=todo["class"]) if todo else None,
        "hint": None if rows else (f"{len(unclassified)} sources not assigned to any class. "
                                   f"Create classes: udb class new {code} <date>"),
    }


def build(code: str | None = None) -> dict:
    codes = [code.upper()] if code else subject_codes()
    data = {"generated": date.today().isoformat(),
            "subjects": [subject_status(c) for c in codes]}
    (index_dir() / "status.json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    return data


def render(data: dict):
    from udb.rendering.jinja import env

    out = index_dir() / "status.html"
    out.write_text(env().get_template("status.html.j2").render(
        **data, summary_title=lang.section("summary")), encoding="utf-8")
    return out
