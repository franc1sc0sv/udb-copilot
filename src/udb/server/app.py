"""The `vault` MCP server: every tool Claude uses to read and check the vault.

Run with `udb mcp` (stdio). Tools are thin: they call the same functions the
CLI calls and return JSON text.
"""
import json
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer

from .. import checks
from ..core import anchors, findings, paths
from ..core.text import contains
from ..vault import classes, index, ingest, ledger, methods, registry

INSTRUCTIONS = """Study vault with mandatory citations.
Search with vault_search, then cite only through vault_quote (it returns the exact anchor).
Before solving any exercise call method_get; NOT_FOUND means stop, conflict means ask.
The virtual classroom (Moodle) is reached only through moodle_assignments, agenda,
status and digest, never through a browser."""

server = MCPServer(name="vault", instructions=INSTRUCTIONS)


def ok(payload: Any) -> str:
    return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False,
                                                               indent=2, default=str)


# ------------------------------------------------------------------ sources

@server.tool()
def vault_search(query: str, subject: str = "", class_number: int = 0, kind: str = "",
                 limit: int = 8) -> str:
    """Search the course material. Returns chunk_id, source and an excerpt.
    Always search before writing any claim."""
    rows = index.search(query, subject=subject or None, kind=kind or None,
                        class_number=class_number or None, limit=limit)
    if not rows:
        return "No results. The indexed material does not cover that."
    sections = {}
    for r in rows:
        key = (r["subject"], r["source_id"])
        if key not in sections:
            sections[key] = {p["page"]: p.get("section") for p in index.load_pages(*key)}
    return ok([{"chunk_id": r["id"], "source_id": r["source_id"], "title": r["title"],
                "kind": r["kind"], "class": r["class"], "page": r["page"],
                "section": sections[(r["subject"], r["source_id"])].get(r["page"]),
                "t_start": r["t_start"], "t_end": r["t_end"], "excerpt": r["text"][:400]}
               for r in rows])


@server.tool()
def vault_quote(chunk_id: int, key: str = "c1", substring: str = "") -> str:
    """The EXACT text of a chunk and its ready-made anchor. The only valid way to cite.
    Pass `substring` to quote part of the chunk; it must be in the chunk."""
    row = index.chunk(int(chunk_id))
    if not row:
        raise ValueError(f"chunk_id {chunk_id} does not exist")
    text = row["text"]
    wanted = substring.strip()
    if wanted and not contains(text, wanted):
        raise ValueError("that text is not in the chunk. Quote only what you see.")
    quote = wanted or text[:240]
    page = row["page"]
    pages = {p["page"]: p for p in index.load_pages(row["subject"], row["source_id"])}
    if page is not None and row["t_start"] is None:
        # A chunk can span two pages; cite the page where the quote really is.
        from ..checks.citations import locate
        found = locate(row["subject"], row["source_id"], quote)
        if found and page not in found:
            page = min(found, key=lambda p: abs(p - row["page"]))
    anchor = anchors.format_anchor(key=key, source_id=row["source_id"], quote=quote,
                                   page=page if row["t_start"] is None else None,
                                   t_start=row["t_start"], t_end=row["t_end"],
                                   url=row["url"], retrieved=row["retrieved_at"] if row["url"] else None)
    return ok({"exact_text": quote, "anchor": anchor, "source": row["source_id"],
               "title": row["title"], "page": page,
               "section": (pages.get(page) or {}).get("section"), "full_chunk": text})


@server.tool()
def vault_source(source_id: str) -> str:
    """Metadata of a source (never its content)."""
    rec = registry.lookup(source_id)
    if not rec:
        raise ValueError(f"{source_id} is not in the registry")
    return ok(rec)


@server.tool()
def vault_register(subject: str, path: str, kind: str = "course", class_number: int = 0,
                   title: str = "") -> str:
    """Register and index a local file in the vault. Returns the new SRC id."""
    result = ingest.ingest_file(subject, path, kind=kind, title=title or None,
                                class_number=class_number or None)
    return ok({"source_id": result["source"]["id"], "chunks": result["chunks"]})


