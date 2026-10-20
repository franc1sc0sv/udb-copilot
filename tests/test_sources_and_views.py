import json

from udb import checks
from udb.agent import guards
from udb.checks import citations
from udb.integrations.mail import base
from udb.rendering import views
from udb.vault import index, ingest, registry, sources

HTML = """<html><body><nav>menu</nav>
<h1>Ley de Ohm</h1><p>Introducción breve al tema de la clase con suficiente texto para ser una sección.</p>
<h2>Cálculo de la corriente</h2><p>La corriente se obtiene dividiendo el voltaje entre la resistencia del circuito.</p>
<img src="https://example.edu/fig1.png" alt="Circuito serie">
<h2>Unidades</h2><p>La unidad de resistencia es el ohmio y la de corriente es el amperio en el sistema.</p>
<iframe src="https://www.youtube.com/embed/x" title="Video de la clase"></iframe>
</body></html>"""


def _add_html(home):
    src = home / "page.html"
    src.write_text(HTML, encoding="utf-8")
    rec = ingest.ingest_file("DEMO", src, title="Página de la clase", url="https://example.edu/c1.html")
    return rec["source"]["id"]


def test_html_splits_into_sections_with_figures_and_embeds(home):
    sid = _add_html(home)
    pages = index.load_pages("DEMO", sid)
    assert [p["section"] for p in pages] == ["Ley de Ohm", "Cálculo de la corriente", "Unidades"]
    assert "[Figura 1: Circuito serie]" in pages[1]["text"]
    assert "Contenido incrustado: Video de la clase" in pages[2]["text"]
    meta = ingest.load_meta("DEMO", sid)
    assert meta["images"][0]["status"] == "pending" and len(meta["embeds"]) == 1
    assert sources.health("DEMO", registry.get("DEMO", sid))["state"] == "images"


def test_fetched_figure_becomes_a_citable_page(home, monkeypatch):
    sid = _add_html(home)
    monkeypatch.setattr(ingest.ocr, "available", lambda: True)
    monkeypatch.setattr(ingest.ocr, "read", lambda data: "R1 10 ohm en serie con R2")
    result = ingest.fetch_images("DEMO", sid, fetch=lambda url: (b"\x89PNG fake", "png"))
    assert result["done"] == 1
    figure = index.load_pages("DEMO", sid)[-1]
    assert figure["kind"] == "figure" and "R1 10 ohm" in figure["text"]
    assert sources.health("DEMO", registry.get("DEMO", sid))["state"] == "ok"
    assert index.search("R1 ohm serie", subject="DEMO")


def test_moved_quote_is_a_warning_and_verify_fix_repairs_it(indexed):
    path = indexed / "vault/DEMO/classes/01-2026-01-10/class.md"
    path.write_text(path.read_text().replace(
        '[^c3]: SRC-DEMO-0001 | page=3', '[^c3]: SRC-DEMO-0001 | page=1'))
    found = citations.check_paths([path])
    moved = [f for f in found if f.code == "quote-moved"]
    assert moved and moved[0].level == "warning" and moved[0].fix["new"] == "page=3"
    assert checks.apply_fixes(found)
    assert "page=3" in path.read_text()
    assert not [f for f in citations.check_paths([path]) if f.code == "quote-moved"]


def test_prompt_hook_only_fires_on_classroom_questions(home, monkeypatch, capsys):
    calls = []

    def fake_build(hours=24, **_):
        calls.append(hours)
        return {"mode": "digest", "generated": "now", "date": "2026-03-01", "classes_today": [],
                "events_today": [], "due_soon": [], "countdown": [],
                "classroom": {"changed_assignments": [], "announcements": [], "forum_posts": []},
                "mail": [], "sources": []}

    monkeypatch.setattr("udb.planning.digest.build", fake_build)
    guards.prompt_context("explícame la ley de ohm")
    assert capsys.readouterr().out == "" and not calls
    guards.prompt_context("¿qué tareas tengo pendientes?")
    out = json.loads(capsys.readouterr().out)
    assert "Classroom state" in out["hookSpecificOutput"]["additionalContext"] and calls
    guards.prompt_context("¿y para mañana?")
    assert len(calls) == 1  # served from the 30-minute cache


def test_views_render(indexed):
    from udb.planning import status
    html = views.status(status.build("DEMO"))
    assert "sr-only" in html and "DEMO" in html and "var(--" in html
    d = {"mode": "digest", "date": "2026-03-01", "classes_today": [{"code": "DEMO", "name": "x"}],
         "events_today": [], "due_soon": [], "sources": [{"name": "mail:x", "ok": False}],
         "countdown": [{"subject": "DEMO", "label": "Quiz", "days": 2, "weight": 10,
                        "submitted": False}],
         "classroom": {"changed_assignments": [], "announcements": [], "forum_posts": []},
         "mail": []}
    html = views.digest(d)
    assert "Quiz" in html and "bg-danger" in html and "No pude leer" in html


def test_gmail_app_password_uses_imap():
    provider = base.provider_for({"id": "g", "provider": "gmail", "auth": "app-password",
                                  "address": "a@gmail.com"})
    assert type(provider).__name__ == "ImapProvider"
    assert provider.account["host"] == "imap.gmail.com"
