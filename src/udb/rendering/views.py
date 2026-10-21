"""Small views rendered inline in the Claude chat (the visualize widget).

The engine builds the HTML, so the numbers are the real ones and the look is
the same every time; Claude only passes it to `show_widget`. The fragments use
Claude's CSS variables, so they follow light and dark mode. Long content
(lessons, exercise guides) stays as pages in the vault instead.
"""
from datetime import date

from .jinja import env

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
        state_es=STATE_ES, **data).strip()


def digest(d: dict) -> str:
    return _render("digest", d=d)


def status(data: dict) -> str:
    return _render("status", subjects=data["subjects"])


def agenda(data: dict) -> str:
    return _render("agenda", subjects=data["subjects"], alerts=data["alerts"],
                   sources=data["sources"], today=data["today"])


def tasks(rows: list[dict]) -> str:
    today = date.today()
    return _render("tasks", rows=sorted(rows, key=lambda r: r["due"] or 10**12), today=today)


def build(kind: str, subject: str | None = None) -> str:
    """The view of `kind` (digest, status, agenda, tasks) with fresh data."""
    code = subject.upper() if subject else None
    if kind == "digest":
        from ..planning import digest as dg
        return digest(dg.build(hours=24))
    if kind == "status":
        from ..planning import status as st
        return status(st.build(code))
    if kind == "agenda":
        from ..planning import agenda as ag
        return agenda(ag.build(code))
    if kind == "tasks":
        from ..moodle import reader
        from ..planning import tasks as tb
        return tasks(tb.board(reader.deadlines(code), code))
    raise ValueError("kind must be digest, status, agenda or tasks")