@server.tool()
def source_status(subject: str = "", source_id: str = "", problems_only: bool = True) -> str:
    """How well each source was read: ok, needs-ocr, images (figures not read yet),
    no-text, unsupported, missing. Call this BEFORE saying a source cannot be read;
    every problem comes with the command that fixes it."""
    from ..vault import sources
    rows = sources.report(subject or None, source_id or None)
    shown = [r for r in rows if r["state"] not in ("ok", "transcript")] if problems_only else rows
    return ok({"summary": sources.summary(rows), "sources": shown})


@server.tool()
def source_figure(source_id: str, n: int) -> list:
    """One figure of an HTML source as an image, to SEE a diagram, table or formula that
    the text does not contain. The only valid way to open source images."""
    from ..vault import ingest
    code = registry.subject_of(source_id)
    meta = ingest.load_meta(code, source_id)
    img = next((i for i in meta.get("images", []) if int(i["n"]) == int(n)), None)
    if not img:
        raise ValueError(f"{source_id} has no figure {n}")
    if not img.get("file"):
        raise ValueError(f"figure {n} of {source_id} is not downloaded. Run: udb sources fix {source_id}")
    path = ingest.images_dir(code, source_id) / img["file"]
    fmt = path.suffix.lstrip(".").replace("jpg", "jpeg")
    return [Image(data=path.read_bytes(), format=fmt),
            ok({"source_id": source_id, "figure": n, "caption": img.get("caption", ""),
                "ocr_text": img.get("text", ""),
                "cite_as": f'[^fN]: {source_id} | page=<the figure page> | quote="<text from ocr_text>"'})]


@server.tool()
def subject_list() -> str:
    """Configured subjects with their kind, Moodle course and class days."""
    return ok(paths.load_subjects())


# ------------------------------------------------------------------ methods and checks

@server.tool()
def method_get(subject: str, slug: str) -> str:
    """The teacher's method steps. NOT_FOUND: do NOT solve; tell the user the method
    must be extracted first. conflict: stop and ask which one the teacher uses."""
    m = methods.read(subject, slug)
    if m is None:
        return ok({"status": "NOT_FOUND", "message": f"No method '{slug}' in {subject}. "
                   "Do not solve anything. Tell the user it must be extracted first."})
    if m.status == "conflict":
        return ok({"status": "conflict", "steps": m.steps, "message":
                   "The sources disagree. Ask the user which one the teacher follows."})
    return ok({"status": m.status, "slug": m.slug, "steps": m.steps,
               "total_steps": len(m.steps), "classes": m.classes})


@server.tool()
def method_list(subject: str) -> str:
    """Methods that already exist for a subject."""
    return ok([{"slug": m.slug, "status": m.status, "steps": len(m.steps), "classes": m.classes}
               for m in methods.list_all(subject)])


@server.tool()
def method_check(path: str) -> str:
    """Check that a solution (markdown or HTML) follows the teacher's method step by step."""
    from ..checks import exercises
    return findings.as_text(exercises.check_path(Path(path)))


@server.tool()
def verify_check(path: str = "", subject: str = "") -> str:
    """Check citations, plain language and method use for one file or a whole subject."""
    found = checks.check_file(Path(path)) if path else checks.check_subject(subject or None)
    return findings.as_text(found)


@server.tool()
def clarity_check(path: str) -> str:
    """Check that a note uses plain language and has every required section."""
    from ..checks import clarity
    return findings.as_text(clarity.check_paths([Path(path)]))


@server.tool()
def syllabus_coverage(subject: str) -> str:
    """Compare the official syllabus with the written notes. Returns what is missing."""
    from ..checks import coverage
    return ok(coverage.syllabus_report(subject))


# ------------------------------------------------------------------ classes and boards

@server.tool()
def status(subject: str = "") -> str:
    """State of every class (material, recording, explanation, method, exercises,
    assignment, lesson, citation errors) and the next step. Offline. Start here."""
    from ..planning import status as st
    return ok(st.build(subject or None))


