"""`udb digest`: the morning summary and the "something changed" alert.

The data is gathered here without any model, so nothing is invented. A
scheduled Claude routine can turn the JSON into a friendly email, or
`--send` mails the built-in HTML version directly.

Morning digest (default): today's classes, a countdown to every graded
activity, what is due in the next 72 hours, what changed in the classroom and
teacher mail since the last digest.

Alerts (`alerts=True`): only what is new in the window — a new or edited
assignment, an announcement, a teacher email. Empty means "send nothing".
"""
from datetime import date, datetime

from udb.config import settings
from udb.config.paths import load_subjects, load_yaml
from udb.domain.planning import agenda

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DUE_SOON_DAYS = 3
HORIZON_DAYS = 45


def _source(sources: list, name: str, fn, default):
    try:
        value = fn()
        sources.append({"name": name, "ok": True})
        return value
    except Exception as exc:  # noqa: BLE001 - one failing source must not kill the digest
        sources.append({"name": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
        return default


def classes_today(today: date) -> list[dict]:
    day = WEEKDAYS[today.weekday()]
    return [{"code": s["code"], "name": s["name"]} for s in load_subjects() if day in s["days"]]


def countdown(rows: list[dict], today: date) -> list[dict]:
    """Every upcoming graded activity, from the route plan and from Moodle, once each."""
    zone = settings.get().tz
    plan = load_yaml("agenda.yaml").get("subjects", {})
    overrides = agenda.load_overrides()
    used: set[str] = set()
    out = []
    for code, spec in plan.items():
        for raw in spec.get("items", []):
            item = dict(raw, subject=code, end=agenda._day(raw["end"]))
            row = agenda._match(item, rows, used, zone)
            if row:
                used.add(row["url"])
            submitted = (row and row["status"] == "submitted") or \
                overrides.get(raw["key"], {}).get("state") == "submitted"
            # The route says what is graded and its weight; Moodle says when it closes.
            due = datetime.fromtimestamp(row["due"], zone).date() if row and row["due"] \
                else item["end"]
            days = (due - today).days
            if days < 0 or days > HORIZON_DAYS:
                continue
            out.append({"subject": code, "label": raw["label"], "due": due.isoformat(),
                        "route_due": item["end"].isoformat() if due != item["end"] else None,
                        "days": days, "weight": raw.get("weight"),
                        "kind": agenda.KINDS.get(raw.get("kind"), raw.get("kind")),
                        "submitted": bool(submitted), "url": row["url"] if row else None})
    for row in rows:
        if row["url"] in used or not row["due"] or row["status"] == "submitted":
            continue
        due = datetime.fromtimestamp(row["due"], zone).date()
        days = (due - today).days
        if 0 <= days <= HORIZON_DAYS:
            out.append({"subject": row["subject"], "label": row["name"], "due": due.isoformat(),
                        "days": days, "weight": None, "kind": row["type"], "submitted": False,
                        "url": row["url"]})
    return sorted(out, key=lambda x: (x["days"], x["subject"]))


def changed_assignments(rows: list[dict], since: float) -> list[dict]:
    return [{"subject": r["subject"], "name": r["name"], "url": r["url"],
             "due": datetime.fromtimestamp(r["due"], settings.get().tz).date().isoformat()
             if r["due"] else None}
            for r in rows if r.get("modified", 0) >= since]


def build(hours: int = 24, alerts: bool = False, now: datetime | None = None) -> dict:
    zone = settings.get().tz
    now = now or datetime.now(zone)
    today = now.date()
    since = now.timestamp() - hours * 3600
    sources: list[dict] = []
    codes = [s["code"] for s in load_subjects()]

    from udb.integrations.mail import base as mail
    from udb.integrations.moodle import reader

    rows = _source(sources, "moodle", lambda: reader.deadlines(None), [])
    activity = _source(sources, "moodle-forums", lambda: reader.news(codes, since), {})
    announcements = [{"subject": c, **a} for c, v in activity.items()
                     for a in v["announcements"] if a["timestamp"] >= since]
    posts = [{"subject": c, **p} for c, v in activity.items() for p in v["forum_posts"]]

    days = max(1, int(hours // 24) + 1)
    found = _source(sources, "mail", lambda: mail.search_all(mail.Query(since_days=days, limit=40)),
                    ([], []))
    messages = [m.as_dict() for m in found[0] if m.date >= since]
    sources += [{"name": f"mail:{s['account']}", "ok": s["ok"], "detail": s["detail"]}
                for s in found[1]]
    labelled = [m for m in messages if m["labels"]] if mail.filters() else messages

    data = {
        "generated": now.isoformat(timespec="minutes"), "date": today.isoformat(),
        "weekday": WEEKDAYS[today.weekday()], "hours": hours, "mode": "alerts" if alerts else "digest",
        "classroom": {"changed_assignments": changed_assignments(rows, since),
                      "announcements": announcements, "forum_posts": posts},
        "mail": labelled, "sources": sources,
    }
    if alerts:
        data["empty"] = not (data["classroom"]["changed_assignments"] or announcements or labelled)
        return data

    data["said_in_class"] = _source(sources, "recordings", lambda: said_in_class(today), [])
    items = countdown(rows, today)
    data["classes_today"] = classes_today(today)
    data["countdown"] = items
    data["due_soon"] = [i for i in items if i["days"] <= DUE_SOON_DAYS and not i["submitted"]]
    data["events_today"] = _source(sources, "calendar", lambda: _events_today(today), [])
    return data


SAID_DAYS = 14


def said_in_class(today: date, days: int = SAID_DAYS, limit: int = 8) -> list[dict]:
    """Radar hits from classes of the last `days` days: dates still ahead, or no date but
    a change, an announcement or "this will be on the exam". Spoken, so "por confirmar"."""
    from udb.integrations.media import catalog, radar, stream
    out = []
    for g in catalog.load():
        day = stream.class_day(g)
        if not g.get("source_id") or not day or (today - day).days > days or day > today:
            continue
        try:
            hits = radar.scan(g["subject"], g["source_id"], on=day)
        except FileNotFoundError:
            continue
        for h in hits:
            ahead = [d for d in h["dates"] if d["date"] >= today.isoformat()]
            loud = {"change", "tested", "announce"} & set(h["categories"])
            if not ahead and not loud:
                continue
            out.append({"subject": g["subject"], "recording": g["id"], "class_date": day.isoformat(),
                        "t": int(h["t_start"]), "categories": h["categories"],
                        "dates": [d["date"] for d in ahead], "quote": h["quote"][:300],
                        "points": h["points"]})
    return sorted(out, key=lambda x: -x["points"])[:limit]


def _events_today(today: date) -> list[dict]:
    from udb.integrations.google import calendar

    start = datetime.combine(today, datetime.min.time(), settings.get().tz).timestamp()
    return calendar.events(start, start + 86400)


def _when(days: int) -> str:
    return "hoy" if days == 0 else "mañana" if days == 1 else f"en {days} días"


def as_text(d: dict) -> str:
    """Plain text (Spanish), used for the email body and the terminal."""
    lines = []
    if d["mode"] == "alerts":
        lines.append("Novedades en el aula")
    else:
        lines.append(f"Buenos días. Resumen del {d['date']}.")
        if d["classes_today"]:
            lines.append("\nClases de hoy: " + ", ".join(f"{c['code']} ({c['name']})"
                                                        for c in d["classes_today"]))
        if d.get("events_today"):
            lines.append("Calendario: " + "; ".join(e["title"] for e in d["events_today"]))
        if d["due_soon"]:
            lines.append("\nVence pronto:")
            lines += [f"  - {i['subject']} · {i['label']} · {_when(i['days'])} ({i['due']})"
                      for i in d["due_soon"]]
        if d["countdown"]:
            lines.append("\nCuenta regresiva:")
            for i in d["countdown"]:
                mark = " ✓ entregada" if i["submitted"] else ""
                weight = f" · {i['weight']}%" if i["weight"] else ""
                lines.append(f"  - {i['days']:>2} d · {i['subject']} · {i['label']}{weight}{mark}")
    if d.get("said_in_class"):
        lines.append("\nDicho en clase (por confirmar):")
        for x in d["said_in_class"]:
            when = f" → {', '.join(x['dates'])}" if x["dates"] else ""
            mm, ss = divmod(x["t"], 60)
            lines.append(f"  - {x['subject']} {x['class_date']} [{mm}:{ss:02d}]{when}: "
                         f"«{x['quote'][:160]}»")
    cr = d["classroom"]
    if cr["changed_assignments"]:
        lines.append("\nActividades nuevas o cambiadas en Moodle:")
        lines += [f"  - {a['subject']} · {a['name']} (vence {a['due'] or 'sin fecha'})"
                  for a in cr["changed_assignments"]]
    if cr["announcements"]:
        lines.append("\nAnuncios:")
        lines += [f"  - {a['subject']} · {a['topic']} — {a['author']}" for a in cr["announcements"]]
    if d["mail"]:
        lines.append("\nCorreos:")
        lines += [f"  - [{m['account']}] {m['sender']}: {m['subject']}" for m in d["mail"][:15]]
    failed = [s for s in d["sources"] if not s["ok"]]
    if failed:
        lines.append("\nNo pude leer: " + ", ".join(s["name"] for s in failed))
    return "\n".join(lines)


def as_html(d: dict) -> str:
    from udb.rendering.jinja import env

    return env().get_template("digest.html.j2").render(d=d, when=_when)


def send(d: dict, account_id: str, to: str) -> str:
    from udb.integrations.mail import base as mail

    provider = mail.provider_for(mail.get_account(account_id))
    if not hasattr(provider, "send"):
        raise mail.MailError(f"account {account_id} cannot send mail")
    subject = ("Novedades en el aula" if d["mode"] == "alerts"
               else f"Mañanita: tu día {d['date']}")
    return provider.send(to, subject, as_html(d), as_text(d))

