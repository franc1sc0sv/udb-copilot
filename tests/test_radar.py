from datetime import date

from udb.integrations.recordings import radar, stream

WED = date(2026, 9, 23)  # a Wednesday


def test_relative_dates_resolve_against_the_class_day():
    found = {d["said"]: d["date"] for d in radar.resolve_dates(
        "El examen es el próximo jueves y la guía vence mañana", WED)}
    assert found["proximo jueves"] == "2026-09-24"
    assert found["manana"] == "2026-09-24"


def test_spoken_and_slash_dates():
    found = [d["date"] for d in radar.resolve_dates("entreguen el 5 de octubre o el 6/10", WED)]
    assert found == ["2026-10-05", "2026-10-06"]


def test_next_week_is_approximate():
    (d,) = radar.resolve_dates("lo vemos la próxima semana", WED)
    assert d["approx"] and d["date"] == "2026-09-28"


def test_scan_keeps_announcements_and_drops_chatter():
    segs = [{"start": 0, "end": 5, "text": "Buenas noches a todos."},
            {"start": 5, "end": 10, "text": "Les recuerdo que el parcial se posterga al 2 de octubre."},
            {"start": 60, "end": 65, "text": "Ahora resolvamos el ejercicio tres."},
            {"start": 120, "end": 125, "text": "Ojo, esto va a venir en el examen."}]
    hits = radar.scan_segments(segs, "SRC-X", WED, window=0)
    assert [h["t_start"] for h in hits] == [5, 120]
    assert "change" in hits[0]["categories"] and hits[0]["dates"][0]["date"] == "2026-10-02"
    assert "tested" in hits[1]["categories"]


def test_stream_entries_become_segments_without_system_lines():
    entries = [{"start": 4, "speaker": "Orador 1", "text": "Orador 1 empezó la transcripción"},
               {"start": 4, "speaker": "Orador 1", "text": "Hola a todos."},
               {"start": 21, "speaker": "Orador 2", "text": "Sí se escucha."}]
    segs = stream.segments_from(entries, 60)
    assert [(s["start"], s["end"], s["speaker"]) for s in segs] == [
        (4.0, 21.0, "Orador 1"), (21.0, 60.0, "Orador 2")]
    assert stream.class_date("Reunión 1 - IRD941-20260923_203547-Meeting Recording") == "2026-09-23"
