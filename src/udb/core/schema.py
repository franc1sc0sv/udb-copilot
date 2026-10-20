"""Canonical (English) keys and values for everything the engine parses.

Files written before v0.1 used Spanish keys (`asignatura`, `clase`,
`estado: en-conflicto`). They are read through these aliases, so old notes
keep working; `udb migrate` rewrites them to the canonical form.
"""
from __future__ import annotations

FRONT_KEYS = {
    "asignatura": "subject",
    "clase": "class",
    "clases": "classes",
    "fecha": "date",
    "titulo": "title",
    "estado": "status",
    "metodo": "method",
    "metodos_usados": "methods",
    "metodos": "methods",
    "citas": "citations",
    "claridad": "clarity",
    "fuente_base": "source",
    "fuentes": "sources",
    "tarea": "task",
    "estado_metodo": "method_status",
    "ejercicios_resueltos": "solved",
    "unidad": "unit",
    "conceptos": "concepts",
}

SUBJECT_KINDS = {
    "ingenieria": "engineering",
    "matematica": "math",
    "fisica": "physics",
    "programacion": "programming",
    "humanistica": "humanities",
    "general": "general",
}
KINDS = tuple(dict.fromkeys(SUBJECT_KINDS.values()))

DOC_TYPES = {"clase": "class", "concepto": "concept", "metodo": "method",
             "ejercicio": "exercise", "tarea": "assignment"}

VALUES = {
    "status": {"confirmado": "confirmed", "en-conflicto": "conflict",
               "en_conflicto": "conflict", "provisional": "provisional"},
    "citations": {"libre": "free", "estricta": "strict", "normal": "normal"},
    "clarity": {"libre": "free"},
}

METHOD_STATES = ("confirmed", "provisional", "conflict")
CITATION_MODES = ("free", "normal", "strict")

DAYS = {"lunes": "mon", "martes": "tue", "miercoles": "wed", "miércoles": "wed",
        "jueves": "thu", "viernes": "fri", "sabado": "sat", "sábado": "sat",
        "domingo": "sun"}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def normalize_front(front: dict) -> dict:
    """Front matter with canonical keys and values."""
    out: dict = {}
    for key, value in (front or {}).items():
        key = FRONT_KEYS.get(key, key)
        if key == "tipo":
            text = str(value).lower()
            if text in SUBJECT_KINDS:
                out.setdefault("kind", SUBJECT_KINDS[text])
            else:
                out.setdefault("type", DOC_TYPES.get(text, text))
            continue
        if key in VALUES and isinstance(value, str):
            value = VALUES[key].get(value.lower(), value.lower())
        if key == "kind" and isinstance(value, str):
            value = SUBJECT_KINDS.get(value.lower(), value.lower())
        out.setdefault(key, value)
    if "slug" in out and "method" not in out and out.get("type") == "method":
        out["method"] = out["slug"]
    return out


def normalize_subject(raw: dict) -> dict:
    s = dict(raw)
    if "tipo" in s:
        s.setdefault("kind", s.pop("tipo"))
    s["kind"] = SUBJECT_KINDS.get(str(s.get("kind") or "general").lower(),
                                  str(s.get("kind") or "general").lower())
    if "dias" in s:
        s.setdefault("days", s.pop("dias"))
    s["days"] = [DAYS.get(str(d).lower(), str(d).lower()[:3]) for d in s.get("days") or []]
    s["code"] = str(s["code"]).upper()
    return s


def normalize_record(rec: dict) -> dict:
    """Registry record (`registry.jsonl`) with canonical keys."""
    out = dict(rec)
    if "clase" in out:
        out.setdefault("class", out.pop("clase"))
    return out
