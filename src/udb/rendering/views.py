"""Small views rendered inline in the Claude chat (the visualize widget).

The engine builds the HTML, so the numbers are the real ones and the look is
the same every time; Claude only passes it to `show_widget`. The fragments use
Claude's CSS variables, so they follow light and dark mode. Long content
(lessons, exercise guides) stays as pages in the vault instead.
"""

from udb.domain.planning.agenda import fmt
from udb.rendering.jinja import env

STAGE_TONE = {"complete": "success", "no material": "neutral", "render lesson": "accent",
              "write explanation": "danger", "method in conflict": "danger",
              "fix verify errors": "danger", "solve assignment": "warning",
              "extract method": "warning"}
STAGE_ES = {"complete": "completa", "no material": "sin material",
            "write explanation": "falta explicación", "method in conflict": "método en conflicto",
            "extract method": "falta método", "fix verify errors": "errores de citas",
            "solve assignment": "falta la tarea", "render lesson": "falta la lección"}
STATE_ES = {"submitted": "entregada", "pending": "pendiente", "not-published": "aún no publicada",
            "no-record": "sin registro", "exam": "prueba", "draft": "borrador",
            "not-submitted": "sin entrega"}


def when(days: int) -> str:
    return "hoy" if days == 0 else "mañana" if days == 1 else f"en {days} días"


def tone_for_days(days: int, done: bool) -> str:
    if done:
        return "success"
    return "danger" if days <= 3 else "warning" if days <= 7 else "neutral"


def _render(name: str, **data) -> str:
    return env().get_template(f"views/{name}.html.j2").render(
        when=when, tone_for_days=tone_for_days, stage_tone=STAGE_TONE, stage_es=STAGE_ES,
        state_es=STATE_ES, fmt=fmt, **data).strip()


def digest(d: dict) -> str:
    return _render("digest", d=d)


def status(data: dict) -> str:
    return _render("status", subjects=data["subjects"])


def agenda(data: dict) -> str:
    return _render("agenda", subjects=data["subjects"], alerts=data["alerts"],
                   sources=data["sources"], today=data["today"])


def pending(data: dict) -> list[dict]:
    """What is still to do, from the learning routes (published in Moodle or not): open work
    by date first, then what is overdue and missing. Exams already taken are not pending."""
    today = data["today"]
    rows = []
    for s in data["subjects"]:
        for it in s["items"]:
            if it["state"] == "submitted" or not (it["end"] >= today or it.get("late")):
                continue
            rows.append({**it, "code": s["code"], "name": s["name"]})
    return sorted(rows, key=lambda r: (bool(r.get("late")), r["end"], r["code"]))


def tasks(data: dict) -> str:
    return _render("tasks", rows=pending(data), today=data["today"])


def build(kind: str, subject: str | None = None) -> str:
    """The view of `kind` (digest, status, agenda, tasks) with fresh data."""
    code = subject.upper() if subject else None
    if kind == "digest":
        from udb.domain.planning import digest as dg
        built = dg.build(hours=24)
        html = digest(built)
        dg.mark_seen(built)
        return html
    if kind == "status":
        from udb.domain.planning import status as st
        return status(st.build(code))
    if kind == "agenda":
        from udb.domain.planning import agenda as ag
        return agenda(ag.build(code))
    if kind == "tasks":
        from udb.domain.planning import agenda as ag
        return tasks(ag.build(code, online=False))
    raise ValueError("kind must be digest, status, agenda or tasks")
