import json
from datetime import date

from udb.planning import digest, status, tasks
from udb.vault import classes, index, methods, registry


def test_index_search_and_chunk(indexed):
    rows = index.search("resistencia ohmios", subject="DEMO")
    assert rows and rows[0]["source_id"] == "SRC-DEMO-0001"
    assert index.chunk(rows[0]["id"])["text"]


def test_superseded_sources_are_not_searched(indexed):
    assert {r["source_id"] for r in index.search("voltaje", limit=50)} == {"SRC-DEMO-0001"}


def test_registry_reads_legacy_class_key(home):
    assert registry.get("DEMO", "SRC-DEMO-0001")["class"] == 1
    assert [s["id"] for s in classes.sources_for("DEMO", 1)] == ["SRC-DEMO-0001"]


def test_method_reading(home):
    m = methods.read("DEMO", "ohm-current")
    assert m.status == "confirmed" and len(m.steps) == 3 and m.classes == [1]


def test_status_board(indexed):
    data = status.build("DEMO")
    row = data["subjects"][0]["classes"][0]
    assert row["material"] == 1
    assert row["explanation"] == "written"
    assert [m["slug"] for m in row["methods"]] == ["ohm-current"]
    assert row["exercises"] == ["ex-01.md"]
    assert row["stage"] == "render lesson"
    assert (indexed / "index/status.json").exists()
    assert "Ley de Ohm" in status.render(data).read_text()


def test_tasks_legacy_and_repos(home):
    found = {t["id"]: t for t in tasks.local_tasks("DEMO")}
    legacy = found["01-tarea-1"]
    assert legacy["status"] == "todo" and legacy["methods"] == ["ohm-current"]
    assert legacy["subject"] == "DEMO" and str(legacy["term"]) == "2026-1"
    project = tasks.projects("DEMO")[0]
    assert project["url"].endswith("demo-project.git") and project["cloned"] is False


def test_task_board_joins_moodle(home):
    rows = tasks.board([{"subject": "DEMO", "name": "Tarea 1", "due": 0, "status": "submitted",
                         "url": "https://moodle.example.edu/mod/assign/view.php?id=1"}], "DEMO")
    joined = next(r for r in rows if r["title"] == "Tarea 1")
    assert joined["local"] == "todo" and joined["moodle"] == "submitted"


def test_countdown_merges_route_and_moodle(home):
    rows = [{"subject": "DEMO", "name": "Tarea 1 · ley de Ohm", "due": 0, "status": "submitted",
             "url": "u1", "type": "assign", "modified": 0},
            {"subject": "DEMO", "name": "Quiz 2", "type": "quiz", "status": "not-submitted",
             "url": "u2", "modified": 0,
             "due": int(__import__("datetime").datetime(2026, 3, 5, 23, 0).timestamp())}]
    items = digest.countdown(rows, date(2026, 3, 1))
    labels = {i["label"]: i for i in items}
    assert labels["Tarea 1"]["submitted"] is True and labels["Tarea 1"]["days"] == 9
    assert labels["Tarea 1"]["route_due"] is None
    assert labels["Quiz 2"]["days"] == 4
    assert [c["code"] for c in digest.classes_today(date(2026, 3, 2))] == ["DEMO"]  # a Monday


def test_digest_text_mentions_due_soon(home):
    data = {"mode": "digest", "date": "2026-03-01", "classes_today": [], "events_today": [],
            "due_soon": [{"subject": "DEMO", "label": "Quiz 2", "days": 1, "due": "2026-03-02"}],
            "countdown": [], "classroom": {"changed_assignments": [], "announcements": [],
                                           "forum_posts": []}, "mail": [], "sources": []}
    text = digest.as_text(data)
    assert "Quiz 2" in text and "mañana" in text
    assert "Quiz 2" in digest.as_html(data)


def test_ledger_roundtrip(home):
    from udb.vault import ledger
    cid = ledger.add_concept("DEMO", "ley de ohm", "x.md", 1)
    card = ledger.add_card(cid, "recordar", "¿V?", "I·R", "[^c1]: SRC-DEMO-0001 | page=1 | quote=\"x\"")
    assert ledger.due("DEMO")[0]["id"] == card
    assert ledger.record(card, 5)["interval_days"] == 1.0
    assert json.dumps(ledger.stats("DEMO"))
