from pathlib import Path

import pytest

from udb.core import anchors, notes, paths, schema, settings
from udb.core.text import contains, normalize


def test_home_from_env(home):
    assert settings.get().home == home
    assert paths.vault() == home / "vault"
    assert settings.get().tz.key == "America/El_Salvador"


def test_home_from_cwd(home, monkeypatch):
    monkeypatch.delenv("UDB_HOME")
    settings.reset()
    assert settings.find_home(home / "vault" / "DEMO") == home


def test_missing_home(tmp_path, monkeypatch):
    monkeypatch.delenv("UDB_HOME", raising=False)
    with pytest.raises(settings.HomeNotFound):
        settings.find_home(tmp_path)


def test_legacy_front_matter_is_read_in_english():
    front = schema.normalize_front({"asignatura": "IRD", "clase": 3, "estado": "en-conflicto",
                                    "citas": "estricta", "tipo": "matematica"})
    assert front == {"subject": "IRD", "class": 3, "status": "conflict",
                     "citations": "strict", "kind": "math"}
    assert schema.normalize_front({"tipo": "concepto"})["type"] == "concept"


def test_subjects_are_normalized(home):
    demo = paths.get_subject("demo")
    assert demo["kind"] == "engineering"
    assert demo["days"] == ["mon", "thu"]


def test_straight_quotes_fold_like_anchor_quotes():
    source = 'El profesor dijo: "la unidad de resistencia es el ohmio".'
    anchor_quote = "El profesor dijo: 'la unidad de resistencia es el ohmio'."
    assert contains(source, anchor_quote)
    assert normalize("Ángulo") == "angulo"


def test_anchor_parsing_rejects_uncheckable_locators():
    a = anchors.parse_definition("c1", 'SRC-X-0001 | line=3 | quote="algo"', 1)
    assert a.error and "locator" in a.error
    ok = anchors.parse_definition("c2", 'SRC-X-0001 | page=3 | quote="algo"', 1)
    assert ok.error is None and ok.source_id == "SRC-X-0001"


def test_protected_paths(home):
    assert paths.is_protected(home / "vault/DEMO/sources/SRC-DEMO-0001.txt")
    assert paths.is_protected("vault/DEMO/derived/text/x.jsonl", cwd=home)
    assert not paths.is_protected(home / "vault/DEMO/classes/01-2026-01-10/class.md")


def test_notes_parse_sections(home):
    note = notes.load(home / "vault/DEMO/classes/01-2026-01-10/class.md")
    assert note.front["subject"] == "DEMO"
    assert note.has_section("Ejemplo")
    assert not notes.is_stub(Path(home / "vault/DEMO/classes/01-2026-01-10/class.md"))


def test_hand_written_front_matter_still_parses():
    front = notes.front_matter("---\ntitle: Tarea 2: VLAN\nstatus: submitted\nmethod: -\n---\nbody")
    assert front["title"] == "Tarea 2: VLAN" and front["status"] == "submitted"
