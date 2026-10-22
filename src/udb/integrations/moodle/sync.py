"""Bring the course into the vault: files and pages (`sync_subject`) and what the
teacher wrote in Moodle (`sync_classroom`), plus an assignment's files on demand.

Reading what is in Moodle without keeping it (deadlines, news, grades) is `reader`.
"""
import tempfile
from pathlib import Path

from udb.config.paths import get_subject
from udb.domain.sources import ingest, registry
from udb.integrations.moodle import client


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
        known = {m for r in registry.read_all(code)
                 for m in [r.get("moodle_id"), *r.get("moodle_aliases", [])] if m}
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
                before = {r["id"] for r in registry.read_all(code)}
                record = registry.register(code, local, kind="course", title=item["module"],
                                           class_number=number, moodle_id=item["moodle_id"])
                if record["id"] in before:
                    # Same file published twice in the course: remember the second link.
                    registry.add_alias(code, record["id"], item["moodle_id"])
                    skipped += 1
                else:
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


# ------------------------------------------------------------------ the teacher's words

def _write(folder: Path, name: str, title: str, meta: list[str], body: list[str]) -> Path:
    path = folder / f"{name}.md"
    head = [f"# {title}", "", *[f"- {m}" for m in meta if m], ""]
    path.write_text("\n".join(head + [b for b in body if b.strip()]) + "\n", encoding="utf-8")
    return path


def _course_links(contents: list[dict]) -> list[tuple[str, str, str]]:
    """Every external link a `url` module holds, except the static class pages (those are files)."""
    out = []
    for sec in contents:
        for m in sec.get("modules", []):
            if m.get("modname") != "url":
                continue
            for item in m.get("contents", []) or []:
                url = item.get("fileurl") or ""
                if url and "/materiales_didacticos/" not in url:
                    out.append((sec.get("name", ""), m.get("name", ""), url))
    return out


CAPTURED_TYPES = {"resource", "folder", "url", "page", "assign", "label", "forum"}


def _stamp_file() -> Path:
    from udb.config.paths import index_dir
    return index_dir() / "last_sync.json"


def stamp(report: dict[str, list[str]]) -> None:
    """Remember when a full sync ran and what it left out, for the session hook."""
    import json
    import time
    _stamp_file().write_text(json.dumps({"at": time.time(), "gaps": report},
                                        ensure_ascii=False), encoding="utf-8")


def last_sync() -> dict:
    import json
    path = _stamp_file()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def audit(code: str) -> list[str]:
    """Everything in the Moodle course that did not reach the vault, so nothing is dropped
    silently: unsupported files, activity types udb does not read, assignments without a
    local task folder, and recordings not yet downloaded."""
    from udb.integrations.media import catalog
    from udb.integrations.moodle import reader
    cid = _course_id(code)
    known = {m for r in registry.read_all(code)
             for m in [r.get("moodle_id"), *r.get("moodle_aliases", [])] if m}
    gaps = []
    with client.connect() as api:
        contents = api.course_contents(cid)
        for item in client.files_in(contents) + client.html_links_in(contents):
            if item["moodle_id"] not in known:
                gaps.append(f"archivo sin indexar: {item['filename']} ({item['section']})")
        for sec in contents:
            for m in sec.get("modules", []):
                kind = m.get("modname")
                if not m.get("uservisible", True):
                    continue
                if kind not in CAPTURED_TYPES:
                    gaps.append(f"actividad no leída ({kind}): {m.get('name')} · cmid {m['id']}")
                elif kind == "label" and reader.text(m.get("description")) \
                        and f"label:{m['id']}" not in known:
                    gaps.append(f"texto del curso sin guardar: cmid {m['id']}")
                elif kind == "page" and f"page:{m['id']}" not in known:
                    gaps.append(f"página sin guardar: {m.get('name')} · cmid {m['id']}")
        for row in reader.deadlines(code):
            if row["status"] != "submitted":
                gaps.append(f"sin entregar en Moodle: {row['name']} · {row['url']}")
    from udb.domain.sources import health
    rows = health.report(code)
    for r in rows:
        if r["state"] in ("unsupported", "missing", "no-text", "needs-ocr"):
            gaps.append(f"fuente no legible ({r['state']}): {r['id']} {r.get('title', '')} → {r['fix']}")
    unread = [r for r in rows if r["state"] == "images"]
    if unread:
        gaps.append(f"{len(unread)} fuentes con figuras sin leer (udb sources fix {code})")
    pending = [g for g in catalog.load() if g["subject"] == code and g["status"] == "pending"]
    if pending:
        gaps.append(f"{len(pending)} grabaciones o videos pendientes (udb recording board {code})")
    return gaps


