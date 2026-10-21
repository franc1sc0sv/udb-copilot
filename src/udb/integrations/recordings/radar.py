"""What a class recording said that the student must not miss.

No model: every transcript segment is scored by phrases (exams, deadlines,
date changes, grading, "this will be on the exam", announcements), spoken
dates and percentages. Relative dates ("el próximo jueves", "mañana") are
resolved against the day of the class. It cannot invent an exam nobody
mentioned and it does not understand irony, so every hit carries the literal
quote and its time, and is shown as "dicho en clase, por confirmar".

Works on any transcript: Whisper, YouTube captions or a Stream transcript.
"""
import re
from datetime import date, timedelta

from ...core.text import strip_accents
from ...vault import index

# category -> (weight, phrases). Phrases are matched without accents.
CATEGORIES: dict[str, tuple[int, tuple[str, ...]]] = {
    "exam": (3, ("examen", "parcial", "prueba", "quiz", "evaluaci", "defensa", "diferido")),
    "deadline": (3, ("entrega", "entregar", "vence", "fecha limite", "plazo", "a mas tardar",
                     "hasta el", "cierre", "cierra", "subir al aula", "suban")),
    "change": (4, ("reprogram", "posterg", "adelant", "se mueve", "se corre", "cambio de fecha",
                   "ya no va a ser", "se suspende", "no habra clase", "no hay clase",
                   "no vamos a tener clase", "prorroga")),
    "grading": (2, ("ponderaci", "porcentaje", "por ciento", "nota", "calificaci", "rubrica",
                    "puntos", "punto extra", "puntos extra", "vale el", "resultados",
                    "en proceso de revision", "ya tengo los resultados")),
    "tested": (4, ("va a venir en", "viene en el examen", "entra en el examen", "entra para el",
                   "no entra", "eso entra", "tomen nota", "es importante", "pongan atencion",
                   "lo van a necesitar", "les va a salir", "esto lo voy a preguntar")),
    "announce": (2, ("les recuerdo", "no se les olvide", "aviso", "anuncio", "recordatorio",
                     "les informo", "tengan en cuenta", "la proxima clase", "la proxima semana",
                     "la otra semana", "les voy a estar informando", "les estare informando",
                     "comentarles", "les comento", "esten pendientes", "esten atentos",
                     "en el aula", "voy a publicar", "voy a subir")),
    "task": (1, ("tarea", "guia", "foro", "laboratorio", "desafio", "proyecto", "fase", "etapa",
                 "investigacion", "caso practico")),
}
KEY_CATEGORIES = {"exam", "deadline", "change", "grading", "tested", "announce"}

MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")
WEEKDAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
DAY_MONTH_RE = re.compile(r"\b(\d{1,2})\s+de\s+(" + "|".join(MONTHS) + r"|setiembre)\b")
SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
WEEKDAY_RE = re.compile(r"\b(?:(proximo|siguiente|este|el)\s+)?(" + "|".join(WEEKDAYS) + r")\b")
RELATIVE = {"pasado manana": 2, "manana": 1}
NEXT_WEEK_RE = re.compile(r"\b(la proxima semana|la otra semana|la siguiente semana)\b")
PERCENT_RE = re.compile(r"\b\d{1,3}\s?(?:%|por\s?ciento\b)")


def _norm(text: str) -> str:
    return strip_accents(text.lower())


def resolve_dates(text: str, on: date | None) -> list[dict]:
    """Dates a sentence mentions, as ISO strings when the class date allows it."""
    low = _norm(text)
    out: list[dict] = []
    for d, m in DAY_MONTH_RE.findall(low):
        month = 9 if m == "setiembre" else MONTHS.index(m) + 1
        year = on.year if on else date.today().year
        try:
            when = date(year, month, int(d))
            if on and when < on - timedelta(days=60):
                when = date(year + 1, month, int(d))
            out.append({"said": f"{d} de {m}", "date": when.isoformat(), "approx": False})
        except ValueError:
            pass
    for d, m, y in SLASH_RE.findall(low):
        try:
            year = (int(y) + (2000 if len(y) == 2 else 0)) if y else (on or date.today()).year
            out.append({"said": f"{d}/{m}", "date": date(year, int(m), int(d)).isoformat(),
                        "approx": False})
        except ValueError:
            pass
    if on:
        for word, delta in RELATIVE.items():
            if re.search(rf"\b{word}\b", low):
                out.append({"said": word, "date": (on + timedelta(days=delta)).isoformat(),
                            "approx": False})
                low = low.replace(word, " ")
        for qualifier, day in WEEKDAY_RE.findall(low):
            target = WEEKDAYS.index(day)
            ahead = (target - on.weekday()) % 7
            if qualifier in ("proximo", "siguiente") or ahead == 0:
                ahead = ahead or 7
            out.append({"said": f"{qualifier} {day}".strip(),
                        "date": (on + timedelta(days=ahead)).isoformat(), "approx": False})
        if NEXT_WEEK_RE.search(low):
            start = on + timedelta(days=7 - on.weekday())
            out.append({"said": "la próxima semana", "date": start.isoformat(), "approx": True})
    return out


def score(text: str, on: date | None = None) -> tuple[int, dict]:
    """How much a sentence matters to the student, and why."""
    low = _norm(text)
    cats = {name: [p for p in phrases if p in low]
            for name, (_, phrases) in CATEGORIES.items()}
    cats = {k: v for k, v in cats.items() if v}
    dates = resolve_dates(text, on)
    percents = PERCENT_RE.findall(low)
    points = sum(CATEGORIES[k][0] * len(v) for k, v in cats.items())
    points += 3 * len(dates) + 3 * len(percents)
    return points, {"categories": sorted(cats), "phrases": cats, "dates": dates,
                    "percents": percents}


def scan_segments(segments: list[dict], source_id: str = "", on: date | None = None,
                  window: int = 1, minimum: int = 5) -> list[dict]:
    """Hits in time order; neighbouring hits are merged into one."""
    hits: list[dict] = []
    for i, seg in enumerate(segments):
        text = seg.get("text", "")
        points, why = score(text, on)
        if points < minimum or not KEY_CATEGORIES & set(why["categories"]):
            continue
        lo, hi = max(0, i - window), min(len(segments), i + window + 1)
        hit = {"source_id": source_id, "t_start": segments[lo]["start"],
               "t_end": segments[hi - 1].get("end", segments[hi - 1]["start"]),
               "points": points, "categories": why["categories"], "dates": why["dates"],
               "why": why, "quote": text.strip(), "speaker": seg.get("speaker"),
               "context": " ".join(s.get("text", "").strip() for s in segments[lo:hi]).strip()}
        if hits and hit["t_start"] <= hits[-1]["t_end"]:
            prev = hits[-1]
            prev["t_end"] = max(prev["t_end"], hit["t_end"])
            prev["points"] = max(prev["points"], points)
            prev["categories"] = sorted(set(prev["categories"]) | set(hit["categories"]))
            prev["dates"] += [d for d in hit["dates"] if d not in prev["dates"]]
            prev["quote"] += " " + hit["quote"]
            continue
        hits.append(hit)
    return hits


def scan(subject: str, source_id: str, window: int = 1, minimum: int = 5,
         on: date | None = None) -> list[dict]:
    """Hits for a registered recording, strongest first."""
    segments = index.load_segments(subject, source_id)
    if not segments:
        raise FileNotFoundError(f"no transcript for {source_id}. "
                                "Run: udb recording transcribe <id> (or import-stream)")
    hits = scan_segments(segments, source_id, on, window, minimum)
    return sorted(hits, key=lambda h: -h["points"])
