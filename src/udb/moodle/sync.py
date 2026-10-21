"""Download course material from Moodle into the vault, and an assignment's files.

Reading what is in Moodle (deadlines, news, grades, forums) is `reader`."""
import tempfile
from pathlib import Path

from ..core.paths import get_subject
from ..vault import ingest, registry
from . import client


def _course_id(code: str) -> int:
    course_id = get_subject(code).get("moodle_course_id")
    if not course_id:
        raise client.MoodleError(f"{code} has no moodle_course_id in config/subjects.yaml")
    return int(course_id)


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
            number = ((section_map or {}).get(item["section"].strip().lower())
                      or registry.guess_class(item["module"], item["filename"]))
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
    data = api.call("mod_assign_get_assignments", **{"courseids[0]": _course_id(code)})
    item = next((a for c in data.get("courses", []) for a in c.get("assignments", [])
                 if a["cmid"] == cmid), None)
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