@server.tool()
def view(kind: str, subject: str = "") -> str:
    """A ready-made inline view for the chat: kind = digest | status | agenda | tasks.
    Pass the returned HTML unchanged to the visualize show_widget tool (read its guide
    first), then add two or three sentences. Without show_widget, use the JSON tools."""
    from ..rendering import views
    return views.build(kind, subject or None)


@server.tool()
def class_sources(subject: str, class_number: int) -> str:
    """The sources that belong to one class."""
    return ok(classes.sources_for(subject, int(class_number)))


@server.tool()
def lesson_render(path: str) -> str:
    """Render the HTML lesson page of a class note."""
    from ..rendering import lesson
    return ok({"html": str(lesson.write_lesson(Path(path)))})


@server.tool()
def diagram_suggest(shape: str) -> str:
    """Pick the right diagram type from the catalog. Describe what you want to show."""
    from ..rendering import diagrams
    return ok(diagrams.suggest(shape))


# ------------------------------------------------------------------ classroom, mail, planning

@server.tool()
def moodle_assignments(subject: str = "") -> str:
    """Graded activities from Moodle with due date and submission status, soonest first.
    Empty subject = all subjects. The only way to read Moodle."""
    from ..integrations.moodle import sync
    return ok(sync.assignments(subject or None))


@server.tool()
def tasks_board(subject: str = "") -> str:
    """Moodle activities joined with the local TASK.md folders."""
    from ..integrations.moodle import sync
    from ..planning import tasks
    code = subject.upper() or None
    return ok(tasks.board(sync.assignments(code), code))


@server.tool()
def agenda(subject: str = "") -> str:
    """Assessment agenda: last week and upcoming, crossing the learning route, Moodle,
    TASK.md, mail, Calendar and recordings. Writes index/agenda.html."""
    from ..planning import agenda as ag
    data = ag.build(subject or None)
    payload = ag.as_json(data)
    payload["html"] = str(ag.render(data))
    return ok(payload)


@server.tool()
def digest(hours: int = 24, alerts: bool = False) -> str:
    """Morning summary (classes today, countdown to every evaluation, due in 72 h,
    classroom news, teacher mail) or, with alerts=true, only what is new in the window."""
    from ..planning import digest as dg
    return ok(dg.build(hours=hours, alerts=alerts))


@server.tool()
def mail_search(query: str = "", days: int = 7, account: str = "", limit: int = 25) -> str:
    """Search every configured mail account (Gmail, Outlook, IMAP). Read-only."""
    from ..integrations.mail import base as mail
    terms = [t for t in query.split(",") if t.strip()] if query else []
    found, sources = mail.search_all(mail.Query(since_days=days, terms=terms, limit=limit),
                                     [account] if account else None)
    return ok({"messages": [m.as_dict() for m in found], "accounts": sources})


@server.tool()
def projects(subject: str = "") -> str:
    """Project repos linked from TASK.md files, with their local git state."""
    from ..planning import tasks
    return ok(tasks.projects(subject or None))


# ------------------------------------------------------------------ recordings

@server.tool()
def recording_board(subject: str = "") -> str:
    """Each class recording: downloaded, transcribed, frames. Start here for recordings."""
    from ..integrations.recordings import catalog
    rows = [r for r in catalog.board() if not subject or r["subject"] == subject.upper()]
    return ok(rows or "Empty catalog. Run in a terminal: udb recording discover")


@server.tool()
def recording_radar(recording_id: str, minimum: int = 4) -> str:
    """What a recording said about exams, deadlines, dates and percentages. No model:
    it only finds and quotes, so it cannot invent an assessment."""
    from ..integrations.recordings import catalog, radar
    g = catalog.find(recording_id)
    if not g.get("source_id"):
        raise ValueError(f"{g['id']} is not downloaded. Run: udb recording download {g['id']}")
    hits = radar.scan(g["subject"], g["source_id"], minimum=minimum)
    return ok({"recording": g["title"], "subject": g["subject"], "source_id": g["source_id"],
               "hits": [{"t": anchors.hhmmss(h["t_start"]), "quote": h["quote"],
                         "context": h["context"], "dates": h["why"]["dates"],
                         "percents": h["why"]["percents"],
                         "anchor": anchors.format_anchor(g["source_id"], g["source_id"],
                                                         h["quote"][:90], t_start=h["t_start"],
                                                         t_end=h["t_end"])} for h in hits]})


