"""Find everything a class recording said about exams, deadlines and grades.

No model: it scores transcript segments by keywords, dates and percentages
and quotes them. It cannot invent an exam nobody mentioned; it also does not
understand irony, so a human reads the hits.
"""
import re

from ...core.text import strip_accents
from ...vault import index

ASSESSMENT_WORDS = (
    "examen", "parcial", "prueba", "evaluaci", "quiz", "defensa", "entrega", "entregar",
    "tarea", "guia", "guía", "desafio", "desafío", "proyecto", "fase", "etapa", "laboratorio",
    "caso practico", "caso práctico", "ponderaci", "nota", "calificaci", "rubrica", "rúbrica",
)
DATE_WORDS = (
    "fecha", "vence", "limite", "límite", "plazo", "prorroga", "prórroga", "cierre", "cierra",
    "hasta el", "para el", "antes del", "reprogram", "posterg", "adelant", "se mueve",
    "se corre", "cambio de",
)
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "setiembre", "octubre", "noviembre", "diciembre")
SPOKEN_DATE_RE = re.compile(r"\b\d{1,2}\s+de\s+(?:" + "|".join(MONTHS) + r")\b"
                            r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", re.I)
# A \b after % never matches (both are non-word characters); only "por ciento" needs it.
PERCENT_RE = re.compile(r"\b\d{1,3}\s?(?:%|por\s?ciento\b)", re.I)


def score(text: str) -> tuple[int, dict]:
    """How much a sentence sounds like an assessment, and why."""
    low = strip_accents(text.lower())
    assessment = [w for w in ASSESSMENT_WORDS if strip_accents(w) in low]
    dates_words = [w for w in DATE_WORDS if strip_accents(w) in low]
    dates = SPOKEN_DATE_RE.findall(text)
    percents = PERCENT_RE.findall(text)
    points = 2 * len(assessment) + 2 * len(dates_words) + 3 * len(dates) + 3 * len(percents)
    return points, {"assessment": assessment, "date_words": dates_words,
                    "dates": dates, "percents": percents}


def scan(subject: str, source_id: str, window: int = 1, minimum: int = 4) -> list[dict]:
    segments = index.load_segments(subject, source_id)
    if not segments:
        raise FileNotFoundError(f"no transcript for {source_id}. "
                                "Run: udb recording transcribe <id>")
    hits = []
    for i, seg in enumerate(segments):
        text = seg.get("text", "")
        points, why = score(text)
        if not why["assessment"] or points < minimum:
            continue
        lo, hi = max(0, i - window), min(len(segments), i + window + 1)
        hits.append({"source_id": source_id, "t_start": segments[lo]["start"],
                     "t_end": segments[hi - 1]["end"], "points": points, "why": why,
                     "quote": text.strip(),
                     "context": " ".join(s["text"].strip() for s in segments[lo:hi]).strip()})
    return sorted(hits, key=lambda h: -h["points"])
