"""Everything a student can see in Moodle, read only.

The `moodle` MCP server, the digest, the agenda and the task board read through
this module. `client.MoodleApi` refuses any web-service function that is not a
pure read (`*_get_*`, `*_search_*`): nothing submits, posts, marks as read or
logs a "view" event, so the teacher never sees activity the student did not do.
Downloading course material for the vault lives in `sync`.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..core import settings
from ..core.paths import load_subjects
from ..core.text import normalize
from . import client

WORKERS = 6
TEACHER_ROLES = {"editingteacher", "teacher"}
GROUP_RE = re.compile(r"grupo|equipo|conform|formaci")
Api = client.MoodleApi
connect = client.connect


# ------------------------------------------------------------------ helpers

BLOCKS = ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol",
          "blockquote", "pre")


def text(html: str | None) -> str:
    """Moodle HTML to readable text: one line per paragraph, list items with a dash."""
    if not html:
        return ""
    soup = BeautifulSoup(re.sub(r"\s*\r?\n\s*", " ", html), "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for li in soup.find_all("li"):
        li.insert_before("- ")
    for tag in soup.find_all(BLOCKS):
        tag.append("\n")
    out = re.sub(r"[ \t\xa0]+", " ", soup.get_text())
    out = re.sub(r" *\n *", "\n", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def when(ts: int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), settings.get().tz).strftime("%Y-%m-%d %H:%M")


def _ids(prefix: str, values: list[int]) -> dict:
    return {f"{prefix}[{i}]": v for i, v in enumerate(values)}


def _parallel(fn, args: list) -> list:
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(fn, args))


def _files(items: list[dict] | None) -> list[dict]:
    return [{"name": f.get("filename"), "url": f.get("fileurl") or f.get("url"),
             "size": f.get("filesize")} for f in items or []]


def subject_courses() -> dict[int, str]:
    return {int(s["moodle_course_id"]): s["code"] for s in load_subjects()
            if s.get("moodle_course_id")}


def course_id(api: Api, subject: str) -> int:
    """A subject code from subjects.yaml, a Moodle course id, or a course name fragment."""
    if not subject:
        raise client.MoodleError("say which subject (code like IRD, or the course id)")
    if subject.isdigit():
        return int(subject)
    for cid, code in subject_courses().items():
        if code.lower() == subject.lower():
            return cid
    wanted = subject.lower()
    for course in courses(api):
        if wanted in course["name"].lower() or wanted == (course["short"] or "").lower():
            return course["id"]
    raise client.MoodleError(f"no course matches {subject!r}; see moodle_courses")


def _course_ids(api: Api, subject: str) -> list[int]:
    if subject:
        return [course_id(api, subject)]
    return [c["id"] for c in courses(api)]


# ------------------------------------------------------------------ courses

def courses(api: Api) -> list[dict]:
    me = api.site_info()["userid"]
    codes = subject_courses()
    now = time.time()
    out = []
    for c in api.call("core_enrol_get_users_courses", userid=me):
        if c.get("enddate") and c["enddate"] < now - 120 * 86400 and c["id"] not in codes:
            continue
        out.append({"id": c["id"], "subject": codes.get(c["id"]), "name": c.get("fullname"),
                    "short": c.get("shortname"), "progress": c.get("progress"),
                    "last_access": when(c.get("lastaccess"))})
    return out


def my_courses() -> list[dict]:
    with connect() as api:
        return courses(api)


def outline(api: Api, cid: int, section: str = "") -> list[dict]:
    """Sections and activities of a course, with dates and completion state."""
    completion = {}
    try:
        me = api.site_info()["userid"]
        data = api.call("core_completion_get_activities_completion_status", courseid=cid,
                        userid=me)
        completion = {s["cmid"]: s["state"] for s in data.get("statuses", [])}
    except client.MoodleError:
        pass
    out = []
    for sec in api.course_contents(cid):
        if section and section.lower() not in (sec.get("name") or "").lower() \
                and section != str(sec.get("section")):
            continue
        mods = []
        for m in sec.get("modules", []):
            if not m.get("uservisible", True):
                continue
            entry = {"cmid": m["id"], "type": m.get("modname"), "name": m.get("name")}
            dates = {d["label"]: when(d["timestamp"]) for d in m.get("dates", []) or []}
            if dates:
                entry["dates"] = dates
            if m["id"] in completion:
                entry["done"] = completion[m["id"]] in (1, 2)
            files = [c for c in m.get("contents", []) or [] if c.get("type") == "file"]
            if files and m.get("modname") in ("resource", "folder"):
                entry["files"] = _files(files)
            if m.get("modname") == "label":
                entry["text"] = text(m.get("description"))[:600]
            elif m.get("modname") == "url" and m.get("contents"):
                entry["url"] = m["contents"][0].get("fileurl")
            mods.append(entry)
        summary = text(sec.get("summary"))
        if mods or summary:
            out.append({"section": sec.get("name"), "number": sec.get("section"),
                        "summary": summary[:800], "activities": mods})
    return out


def _module(api: Api, cmid: int) -> dict:
    return api.call("core_course_get_course_module", cmid=cmid)["cm"]


def activity(api: Api, cmid: int) -> dict:
    """The full content of one activity, whatever its type."""
    cm = _module(api, cmid)
    kind, cid, instance = cm["modname"], cm["course"], cm["instance"]
    base = {"cmid": cmid, "type": kind, "name": cm.get("name"), "course": cid}
    if kind == "assign":
        return {**base, **assignment(api, instance, cid)}
    if kind == "forum":
        return {**base, "discussions": discussions(api, instance)}
    if kind == "quiz":
        return {**base, **quiz(api, instance, cid)}
    if kind == "page":
        for p in api.call("mod_page_get_pages_by_courses", **_ids("courseids", [cid]))["pages"]:
            if p["coursemodule"] == cmid:
                return {**base, "intro": text(p.get("intro")), "content": text(p.get("content")),
                        "files": _files(p.get("contentfiles"))}
    if kind == "url":
        for u in api.call("mod_url_get_urls_by_courses", **_ids("courseids", [cid]))["urls"]:
            if u["coursemodule"] == cmid:
                return {**base, "intro": text(u.get("intro")), "url": u.get("externalurl")}
    if kind == "book":
        return {**base, "chapters": book(api, cid, cmid)}
    for sec in api.course_contents(cid):
        for m in sec.get("modules", []):
            if m["id"] == cmid:
                return {**base, "section": sec.get("name"),
                        "description": text(m.get("description")),
                        "files": _files([c for c in m.get("contents", []) or []
                                         if c.get("type") == "file"])}
    return base


def book(api: Api, cid: int, cmid: int) -> list[dict]:
    for sec in api.course_contents(cid):
        for m in sec.get("modules", []):
            if m["id"] != cmid:
                continue
            chapters = []
            for c in m.get("contents", []) or []:
                if c.get("filename") == "index.html" and c.get("fileurl"):
                    response = api.client.get(c["fileurl"], params={"token": api.token})
                    chapters.append({"chapter": c.get("filepath", "").strip("/"),
                                     "text": text(response.text)})
            return chapters
    return []


# ------------------------------------------------------------------ assignments

def assignment(api: Api, instance: int, cid: int) -> dict:
    data = api.call("mod_assign_get_assignments", **_ids("courseids", [cid]))
    item = next((a for c in data.get("courses", []) for a in c.get("assignments", [])
                 if a["id"] == instance), {})
    status = api.submission_status(instance)
    info = api.submission_info(instance)
    feedback = status.get("feedback") or {}
    comments = [text(f.get("text")) for p in feedback.get("plugins", [])
                for f in p.get("editorfields", []) if f.get("text")]
    feedback_files = [f for p in feedback.get("plugins", []) for fa in p.get("fileareas", [])
                      for f in _files(fa.get("files"))]
    return {"intro": text(item.get("intro")), "attachments": _files(item.get("introattachments")),
            "opens": when(item.get("allowsubmissionsfromdate")), "due": when(item.get("duedate")),
            "cutoff": when(item.get("cutoffdate")), "max_grade": item.get("grade"),
            "team": bool(item.get("teamsubmission")), "status": info["status"],
            "my_files": info["files"], "grade": info["grade"],
            "graded_on": when(feedback.get("gradeddate")), "feedback": comments,
            "feedback_files": feedback_files}


def assignments(api: Api, subject: str = "") -> list[dict]:
    cids = _course_ids(api, subject)
    data = api.call("mod_assign_get_assignments", **_ids("courseids", cids))
    codes = subject_courses()
    items = [(c["id"], a) for c in data.get("courses", []) for a in c.get("assignments", [])]
    infos = _parallel(lambda pair: api.submission_info(pair[1]["id"]), items)
    return [{"subject": codes.get(cid), "course": cid, "cmid": a["cmid"], "name": a["name"],
             "due": when(a.get("duedate")), "cutoff": when(a.get("cutoffdate")),
             "status": info["status"], "grade": info["grade"]}
            for (cid, a), info in zip(items, infos, strict=True)]


# ------------------------------------------------------------------ grades

def grades(api: Api, subject: str = "") -> list[dict]:
    me = api.site_info()["userid"]
    codes = subject_courses()
    totals = {g["courseid"]: g.get("grade") for g in
              api.call("gradereport_overview_get_course_grades", userid=me).get("grades", [])}

    def cell(row: dict, key: str) -> str | None:
        value = text((row.get(key) or {}).get("content"))
        return value if value and value != "-" else None

    def one(cid: int) -> dict:
        # The grades table is what the student sees in Moodle: range, percent and weight.
        data = api.call("gradereport_user_get_grades_table", courseid=cid, userid=me)
        rows = []
        for table in data.get("tables", [])[:1]:
            for row in table.get("tabledata", []):
                if not isinstance(row, dict) or "grade" not in row:
                    continue
                name = cell(row, "itemname")
                if not name or name.lower().startswith(("total del curso", "course total")):
                    continue
                # Each school hides different columns; keep only the ones it shows.
                fields = {"item": name, "grade": cell(row, "grade"),
                          "range": cell(row, "range"), "percent": cell(row, "percentage"),
                          "weight": cell(row, "weight"),
                          "counts": cell(row, "contributiontocoursetotal"),
                          "feedback": cell(row, "feedback")}
                rows.append({k: v for k, v in fields.items() if v is not None or k == "grade"})
        return {"subject": codes.get(cid), "course": cid, "total": totals.get(cid),
                "items": rows}

    return _parallel(one, _course_ids(api, subject))


# ------------------------------------------------------------------ quizzes

def quiz(api: Api, instance: int, cid: int) -> dict:
    data = api.call("mod_quiz_get_quizzes_by_courses", **_ids("courseids", [cid]))
    q = next((q for q in data.get("quizzes", []) if q["id"] == instance), {})
    attempts = api.call("mod_quiz_get_user_attempts", quizid=instance, status="all")
    best = api.call("mod_quiz_get_user_best_grade", quizid=instance)
    return {"intro": text(q.get("intro")), "opens": when(q.get("timeopen")),
            "closes": when(q.get("timeclose")),
            "time_limit_min": (q.get("timelimit") or 0) // 60 or None,
            "attempts_allowed": q.get("attempts") or "unlimited", "max_grade": q.get("grade"),
            "my_attempts": [{"state": a.get("state"), "started": when(a.get("timestart")),
                             "finished": when(a.get("timefinish")),
                             "score": a.get("sumgrades")}
                            for a in attempts.get("attempts", [])],
            "best_grade": best.get("grade") if best.get("hasgrade") else None}


def quizzes(api: Api, subject: str = "") -> list[dict]:
    cids = _course_ids(api, subject)
    data = api.call("mod_quiz_get_quizzes_by_courses", **_ids("courseids", cids))
    codes = subject_courses()
    items = data.get("quizzes", [])

    def best(q: dict):
        b = api.call("mod_quiz_get_user_best_grade", quizid=q["id"])
        return b.get("grade") if b.get("hasgrade") else None

    grades_ = _parallel(best, items)
    return [{"subject": codes.get(q["course"]), "cmid": q["coursemodule"], "name": q["name"],
             "opens": when(q.get("timeopen")), "closes": when(q.get("timeclose")),
             "time_limit_min": (q.get("timelimit") or 0) // 60 or None,
             "max_grade": q.get("grade"), "best_grade": g}
            for q, g in zip(items, grades_, strict=True)]


# ------------------------------------------------------------------ forums

def forums(api: Api, subject: str = "") -> list[dict]:
    codes = subject_courses()
    data = api.call("mod_forum_get_forums_by_courses", **_ids("courseids",
                                                              _course_ids(api, subject)))
    return [{"subject": codes.get(f["course"]), "forum_id": f["id"], "cmid": f.get("cmid"),
             "name": f.get("name"), "type": f.get("type"),
             "discussions": f.get("numdiscussions"), "due": when(f.get("duedate")),
             "intro": text(f.get("intro"))[:400]} for f in data]


def discussions(api: Api, forum_id: int, limit: int = 30) -> list[dict]:
    data = api.call("mod_forum_get_forum_discussions", forumid=forum_id, sortorder=-1,
                    perpage=limit)
    return [{"discussion_id": d.get("discussion"), "subject": d.get("subject") or d.get("name"),
             "author": d.get("userfullname"), "created": when(d.get("created")),
             "last_post": when(d.get("timemodified")), "replies": d.get("numreplies"),
             "pinned": d.get("pinned"), "preview": text(d.get("message"))[:300]}
            for d in data.get("discussions", [])]


def discussion(api: Api, discussion_id: int) -> list[dict]:
    data = api.call("mod_forum_get_discussion_posts", discussionid=discussion_id,
                    sortby="created", sortdirection="ASC")
    return [{"post_id": p["id"], "reply_to": p.get("parentid") or None,
             "author": (p.get("author") or {}).get("fullname"),
             "created": when(p.get("timecreated")), "subject": p.get("subject"),
             "text": text(p.get("message")), "files": _files(p.get("attachments"))}
            for p in data.get("posts", [])]


# ------------------------------------------------------------------ notifications, messages

def notifications(api: Api, limit: int = 30, unread_only: bool = False) -> list[dict]:
    me = api.site_info()["userid"]
    data = api.call("message_popup_get_popup_notifications", useridto=me, newestfirst=1,
                    limit=limit, offset=0)
    out = []
    for n in data.get("notifications", []):
        if unread_only and n.get("read"):
            continue
        out.append({"when": when(n.get("timecreated")), "read": bool(n.get("read")),
                    "subject": n.get("subject"), "from": n.get("component"),
                    "text": text(n.get("fullmessagehtml") or n.get("fullmessage")
                                 or n.get("smallmessage"))[:800],
                    "link": n.get("contexturl")})
    return out


def conversations(api: Api, limit: int = 20) -> list[dict]:
    me = api.site_info()["userid"]
    data = api.call("core_message_get_conversations", userid=me, limitfrom=0, limitnum=limit)
    out = []
    for c in data.get("conversations", []):
        members = [m.get("fullname") for m in c.get("members", []) if m.get("id") != me]
        last = (c.get("messages") or [{}])[0]
        out.append({"conversation_id": c["id"], "with": c.get("name") or ", ".join(members),
                    "unread": c.get("unreadcount") or 0, "last": when(last.get("timecreated")),
                    "preview": text(last.get("text"))[:200]})
    return out


def conversation(api: Api, conversation_id: int, limit: int = 50) -> list[dict]:
    me = api.site_info()["userid"]
    data = api.call("core_message_get_conversation_messages", currentuserid=me,
                    convid=conversation_id, limitfrom=0, limitnum=limit, newest=1)
    names = {m["id"]: m.get("fullname") for m in data.get("members", [])}
    return [{"when": when(m.get("timecreated")),
             "from": "yo" if m.get("useridfrom") == me else names.get(m.get("useridfrom")),
             "text": text(m.get("text"))} for m in reversed(data.get("messages", []))]


# ------------------------------------------------------------------ calendar, updates, people

def calendar(api: Api, days: int = 30, subject: str = "") -> list[dict]:
    now = int(time.time())
    params = {"options[timestart]": now, "options[timeend]": now + days * 86400,
              "options[userevents]": 1, "options[siteevents]": 1}
    params.update(_ids("events[courseids]", _course_ids(api, subject)))
    codes = subject_courses()
    data = api.call("core_calendar_get_calendar_events", **params)
    return sorted(({"when": when(e.get("timestart")), "subject": codes.get(e.get("courseid")),
                    "name": e.get("name"), "type": e.get("modulename") or e.get("eventtype"),
                    "description": text(e.get("description"))[:300]}
                   for e in data.get("events", [])), key=lambda e: e["when"] or "")


def updates(api: Api, hours: int = 72, subject: str = "") -> list[dict]:
    """What changed in each course since `hours` ago: new files, posts, grades, dates."""
    since = int(time.time()) - hours * 3600
    codes = subject_courses()

    def one(cid: int) -> list[dict]:
        data = api.call("core_course_get_updates_since", courseid=cid, since=since)
        names = {m["id"]: m.get("name") for s in api.course_contents(cid)
                 for m in s.get("modules", [])} if data.get("instances") else {}
        return [{"subject": codes.get(cid), "cmid": i["id"], "name": names.get(i["id"]),
                 "changed": sorted({u["name"] for u in i.get("updates", [])}),
                 "when": when(max((u.get("timeupdated") or 0 for u in i.get("updates", [])),
                                  default=0))}
                for i in data.get("instances", []) if i.get("contextlevel") == "module"]

    return [row for rows in _parallel(one, _course_ids(api, subject)) for row in rows]


def teachers(api: Api, subject: str) -> list[dict]:
    cid = course_id(api, subject)
    data = api.call("core_enrol_get_enrolled_users", courseid=cid,
                    **{"options[0][name]": "userfields",
                       "options[0][value]": "id,fullname,email,roles,lastaccess"})
    return [{"name": u.get("fullname"), "email": u.get("email"),
             "role": ", ".join(r["shortname"] for r in u.get("roles", [])),
             "last_access": when(u.get("lastaccess"))}
            for u in data if TEACHER_ROLES & {r["shortname"] for r in u.get("roles", [])}]


# ------------------------------------------------------------------ files

def download(api: Api, url: str, dest_dir: Path) -> Path:
    """Save a file linked from Moodle (pluginfile URLs only) and return its path."""
    host = urlparse(client.base_url()).netloc
    parsed = urlparse(url)
    if parsed.netloc != host or "pluginfile.php" not in parsed.path:
        raise client.MoodleError("only Moodle file links (pluginfile.php) can be downloaded")
    url = url.replace("/pluginfile.php", "/webservice/pluginfile.php", 1) \
        if "/webservice/pluginfile.php" not in url else url
    name = re.sub(r"[^\w.\-]+", "_", Path(parsed.path).name) or "file"
    return api.download(url.split("?")[0], dest_dir / name)


# ------------------------------------------------------------------ feeds for planning

def deadlines(code: str | None = None) -> list[dict]:
    """Every graded activity with its due date and submission status, soonest first
    (digest, agenda, task board). Epoch seconds, not formatted dates."""
    codes = subject_courses()
    by_course = {cid: c for cid, c in codes.items() if not code or c == code.upper()}
    if not by_course:
        raise client.MoodleError("no subject has moodle_course_id in config/subjects.yaml")
    with connect() as api:
        data = api.call("mod_assign_get_assignments", **_ids("courseids", list(by_course)))
        items = [{**a, "course_id": c["id"]} for c in data.get("courses", [])
                 for a in c.get("assignments", [])]
        infos = _parallel(api.submission_info, [i["id"] for i in items])
        out = [{"subject": by_course[i["course_id"]], "type": "assign", "name": i["name"],
                "opens": i.get("allowsubmissionsfromdate") or 0, "due": i.get("duedate") or 0,
                "cutoff": i.get("cutoffdate") or 0, "status": info["status"],
                "files": info["files"], "grade": info["grade"],
                "modified": i.get("timemodified") or 0,
                "instructions": text(i.get("intro"))[:400],
                "url": f"{api.base}/mod/assign/view.php?id={i['cmid']}"}
               for i, info in zip(items, infos, strict=True)]
        # Quizzes, forums and the rest: the calendar only lists what is pending.
        events = api.call("core_calendar_get_action_events_by_timesort",
                          timesortfrom=int(time.time()) - 60 * 86400, limitnum=50)
        for ev in events.get("events", []):
            cid = (ev.get("course") or {}).get("id")
            if cid not in by_course or ev.get("modulename") == "assign":
                continue
            out.append({"subject": by_course[cid], "type": ev.get("modulename") or "event",
                        "name": ev["name"], "opens": 0, "due": ev.get("timesort") or 0,
                        "cutoff": 0, "status": "not-submitted", "files": [], "grade": None,
                        "modified": ev.get("timemodified") or 0, "instructions": "",
                        "url": ev.get("url") or ""})
    return sorted(out, key=lambda t: t["due"] or 10**12)


def news(codes: list[str], since: float) -> dict[str, dict]:
    """Course announcements and recent forum posts per subject (digest, agenda)."""
    zone = settings.get().tz
    by_course = {cid: c for cid, c in subject_courses().items() if c in codes}
    out = {c: {"announcements": [], "forum_posts": [], "group_threads": 0} for c in codes}
    with connect() as api:
        forums_ = [f for f in api.call("mod_forum_get_forums_by_courses",
                                       **_ids("courseids", list(by_course)))
                   if by_course.get(f["course"]) and f["type"] in ("news", "general")]
        threads = _parallel(lambda fid: api.call("mod_forum_get_forum_discussions", forumid=fid,
                                                 perpage=20, sortorder=-1).get("discussions", []),
                            [f["id"] for f in forums_])
        for forum, discussions_ in zip(forums_, threads, strict=True):
            code = by_course[forum["course"]]
            for d in discussions_:
                when = d.get("timemodified") or 0
                row = {"forum": forum["name"], "topic": d.get("name", ""),
                       "author": d.get("userfullname", ""),
                       "date": datetime.fromtimestamp(when, zone).date(), "timestamp": when,
                       "replies": d.get("numreplies", 0), "text": text(d.get("message"))[:280]}
                if forum["type"] == "news":
                    out[code]["announcements"].append(row)
                elif when >= since:
                    if GROUP_RE.search(normalize(forum["name"] + " " + row["topic"])):
                        out[code]["group_threads"] += 1
                    else:
                        out[code]["forum_posts"].append(row)
    return out