@server.tool()
def recording_frames(recording_id: str) -> str:
    """Frame index of a recording: timestamp and OCR text of each screen. Pick one to look at."""
    from ..integrations.recordings import catalog, frames
    g = catalog.find(recording_id)
    rows = frames.frame_index(g["subject"], g.get("source_id") or "")
    return ok([{"n": f["n"], "t": anchors.hhmmss(f["t"]) if f.get("t") is not None else None,
                "text": (f.get("text") or "")[:300]} for f in rows]
              or f"No frames. Run: udb recording frames {g['id']}")


@server.tool()
def recording_frame(recording_id: str, n: int) -> list:
    """One frame as an image, to SEE what the teacher showed on screen. Frames live in
    derived/ and this is the only valid way to open them."""
    from ..integrations.recordings import catalog, frames
    g = catalog.find(recording_id)
    path = frames.frame_path(g["subject"], g["source_id"], int(n))
    info = next((f for f in frames.frame_index(g["subject"], g["source_id"])
                 if int(f["n"]) == int(n)), {})
    stamp = anchors.hhmmss(info["t"]) if info.get("t") is not None else "?"
    meta = {"source_id": g["source_id"], "n": n, "t": stamp, "ocr": info.get("text", ""),
            "anchor_base": f'[^{g["source_id"]}]: {g["source_id"]} | t={stamp}-{stamp} | quote="..."'}
    return [Image(data=path.read_bytes(), format="jpeg"),
            ok(meta)]


# ------------------------------------------------------------------ study ledger

@server.tool()
def ledger_add_card(subject: str, concept: str, question: str, answer: str, anchor: str,
                    note_path: str = "", bloom: str = "remember", class_number: int = 0) -> str:
    """Save a review card. Every card needs its citation anchor."""
    if not anchor:
        raise ValueError("a card without an anchor is not saved")
    concept_id = ledger.add_concept(subject, concept, note_path, class_number or None)
    return ok({"card_id": ledger.add_card(concept_id, bloom, question, answer, anchor),
               "concept_id": concept_id})


@server.tool()
def ledger_due(subject: str = "", limit: int = 20) -> str:
    """Cards due for review today."""
    return ok(ledger.due(subject or None, limit))


@server.tool()
def ledger_record(card_id: int, grade: int, your_answer: str = "") -> str:
    """Record a review result. grade goes from 0 to 5."""
    return ok(ledger.record(int(card_id), int(grade), your_answer))


@server.tool()
def ledger_weak(subject: str = "", limit: int = 10) -> str:
    """The concepts the student does worst, plus open misconceptions."""
    return ok({"concepts": ledger.weak(subject or None, limit),
               "misconceptions": ledger.open_misconceptions(subject or None)})


@server.tool()
def ledger_misconception(concept_id: str, wrong_claim: str, correct_anchor: str) -> str:
    """Save a wrong idea of the student and the citation that corrects it."""
    return ok({"id": ledger.add_misconception(concept_id, wrong_claim, correct_anchor)})


@server.tool()
def ledger_method_error(subject: str, method: str, wrong_step: str,
                        correct_step_anchor: str = "") -> str:
    """Save a method error: the student used a step the teacher did not teach."""
    return ok({"id": ledger.add_method_error(subject, method, wrong_step, correct_step_anchor)})


TOOL_NAMES = [
    "vault_search", "vault_quote", "vault_source", "vault_register", "source_status",
    "source_figure", "subject_list",
    "method_get", "method_list", "method_check", "verify_check", "clarity_check",
    "syllabus_coverage", "status", "view", "class_sources", "lesson_render", "diagram_suggest",
    "moodle_assignments", "tasks_board", "agenda", "digest", "mail_search", "projects",
    "recording_board", "recording_radar", "recording_frames", "recording_frame",
    "ledger_add_card", "ledger_due", "ledger_record", "ledger_weak", "ledger_misconception",
    "ledger_method_error",
]


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