def sync_classroom(code: str) -> dict:
    """What the teacher wrote in Moodle, as citable sources: course pages, assignment
    instructions (and their attachments), forum posts by teachers and private messages
    from teachers. Edited items become new versions; classmates' posts are not kept."""
    from udb.integrations.moodle import reader
    cid = _course_id(code)
    tmp = Path(tempfile.mkdtemp(prefix="udb-classroom-"))
    report = {"new": [], "updated": [], "same": 0}

    def keep(path: Path, moodle_id: str, title: str, url: str, number: int | None) -> None:
        rec, state = registry.register_version(code, path, "moodle", moodle_id, title=title,
                                               url=url, class_number=number)
        if state == "same":
            report["same"] += 1
            return
        ingest.index_source(code, rec["id"])
        report[state].append(f"{rec['id']}  {title}")

    with client.connect() as api:
        base = api.base
        teachers = {t["name"] for t in reader.teachers(api, str(cid))}
        contents = api.course_contents(cid)
        sections = {m["id"]: sec.get("name", "") for sec in contents
                    for m in sec.get("modules", [])}

        def number(name: str, cmid: int | None) -> int | None:
            return (registry.guess_class(name, None)
                    or registry.guess_class(sections.get(cmid, ""), None))

        for page in api.call("mod_page_get_pages_by_courses",
                             **{"courseids[0]": cid}).get("pages", []):
            cmid = page["coursemodule"]
            path = _write(tmp, f"page-{cmid}", page["name"],
                          [f"Página del curso · {sections.get(cmid, '')}"],
                          [reader.text(page.get("intro")), reader.text(page.get("content"))])
            keep(path, f"page:{cmid}", page["name"], f"{base}/mod/page/view.php?id={cmid}",
                 number(page["name"], cmid))

        for sec in contents:
            for m in sec.get("modules", []):
                if m.get("modname") != "label" or not m.get("uservisible", True):
                    continue
                body = reader.text(m.get("description"))
                if not body:
                    continue
                title = f"{sec.get('name', '')}: {body.splitlines()[0][:60]}".strip(": ")
                path = _write(tmp, f"label-{m['id']}", title,
                              [f"Texto del curso · {sec.get('name', '')}"], [body])
                keep(path, f"label:{m['id']}", title, f"{base}/course/view.php?id={cid}",
                     number(title, m["id"]))

        links = _course_links(contents)
        if links:
            path = _write(tmp, f"links-{cid}", "Enlaces del curso", ["Todos los enlaces del curso"],
                          [f"- {name} · {sec}: {url}" for sec, name, url in links])
            keep(path, f"links:{cid}", "Enlaces del curso", f"{base}/course/view.php?id={cid}", None)

        data = api.call("mod_assign_get_assignments", **{"courseids[0]": cid})
        for a in [a for c in data.get("courses", []) for a in c.get("assignments", [])]:
            cmid = a["cmid"]
            intro = reader.text(a.get("intro"))
            if intro:
                path = _write(tmp, f"assign-{cmid}", a["name"],
                              [f"Instrucciones de la tarea · vence {reader.when(a.get('duedate'))}"],
                              [intro])
                keep(path, f"assign:{cmid}", a["name"],
                     f"{base}/mod/assign/view.php?id={cmid}", number(a["name"], cmid))
            for f in a.get("introattachments") or []:
                local = api.download(f["fileurl"], tmp / f["filename"])
                try:
                    keep(local, f"assignfile:{cmid}:{f['filename']}", f"{a['name']} · {f['filename']}",
                         f"{base}/mod/assign/view.php?id={cmid}", number(a["name"], cmid))
                except ValueError:
                    pass  # a file type the extractor cannot read stays out
                client.pause()

        forums = api.call("mod_forum_get_forums_by_courses", **{"courseids[0]": cid})
        for forum in forums:
            listing = api.call("mod_forum_get_forum_discussions", forumid=forum["id"],
                               perpage=50, sortorder=-1).get("discussions", [])
            for d in listing:
                posts = [p for p in reader.discussion(api, d["discussion"])
                         if p["author"] in teachers]
                if not posts:
                    continue
                body = [f"**{p['author']} · {p['created']}**\n\n{p['text']}" for p in posts]
                path = _write(tmp, f"forum-{d['discussion']}", d.get("name") or forum["name"],
                              [f"Foro «{forum['name']}»"], body)
                keep(path, f"forum:{d['discussion']}", d.get("name") or forum["name"],
                     f"{base}/mod/forum/discuss.php?d={d['discussion']}",
                     registry.guess_class(d.get("name"), None))

        for conv in reader.conversations(api, limit=50):
            if conv["with"] not in teachers:
                continue
            messages = [m for m in reader.conversation(api, conv["conversation_id"], 200)
                        if m["from"] in teachers]
            if not messages:
                continue
            body = [f"**{m['from']} · {m['when']}**\n\n{m['text']}" for m in messages]
            path = _write(tmp, f"message-{conv['conversation_id']}", f"Mensajes de {conv['with']}",
                          ["Mensajes privados del profesor"], body)
            keep(path, f"message:{conv['conversation_id']}", f"Mensajes de {conv['with']}",
                 f"{base}/message/index.php", None)
    return report
