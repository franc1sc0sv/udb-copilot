"""Assessment agenda: every graded activity, from every source, in one board.

Sources, in order of authority:

1. The learning route (an indexed PDF): what is graded, its weight and date.
   Activities live in `config/agenda.yaml`; each has an `evidence` text that
   must still appear in the indexed route, checked on every run.
2. Moodle: what is published and whether it was submitted.
3. Local `cycles/**/TASK.md` folders.
4. Mail (every account in `config/mail.yaml`) and Google Calendar, read-only.
5. Class recordings (radar, no model): what the teacher said about exams.

No model is used. When a source fails, the board says so instead of going quiet.
"""
import hashlib
import json
import re
import time
from datetime import date, datetime, timedelta

from ..core import settings
from ..core.paths import index_dir, load_subjects, load_yaml
from ..core.text import normalize
from ..vault import index

MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
          "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
          "noviembre": 11, "diciembre": 12}
DATE_RE = re.compile(r"(\d{1,2})\s+(?:de\s+)?(" + "|".join(MONTHS) + r")", re.I)
# Route dates that are not deliverables or tests.
NOT_ASSESSMENT = ("desarrollo de", "vacaciones", "sintesis", "inicio", "finalizacion",
                  "fin de ciclo", "final de ciclo", "bienvenida", "induccion", "semana de",
                  "unidad ", "hasta")
MAIL_TERMS = ["udb", "aula digital", "ruta de aprendizaje", "parcial", "prueba", "examen",
              "encuentro", "defensa", "tarea"]
KINDS = {"entrega": "assignment", "prueba": "exam", "foro": "forum", "proyecto": "project"}
WEEKDAYS_ES = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MONTHS_ES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def fmt(d: date) -> str:
    return f"{WEEKDAYS_ES[d.weekday()]} {d.day:02d} {MONTHS_ES[d.month - 1]}"


