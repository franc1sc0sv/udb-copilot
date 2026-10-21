"""Full-text index over the derived text of every source (SQLite FTS5)."""
import json
import sqlite3
from pathlib import Path

from ..core.chunking import chunk_pages, chunk_segments
from ..core.paths import derived_dir, index_dir, subject_codes
from . import registry

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, subject TEXT, kind TEXT, title TEXT,
  path TEXT, url TEXT, class INTEGER, retrieved_at TEXT, superseded_by TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY, source_id TEXT, subject TEXT, ord INTEGER,
  page INTEGER, t_start REAL, t_end REAL,
  char_start INTEGER, char_end INTEGER, text TEXT, frame INTEGER
);

CREATE INDEX IF NOT EXISTS chunks_source ON chunks(source_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text, content='chunks', content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
"""
VERSION = 3  # bump when SCHEMA changes; an old index is rebuilt from scratch


def db_path() -> Path:
    return index_dir() / "vault.db"


def connect() -> sqlite3.Connection:
    path = db_path()
    con = sqlite3.connect(path)
    if con.execute("PRAGMA user_version").fetchone()[0] != VERSION:
        con.close()
        path.unlink(missing_ok=True)
        con = sqlite3.connect(path)
        con.executescript(SCHEMA)
        con.execute(f"PRAGMA user_version = {VERSION}")
    con.row_factory = sqlite3.Row
    return con


def is_empty() -> bool:
    if not db_path().exists():
        return True
    con = connect()
    try:
        return con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
    finally:
        con.close()


def upsert_source(con: sqlite3.Connection, rec: dict) -> None:
    con.execute(
        "INSERT OR REPLACE INTO sources"
        " (id, subject, kind, title, path, url, class, retrieved_at, superseded_by)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (rec["id"], rec["subject"], rec["kind"], rec["title"], rec["path"],
         rec.get("url"), rec.get("class"), rec.get("retrieved_at"), rec.get("superseded_by")))


def clear_source(con: sqlite3.Connection, source_id: str) -> None:
    con.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))


def add_chunks(con: sqlite3.Connection, source_id: str, subject: str, chunks: list[dict]) -> int:
    rows = [(source_id, subject, i, c.get("page"), c.get("t_start"), c.get("t_end"),
             c.get("char_start"), c.get("char_end"), c["text"], c.get("frame"))
            for i, c in enumerate(chunks)]
    con.executemany(
        "INSERT INTO chunks (source_id, subject, ord, page, t_start, t_end, char_start,"
        " char_end, text, frame) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def fts_query(text: str) -> str:
    terms = [t for t in "".join(c if c.isalnum() or c.isspace() else " " for c in text).split()
             if len(t) > 1]
    return " OR ".join(f'"{t}"' for t in terms) if terms else '""'


def search(query: str, subject: str | None = None, kind: str | None = None,
           class_number: int | None = None, limit: int = 8) -> list[dict]:
    sql = ("SELECT c.id, c.source_id, c.subject, c.page, c.t_start, c.t_end, c.frame,"
           " c.char_start, c.char_end, c.text, s.title, s.kind, s.class,"
           " bm25(chunks_fts) AS score"
           " FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid"
           " JOIN sources s ON s.id = c.source_id"
           " WHERE chunks_fts MATCH ? AND s.superseded_by IS NULL")
    args: list = [fts_query(query)]
    if subject:
        sql += " AND c.subject = ?"
        args.append(subject.upper())
    if kind:
        sql += " AND s.kind = ?"
        args.append(kind)
    if class_number is not None:
        sql += " AND s.class = ?"
        args.append(class_number)
    sql += " ORDER BY score LIMIT ?"
    args.append(limit)
    con = connect()
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def chunk(chunk_id: int) -> dict | None:
    con = connect()
    try:
        row = con.execute("SELECT c.*, s.title, s.kind, s.url, s.retrieved_at FROM chunks c"
                          " JOIN sources s ON s.id = c.source_id WHERE c.id = ?",
                          (chunk_id,)).fetchone()
    finally:
        con.close()
    return dict(row) if row else None


def source_chunks(source_id: str) -> list[dict]:
    con = connect()
    try:
        rows = con.execute("SELECT id, page, text FROM chunks WHERE source_id=? ORDER BY ord",
                           (source_id,)).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def pages_file(subject: str, source_id: str) -> Path:
    return derived_dir(subject) / "text" / f"{source_id}.pages.jsonl"


def transcript_file(subject: str, source_id: str) -> Path:
    return derived_dir(subject) / "transcripts" / f"{source_id}.json"


def load_pages(subject: str, source_id: str) -> list[dict]:
    path = pages_file(subject, source_id)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def load_segments(subject: str, source_id: str) -> list[dict]:
    path = transcript_file(subject, source_id)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("segments", [])


def frame_chunks(code: str, source_id: str) -> list[dict]:
    """What was read on each board still of a recording, one chunk per still, citable
    with `t=` and `frame=`. Intro cards and half-written stills are left out."""
    from ..media.frames import frame_index
    out = []
    for f in frame_index(code, source_id):
        text = (f.get("text") or "").strip()
        if not text or f.get("kind") in ("growth", "branding") or f.get("t") is None:
            continue
        out.append({"text": text, "t_start": float(f["t"]), "t_end": float(f["t"]),
                    "frame": int(f["n"])})
    return out


BOILERPLATE_SHARE = 0.6  # a line on this share of a subject's HTML pages is the site template
BOILERPLATE_MIN = 4


def boilerplate(code: str) -> set[str]:
    """Lines repeated on most HTML pages of a subject (navigation help, menus, footers):
    the course site's template, not content. They stay in the extracted text, so quotes
    still verify, but are left out of the search index."""
    from collections import Counter

    from ..core.text import normalize
    pages_by_source = [load_pages(code, r["id"]) for r in registry.read_all(code)
                       if str(r.get("path", "")).lower().endswith((".html", ".htm"))]
    if len(pages_by_source) < BOILERPLATE_MIN:
        return set()
    seen: Counter = Counter()
    for pages in pages_by_source:
        seen.update({normalize(line) for p in pages for line in (p.get("text") or "").split("\n")
                     if line.strip()})
    floor = max(BOILERPLATE_MIN, BOILERPLATE_SHARE * len(pages_by_source))
    return {line for line, n in seen.items() if n >= floor}


def _strip_boilerplate(pages: list[dict], noise: set[str]) -> list[dict]:
    if not noise:
        return pages
    from ..core.text import normalize
    return [{**p, "text": "\n".join(line for line in (p.get("text") or "").split("\n")
                                    if normalize(line) not in noise)} for p in pages]


def chunks_for(code: str, source_id: str, noise: set[str] | None = None) -> list[dict]:
    segments = load_segments(code, source_id)
    if segments:
        return chunk_segments(segments) + frame_chunks(code, source_id)
    return chunk_pages(_strip_boilerplate(load_pages(code, source_id), noise or set()))


def reindex_subject(code: str) -> int:
    con = connect()
    total = 0
    try:
        noise = boilerplate(code)
        for rec in registry.read_all(code):
            upsert_source(con, rec)
            clear_source(con, rec["id"])
            total += add_chunks(con, rec["id"], code.upper(), chunks_for(code, rec["id"], noise))
        con.commit()
    finally:
        con.close()
    return total


def reindex_all() -> dict[str, int]:
    return {code: reindex_subject(code) for code in subject_codes()}
