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


def test_youtube_ids_survive_url_keys():
    from udb.integrations.recordings import catalog
    a = catalog.url_key("https://www.youtube.com/watch?v=8M1KGEQmV_w")
    b = catalog.url_key("https://www.youtube.com/embed/8M1KGEQmV_w?rel=0")
    c = catalog.url_key("https://www.youtube.com/watch?v=jt9V1h78oSQ")
    assert a == b != c


def test_ink_is_measured_inside_the_board_only():
    import numpy as np

    from udb.integrations.recordings import frames
    cam = np.random.default_rng(0).integers(0, 256, (180, 320)).astype(np.int16)
    assert frames._measure(cam) is None            # a camera picture, no board
    light = np.zeros((180, 320), np.int16)
    light[20:160, 40:280] = 255                   # white slide inside a dark call
    light[60:70, 60:200] = 0                      # one line of writing
    ink, _ = frames._measure(light)
    assert 0.03 < ink < 0.06
    dark = np.full((180, 320), 20, np.int16)      # black board, white chalk
    dark[60:70, 60:200] = 240
    ink, _ = frames._measure(dark)
    assert 0.02 < ink < 0.04


def test_branding_cards_are_not_boards():
    from udb.integrations.recordings import vision
    assert vision.is_branding("UNIVERSIDAD DON BOSCO\nUDB VIRTUAL\nEl Salvador")
    assert not vision.is_branding("UDB VIRTUAL\n\\( \\sum F_x = ma \\) T_1 cos θ + T_2 cos θ = m v^2/R")
    assert vision.clean("\\( T_1 \\sen\\theta \\)\nFigura: No hay figura.") == "\\( T_1 \\operatorname{sen}\\theta \\)"


def test_passage_is_whole_sentences_and_verbatim():
    from udb.core.text import contains, passage
    chunk = ("forma de los pares. La fuerza neta es la suma de todas las fuerzas. "
             "Si la fuerza neta es cero, el cuerpo no acelera. Por eso se dibuja el DCL.")
    p = passage(chunk, "cuerpo no acelera")
    assert p == "Si la fuerza neta es cero, el cuerpo no acelera."
    assert passage(chunk).startswith("La fuerza neta")
    assert contains(chunk, passage(chunk))
    board = "\\( \\sum F_x = ma \\)\nT_1 cos θ + T_2 cos θ = m v^2 / R\nT_1 = (mg + T_2 sen θ) / sen θ"
    assert "T_1 =" in passage(board, "T_1 = (mg")