def _day(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def load_plan() -> dict:
    plan = load_yaml("agenda.yaml")
    if not plan:
        raise RuntimeError("config/agenda.yaml is missing or empty")
    return plan


def load_overrides() -> dict:
    raw = load_yaml("agenda_overrides.yaml").get("overrides") or {}
    return {k: {**v, "state": {"entregada": "submitted"}.get(v.get("state"), v.get("state"))}
            for k, v in raw.items()}


def find_evidence(chunks: list[dict], evidence: str) -> dict | None:
    needle = normalize(evidence)
    for chunk in chunks:
        if needle in normalize(chunk["text"]):
            return {"chunk_id": chunk["id"], "page": chunk["page"]}
    return None


def _route_state(source_id: str, chunks: list[dict]) -> dict:
    digest = hashlib.sha256("".join(c["text"] for c in chunks).encode()).hexdigest()[:16]
    path = index_dir() / "agenda_state.json"
    state = json.loads(path.read_text()) if path.exists() else {}
    previous = state.get(source_id)
    state[source_id] = digest
    path.write_text(json.dumps(state, indent=2))
    return {"hash": digest, "changed": bool(previous and previous != digest)}


def uncovered_dates(chunks: list[dict], covered: set[tuple[int, int]]) -> list[dict]:
    """Dates the route mentions that no activity in the plan explains."""
    found, seen = [], set()
    for chunk in chunks:
        text = re.sub(r"\s+", " ", chunk["text"])
        for m in DATE_RE.finditer(text):
            key = (int(m.group(1)), MONTHS[m.group(2).lower()])
            before = normalize(text[max(0, m.start() - 70):m.start()])
            if key in covered or any(w in before for w in NOT_ASSESSMENT):
                continue
            if "rubrica" in normalize(text[:60]) or (chunk["id"], key) in seen:
                continue
            seen.add((chunk["id"], key))
            found.append({"date": f"{key[0]} de {m.group(2).lower()}", "page": chunk["page"],
                          "chunk_id": chunk["id"],
                          "context": text[max(0, m.start() - 80):m.end() + 60]})
    return found


def parse_grade(text: str | None) -> float | None:
    """'95,00 / 100,00' -> 9.5 out of 10."""
    m = re.search(r"([\d.,]+)\s*/\s*([\d.,]+)", text or "")
    if not m:
        return None
    num, den = (float(g.replace(",", ".")) for g in m.groups())
    return round(num / den * 10, 2) if den else None


def grade_breakdown(items: list[dict], today: date, passing: float) -> dict:
    """What is graded, what awaits a grade, what is still ahead, and what you need."""
    total = sum(i["weight"] for i in items)
    earned = graded = waiting = future = 0.0
    for it in items:
        g = it.get("grade10")
        if g is not None:
            earned += g * it["weight"] / 100
            graded += it["weight"]
        elif it["end"] < today:
            waiting += it["weight"]
        else:
            future += it["weight"]
    rest = total - graded
    out = {"total": total, "earned": round(earned, 2), "graded": graded, "waiting": waiting,
           "future": future, "passing": passing, "needed": None, "status": "no-grades"}
    if rest > 0:
        need = (passing - earned) / (rest / 100)
        out["needed"] = round(need, 2)
        out["status"] = "passed" if need <= 0 else "impossible" if need > 10 else "in-play"
    return out


def _match(item: dict, rows: list[dict], used: set[str], zone) -> dict | None:
    """Match by name; among several, take the one whose date is closest to the route.

    Moodle repeats names for support activities ("Checkpoint 2 ... del
    Desafío 1"); the route date tells them apart.
    """
    patterns = [normalize(p) for p in item.get("moodle", [])]
    found = []
    for row in rows:
        if row["url"] in used or row["subject"] != item["subject"]:
            continue
        if any(p in normalize(row["name"]) for p in patterns):
            due = datetime.fromtimestamp(row["due"], zone).date() if row["due"] else None
            found.append((abs((due - item["end"]).days) if due else 10**6, row))
    return min(found, key=lambda f: f[0])[1] if found else None


def _calendar_hits(item: dict, events: list[dict], names: dict[str, str]) -> list[dict]:
    code = item["subject"].lower()
    words = [w for w in normalize(item["label"]).split() if len(w) > 4]
    hits = []
    for ev in events:
        if not ev["start"] or ev["start"][:10] != item["end"].isoformat():
            continue
        title = normalize(ev["title"])
        if code in title or normalize(names.get(item["subject"], "")) in title \
                or any(w in title for w in words):
            hits.append(ev)
    return hits


def _collect(sources: list, name: str, fn, optional: bool = False, detail=len):
    try:
        value = fn()
        sources.append({"name": name, "ok": True, "detail": detail(value)})
        return value
    except Exception as exc:  # noqa: BLE001 - a failing source is reported, not fatal
        sources.append({"name": name, "ok": False, "optional": optional,
                        "detail": f"{type(exc).__name__}: {exc}"})
        return None


def build(subject: str | None = None, online: bool = True, now: datetime | None = None) -> dict:
    zone = settings.get().tz
    now = now or datetime.now(zone)
    today = now.date()
    week_start = today - timedelta(days=7)
    plan = load_plan()
    names = {s["code"]: s["name"] for s in load_subjects()}
    code_filter = subject.upper() if subject else None
    codes = [code_filter] if code_filter else list(plan["subjects"])
    sources: list[dict] = []
    alerts: list[dict] = []

    from ..moodle import reader
    from . import tasks

    rows = _collect(sources, "Moodle (tareas y eventos)", lambda: reader.deadlines(code_filter),
                    detail=lambda v: f"{len(v)} actividades") or []
    local = {t["moodle_url"]: t for t in (_collect(
        sources, "TASK.md locales", lambda: tasks.local_tasks(code_filter),
        detail=lambda v: f"{len(v)} carpetas") or []) if t.get("moodle_url")}

    events, mails = [], []
    if online:
        from ..google import calendar
        from ..mail import base as mail
        events = _collect(sources, "Google Calendar", optional=True,
                          fn=lambda: calendar.events(time.time() - 14 * 86400,
                                                     time.time() + 75 * 86400),
                          detail=lambda v: f"{len(v)} eventos (-14 a +75 días)") or []
        found = _collect(sources, "Correo (últimos 75 días)", optional=True,
                         fn=lambda: mail.search_all(mail.Query(since_days=75, terms=MAIL_TERMS)),
                         detail=lambda v: f"{len(v[0])} correos relacionados")
        mails = [m.as_dict() for m in found[0]] if found else []
        sources += [{"name": f"Correo: {st['account']}", "ok": st["ok"], "optional": True,
                     "detail": st["detail"]} for st in (found[1] if found else []) if not st["ok"]]

    def radar_hits() -> dict:
        from ..media import catalog, radar
        out: dict[str, list] = {}
        for g in catalog.board():
            if g["subject"] in codes and g["transcribed"]:
                for h in radar.scan(g["subject"], g["source_id"])[:4]:
                    out.setdefault(g["subject"], []).append(
                        {"recording": g["title"], "t": int(h["t_start"]), "quote": h["quote"]})
        return out

    radar = _collect(sources, "Grabaciones (radar)", radar_hits,
                     detail=lambda v: f"{sum(len(x) for x in v.values())} menciones") or {}
    feed = _collect(sources, "Moodle: anuncios y foros",
                    lambda: reader.news(codes, time.time() - 21 * 86400),
                    detail=lambda v: f"{sum(len(x['announcements']) for x in v.values())} anuncios"
                    ) or {} if online else {}

    overrides = load_overrides()
    used: set[str] = set()
    blocks = []
    for code in codes:
        spec = plan["subjects"].get(code)
        if not spec:
            continue
        chunks = index.source_chunks(spec["source"])
        sources.append({"name": f"Ruta {code} ({spec['source']})", "ok": bool(chunks),
                        "detail": f"{len(chunks)} fragmentos" if chunks else "no está indexada"})
        if chunks and _route_state(spec["source"], chunks)["changed"]:
            alerts.append({"level": "bad", "subject": code,
                           "text": f"La ruta de {code} cambió desde la última vez: revisa agenda.yaml."})
        items, covered = [], set()
        for raw in spec["items"]:
            item = dict(raw, subject=code, kind=KINDS.get(raw.get("kind"), raw.get("kind")))
            item["end"] = _day(raw["end"])
            item["start"] = _day(raw["start"]) if raw.get("start") else None
            covered |= {(item["end"].day, item["end"].month)}
            if item["start"]:
                covered |= {(item["start"].day, item["start"].month)}
            item["proof"] = find_evidence(chunks, raw["evidence"])
            if not item["proof"]:
                alerts.append({"level": "bad", "subject": code, "text":
                               f"{item['label']}: la ruta ya no dice «{raw['evidence']}». Revisa la fecha."})
            row = _match(item, rows, used, zone)
            if row:
                used.add(row["url"])
            item["moodle"] = row
            if row and row["due"]:
                due = datetime.fromtimestamp(row["due"], zone).date()
                item["moodle_due"] = due
                if abs((due - item["end"]).days) > 1:
                    item["mismatch"] = True
                    alerts.append({"level": "warn", "subject": code, "text":
                                   f"{item['label']}: la ruta dice {fmt(item['end'])} y Moodle cierra {fmt(due)}."})
            if row and row["url"] in local:
                item["local_status"] = local[row["url"]]["status"]
            item["days"] = (item["end"] - today).days
            item["calendar"] = _calendar_hits(item, events, names) if events else []
            if not row:
                item["state"] = "exam" if item["kind"] == "exam" else (
                    "no-record" if item["end"] < today else "not-published")
            else:
                item["state"] = "submitted" if row["status"] == "submitted" else "pending"
                item["files"] = row.get("files") or []
                item["grade"] = row.get("grade")
                item["grade10"] = parse_grade(row.get("grade"))
                item["instructions"] = row.get("instructions") or ""
                if row.get("modified"):
                    item["published"] = datetime.fromtimestamp(row["modified"], zone).date()
            fix = overrides.get(item["key"])
            if fix and fix.get("state") == "submitted":
                item["state"], item["override"] = "submitted", fix
            item["bucket"] = ("before" if item["end"] < week_start
                              else "week" if item["end"] < today else "upcoming")
            if item["state"] in ("pending", "no-record") and item["end"] < today \
                    and item["kind"] != "exam":
                item["late"] = True
            if item["end"] >= today and events and not item["calendar"]:
                item["no_calendar"] = True
            items.append(item)

        notices: dict[str, dict] = {}
        for nt in spec.get("notices", spec.get("avisos", [])):
            hit = find_evidence(chunks, nt["evidence"])
            rec = notices.setdefault(nt["text"], {"level": nt["level"], "text": nt["text"],
                                                  "ok": True, "pages": set()})
            rec["ok"] = rec["ok"] and bool(hit)
            if hit:
                rec["pages"].add(hit["page"])
        notice_list = [dict(n, pages=sorted(n["pages"])) for n in notices.values()]
        alerts += [{"level": "warn", "subject": code,
                    "text": "Un aviso de la ruta ya no se encuentra en el PDF: " + n["text"]}
                   for n in notice_list if not n["ok"]]
        blocks.append({
            "code": code, "name": names.get(code, code), "items": items,
            "notices": notice_list,
            "feed": feed.get(code, {"announcements": [], "forum_posts": [], "group_threads": 0}),
            "breakdown": grade_breakdown(items, today, plan.get("passing_grade", 6.0)),
            "new": [i for i in items if i.get("published") and (today - i["published"]).days <= 14],
            "radar": radar.get(code, []), "gaps": uncovered_dates(chunks, covered),
            "route": spec["source"], "weight_total": sum(i["weight"] for i in items)})

    for block in blocks:
        block["extras"] = [
            {"name": r["name"], "type": r["type"], "status": r["status"], "url": r["url"],
             "due": datetime.fromtimestamp(r["due"], zone).date() if r["due"] else None}
            for r in rows if r["url"] not in used and r["subject"] == block["code"]]
        for it in block["items"]:
            if it.get("late"):
                alerts.append({"level": "bad", "subject": block["code"], "text":
                               f"{it['label']} venció el {fmt(it['end'])} ({it['weight']}%) y no consta entrega."})
            elif it["bucket"] == "upcoming" and it["days"] <= 3 and it["state"] != "submitted":
                when = "hoy" if it["days"] == 0 else f"en {it['days']} d"
                alerts.append({"level": "warn", "subject": block["code"], "text":
                               f"{it['label']} vence {when} ({fmt(it['end'])}, {it['weight']}%)."})

    alerts.sort(key=lambda a: {"bad": 0, "warn": 1}.get(a["level"], 2))
    return {"generated": now, "today": today, "week_start": week_start, "subjects": blocks,
            "sources": sources, "alerts": alerts, "mails": mails}


def render(data: dict):
    from ..rendering.jinja import env
    out = index_dir() / "agenda.html"
    out.write_text(env().get_template("agenda.html.j2").render(**data, fmt=fmt), encoding="utf-8")
    return out


def as_json(data: dict):
    def clean(v):
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items()}
        if isinstance(v, (list, tuple, set)):
            return [clean(x) for x in v]
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        return v
    return clean(data)


def write_json(data: dict):
    out = index_dir() / "agenda.json"
    out.write_text(json.dumps(as_json(data), ensure_ascii=False, indent=2), encoding="utf-8")
    return out
