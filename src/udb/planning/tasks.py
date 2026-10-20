"""Homework folders and the task board.

Each task lives in `cycles/<term>/<SUBJECT>/tasks/<NN-slug>/TASK.md`:

    ---
    id: 02-challenge-2-trunks-vtp
    subject: IRD
    term: 2026-2
    title: Desafío 2
    moodle_url: https://.../mod/assign/view.php?id=2274947
    status: todo            # todo | in-progress | submitted | graded
    due: 2026-09-30
    methods: [configure-trunks-vtp]
    deliverables: [delivery/video.mp4]
    repos:                  # project code lives in its own repo
      - url: git@github.com:me/project.git
        path: work/project
    ---

The board joins those files with Moodle by `moodle_url`.
"""
import subprocess
import time
from pathlib import Path

from ..core import notes
from ..core.paths import cycles

STATUSES = ("todo", "in-progress", "submitted", "graded")
LEGACY_STATUS = {"pending": "todo", "done": "submitted"}


def read_task(path: Path) -> dict:
    task = notes.front_matter(path.read_text(encoding="utf-8"))
    task["folder"] = path.parent
    task.setdefault("id", path.parent.name)
    task.setdefault("subject", path.parents[2].name)
    task.setdefault("term", path.parents[3].name)
    task["status"] = LEGACY_STATUS.get(str(task.get("status", "todo")), task.get("status", "todo"))
    methods = task.get("methods", task.get("method"))
    if isinstance(methods, str):
        methods = [] if methods in ("-", "") else [m.strip() for m in methods.split(",")]
    task["methods"] = methods or []
    task["repos"] = [r if isinstance(r, dict) else {"url": r} for r in task.get("repos") or []]
    return task


def local_tasks(code: str | None = None) -> list[dict]:
    found = []
    for path in sorted(cycles().glob("*/*/tasks/*/TASK.md")):
        task = read_task(path)
        if code and task["subject"].upper() != code.upper():
            continue
        found.append(task)
    return found


def days_left(due: int, now: float | None = None) -> int | None:
    return int((due - (now or time.time())) // 86400) if due else None


def board(moodle_rows: list[dict], code: str | None = None) -> list[dict]:
    """One row per Moodle activity, plus local-only tasks with no Moodle match."""
    local = local_tasks(code)
    by_url = {t.get("moodle_url"): t for t in local if t.get("moodle_url")}
    rows, used = [], set()
    for item in moodle_rows:
        task = by_url.get(item["url"])
        if task:
            used.add(item["url"])
        rows.append({"subject": item["subject"], "title": item["name"], "due": item["due"],
                     "days": days_left(item["due"]), "moodle": item["status"],
                     "local": task["status"] if task else "no folder",
                     "methods": task["methods"] if task else [],
                     "folder": str(task["folder"]) if task else None, "url": item["url"]})
    for task in local:
        if task.get("moodle_url") in used:
            continue
        rows.append({"subject": task["subject"], "title": task.get("title", task["id"]),
                     "due": 0, "days": None, "moodle": "-", "local": task["status"],
                     "methods": task["methods"], "folder": str(task["folder"]), "url": None})
    return rows


def _git(folder: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def projects(code: str | None = None) -> list[dict]:
    """Every project repo linked from a TASK.md, with its local state."""
    out = []
    for task in local_tasks(code):
        for repo in task["repos"]:
            path = task["folder"] / repo.get("path", Path(repo["url"]).stem)
            cloned = (path / ".git").exists()
            out.append({
                "subject": task["subject"], "task": task["id"], "url": repo["url"],
                "path": str(path), "cloned": cloned,
                "branch": _git(path, "branch", "--show-current") if cloned else None,
                "last_commit": _git(path, "log", "-1", "--format=%cs %s") if cloned else None,
                "dirty": bool(_git(path, "status", "--porcelain")) if cloned else None})
    return out


def clone_projects(code: str | None = None) -> list[dict]:
    results = []
    for p in projects(code):
        if p["cloned"]:
            results.append({**p, "action": "already cloned"})
            continue
        proc = subprocess.run(["git", "clone", p["url"], p["path"]], capture_output=True,
                              text=True)
        results.append({**p, "action": "cloned" if proc.returncode == 0
                        else f"failed: {proc.stderr.strip().splitlines()[-1:]}"})
    return results
