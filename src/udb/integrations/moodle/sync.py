"""Read-only Moodle workflows: material sync, assignments, announcements."""
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path

from ...core import settings
from ...core.paths import get_subject, load_subjects
from ...core.text import normalize
from ...vault import ingest, registry
from . import client


def _course_id(code: str) -> int:
    course_id = get_subject(code).get("moodle_course_id")
    if not course_id:
        raise client.MoodleError(f"{code} has no moodle_course_id in config/subjects.yaml")
    return int(course_id)


def _courses(code: str | None) -> dict[int, str]:
    subjects = [get_subject(code)] if code else load_subjects()
    by_course = {int(s["moodle_course_id"]): s["code"] for s in subjects
                 if s.get("moodle_course_id")}
    if not by_course:
        raise client.MoodleError("no subject has moodle_course_id in config/subjects.yaml")
    return by_course


def sync_subject(code: str, section_map: dict[str, int] | None = None,
                 dry_run: bool = False) -> dict:
    """Download and index every course file not yet in the registry."""
    course_id = _course_id(code)
    with client.connect() as api:
        contents = api.course_contents(course_id)
        html_pages = client.html_links_in(contents)
        files = client.files_in(contents) + html_pages
        known = {r.get("moodle_id") for r in registry.read_all(code)}
        added, skipped = [], 0
        tmp = Path(tempfile.mkdtemp(prefix="udb-moodle-"))
        for item in files:
            if item["moodle_id"] in known:
                skipped += 1
                continue
            if dry_run:
                added.append(item["filename"])
                continue
            if item in html_pages:
                # Public static page: the Moodle token is not sent there.
                local = tmp / item["filename"]
                response = api.client.get(item["fileurl"])
                response.raise_for_status()
                local.write_bytes(response.content)
            else:
                local = api.download(item["fileurl"], tmp / item["filename"])
            number = (section_map or {}).get(item["section"].strip().lower())
            try:
                record = registry.register(code, local, kind="course", title=item["module"],
                                           class_number=number, moodle_id=item["moodle_id"])
                ingest.index_source(code, record["id"])
                added.append(f"{record['id']}  {item['filename']}")
            except (ValueError, RuntimeError) as exc:
                added.append(f"[not indexed] {item['filename']}: {exc}")
            client.pause()
    return {"course": course_id, "added": added, "already_there": skipped,
            "sections": sorted({f["section"] for f in files})}


def _find_assignment(api: client.MoodleApi, code: str, cmid: int) -> dict:
    item = next((a for a in api.assignments([_course_id(code)]) if a["cmid"] == cmid), None)
    if item is None:
        raise client.MoodleError(f"{code} has no assignment with id {cmid}")
    return item


def _save(api: client.MoodleApi, files: list[dict], dest: Path) -> list[dict]:
    out = []
    for f in files:
        local = api.download(f["fileurl"], dest / f["filename"])
        out.append({"file": local.name, "bytes": local.stat().st_size,
                    "expected": f.get("filesize")})
        client.pause()
    return out


def fetch_assignment(code: str, cmid: int, dest: Path) -> dict:
    """Save an assignment's description and attachments into `dest`."""
    with client.connect() as api:
        item = _find_assignment(api, code, cmid)
        dest.mkdir(parents=True, exist_ok=True)
        description = dest / "description.html"
        description.write_text(item.get("intro") or "", encoding="utf-8")
        return {"assignment": item["name"], "description": description.name,
                "attachments": _save(api, item.get("introattachments", []), dest)}


def fetch_submission(code: str, cmid: int, dest: Path) -> dict:
    """Save what you (or your team) submitted: files and online text."""
    with client.connect() as api:
        item = _find_assignment(api, code, cmid)
        last = api.submission_status(item["id"]).get("lastattempt") or {}
        sub = last.get("submission") or last.get("teamsubmission") or {}
        dest.mkdir(parents=True, exist_ok=True)
        files, texts = [], []
        for plugin in sub.get("plugins", []):
            for area in plugin.get("fileareas", []):
                files += _save(api, area.get("files", []), dest)
            for field in plugin.get("editorfields", []):
                if field.get("text"):
                    path = dest / f"{plugin.get('type', 'text')}.html"
                    path.write_text(field["text"], encoding="utf-8")
                    texts.append(path.name)
        return {"assignment": item["name"], "status": sub.get("status", "not-submitted"),
                "attachments": files, "texts": texts}


def list_courses() -> list[dict]:
    with client.connect() as api:
        return [{"id": c["id"], "shortname": c.get("shortname"), "fullname": c.get("fullname")}
                for c in api.my_courses()]


def assignments(code: str | None = None) -> list[dict]:
    """Every graded activity with its due date and submission status, soonest first."""
    by_course = _courses(code)
    with client.connect() as api:
        out = []
        for item in api.assignments(list(by_course)):
            info = api.submission_info(item["id"])
            out.append({
                "subject": by_course[item["course_id"]],
                "type": "assign",
                "name": item["name"],
                "opens": item.get("allowsubmissionsfromdate") or 0,
                "due": item.get("duedate") or 0,
                "cutoff": item.get("cutoffdate") or 0,
                "status": info["status"],
                "files": info["files"],
                "grade": info["grade"],
                "modified": item.get("timemodified") or 0,
                "instructions": client.plain(item.get("intro")),
                "url": f"{api.base}/mod/assign/view.php?id={item['cmid']}",
            })
            client.pause()
        # Quizzes, forums and the rest: the calendar only lists what is pending.
        for ev in api.action_events(since=int(time.time()) - 60 * 86400):
            course_id = (ev.get("course") or {}).get("id")
            if course_id not in by_course or ev.get("modulename") == "assign":
                continue
            out.append({"subject": by_course[course_id], "type": ev.get("modulename") or "event",
                        "name": ev["name"], "opens": 0, "due": ev.get("timesort") or 0,
                        "cutoff": 0, "status": "not-submitted", "files": [], "grade": None,
                        "modified": ev.get("timemodified") or 0, "instructions": "",
                        "url": ev.get("url") or ""})
        return sorted(out, key=lambda t: t["due"] or 10**12)


GROUP_RE = re.compile(r"grupo|equipo|conform|formaci")


def activity(codes: list[str], since: float) -> dict[str, dict]:
    """Course announcements and recent forum posts per subject."""
    zone = settings.get().tz
    by_course = {cid: c for cid, c in _courses(None).items() if c in codes}
    out = {c: {"announcements": [], "forum_posts": [], "group_threads": 0} for c in codes}
    with client.connect() as api:
        for forum in api.forums(list(by_course)):
            code = by_course.get(forum["course"])
            if not code or forum["type"] not in ("news", "general"):
                continue
            for d in api.discussions(forum["id"], 20):
                when = d.get("timemodified") or 0
                row = {"forum": forum["name"], "topic": d.get("name", ""),
                       "author": d.get("userfullname", ""),
                       "date": datetime.fromtimestamp(when, zone).date(), "timestamp": when,
                       "replies": d.get("numreplies", 0),
                       "text": client.plain(d.get("message"), 280)}
                if forum["type"] == "news":
                    out[code]["announcements"].append(row)
                elif when >= since:
                    if GROUP_RE.search(normalize(forum["name"] + " " + row["topic"])):
                        out[code]["group_threads"] += 1
                    else:
                        out[code]["forum_posts"].append(row)
            client.pause()
    return out
