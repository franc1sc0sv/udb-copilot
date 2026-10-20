"""Study progress: concepts, review cards (SM-2), mistakes and agent sessions."""
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from ..core.paths import index_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS concepts (
  id TEXT PRIMARY KEY, subject TEXT, class_number INTEGER, name TEXT,
  note_path TEXT, syllabus_topic TEXT
);
CREATE TABLE IF NOT EXISTS cards (
  id INTEGER PRIMARY KEY, concept_id TEXT, bloom TEXT,
  question TEXT, answer TEXT, anchor TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY, card_id INTEGER, at TEXT, grade INTEGER, your_answer TEXT
);
CREATE TABLE IF NOT EXISTS schedule (
  card_id INTEGER PRIMARY KEY, due TEXT, interval_days REAL,
  ease REAL, reps INTEGER, lapses INTEGER
);
CREATE TABLE IF NOT EXISTS misconceptions (
  id INTEGER PRIMARY KEY, concept_id TEXT, at TEXT,
  wrong_claim TEXT, correct_anchor TEXT, resolved INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS method_errors (
  id INTEGER PRIMARY KEY, subject TEXT, method TEXT, at TEXT,
  wrong_step TEXT, correct_step_anchor TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  subject TEXT PRIMARY KEY, session_id TEXT, updated_at TEXT
);
"""

# Old Spanish column names, renamed in place the first time a ledger opens.
RENAMES = [("concepts", "clase", "class_number"), ("method_errors", "metodo", "method")]
BLOOM = ("remember", "understand", "apply", "analyze")
BLOOM_LEGACY = {"recordar": "remember", "comprender": "understand", "aplicar": "apply",
                "analizar": "analyze"}
MIN_EASE = 1.3


def db_path() -> Path:
    return index_dir() / "ledger.db"


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(db_path())
    con.row_factory = sqlite3.Row
    for table, old, new in RENAMES:
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        if old in cols and new not in cols:
            con.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
    for old, new in BLOOM_LEGACY.items():
        try:
            con.execute("UPDATE cards SET bloom=? WHERE bloom=?", (new, old))
        except sqlite3.OperationalError:
            break
    con.executescript(SCHEMA)
    return con


def _write(sql: str, args: tuple) -> int:
    con = connect()
    try:
        cur = con.execute(sql, args)
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def _rows(sql: str, args: list) -> list[dict]:
    con = connect()
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def add_concept(subject: str, name: str, note_path: str, class_number: int | None = None,
                topic: str | None = None) -> str:
    concept_id = f"{subject.upper()}:{name.strip().lower().replace(' ', '-')}"
    _write("INSERT OR REPLACE INTO concepts (id, subject, class_number, name, note_path,"
           " syllabus_topic) VALUES (?,?,?,?,?,?)",
           (concept_id, subject.upper(), class_number, name, note_path, topic))
    return concept_id


def add_card(concept_id: str, bloom: str, question: str, answer: str, anchor: str) -> int:
    bloom = BLOOM_LEGACY.get(bloom, bloom)
    if bloom not in BLOOM:
        raise ValueError(f"invalid bloom level: {bloom} (use one of {', '.join(BLOOM)})")
    con = connect()
    try:
        cur = con.execute(
            "INSERT INTO cards (concept_id, bloom, question, answer, anchor, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (concept_id, bloom, question, answer, anchor, datetime.now().isoformat()))
        card_id = cur.lastrowid
        con.execute("INSERT OR REPLACE INTO schedule (card_id, due, interval_days, ease, reps,"
                    " lapses) VALUES (?,?,?,?,?,?)",
                    (card_id, date.today().isoformat(), 0.0, 2.5, 0, 0))
        con.commit()
        return card_id
    finally:
        con.close()


def next_interval(interval: float, ease: float, reps: int, grade: int) -> tuple[float, float]:
    if grade < 3:
        return 1.0, max(MIN_EASE, ease - 0.20)
    ease = max(MIN_EASE, ease + (0.10 - (5 - grade) * (0.08 + (5 - grade) * 0.02)))
    if reps == 0:
        return 1.0, ease
    if reps == 1:
        return 6.0, ease
    return round(interval * ease, 2), ease


def record(card_id: int, grade: int, your_answer: str = "") -> dict:
    con = connect()
    try:
        row = con.execute("SELECT * FROM schedule WHERE card_id = ?", (card_id,)).fetchone()
        interval, ease, reps, lapses = ((row["interval_days"], row["ease"], row["reps"],
                                         row["lapses"]) if row else (0.0, 2.5, 0, 0))
        new_interval, new_ease = next_interval(interval, ease, reps, grade)
        reps = 0 if grade < 3 else reps + 1
        lapses = lapses + 1 if grade < 3 else lapses
        due = (date.today() + timedelta(days=new_interval)).isoformat()
        con.execute("INSERT INTO reviews (card_id, at, grade, your_answer) VALUES (?,?,?,?)",
                    (card_id, datetime.now().isoformat(), grade, your_answer))
        con.execute("INSERT OR REPLACE INTO schedule (card_id, due, interval_days, ease, reps,"
                    " lapses) VALUES (?,?,?,?,?,?)",
                    (card_id, due, new_interval, new_ease, reps, lapses))
        con.commit()
    finally:
        con.close()
    return {"card_id": card_id, "due": due, "interval_days": new_interval,
            "ease": round(new_ease, 2), "lapses": lapses}


def due(subject: str | None = None, limit: int = 20) -> list[dict]:
    sql = ("SELECT c.id, c.question, c.answer, c.anchor, c.bloom, c.concept_id,"
           " s.due, s.lapses, k.subject, k.name, k.class_number"
           " FROM cards c JOIN schedule s ON s.card_id = c.id"
           " JOIN concepts k ON k.id = c.concept_id WHERE s.due <= ?")
    args: list = [date.today().isoformat()]
    if subject:
        sql += " AND k.subject = ?"
        args.append(subject.upper())
    return _rows(sql + " ORDER BY s.lapses DESC, s.due ASC, RANDOM() LIMIT ?", args + [limit])


def weak(subject: str | None = None, limit: int = 10) -> list[dict]:
    sql = ("SELECT k.id, k.name, k.subject, k.class_number, k.note_path,"
           " COUNT(r.id) AS attempts,"
           " SUM(CASE WHEN r.grade < 3 THEN 1 ELSE 0 END) AS failures"
           " FROM concepts k JOIN cards c ON c.concept_id = k.id"
           " LEFT JOIN reviews r ON r.card_id = c.id")
    args: list = []
    if subject:
        sql += " WHERE k.subject = ?"
        args.append(subject.upper())
    sql += (" GROUP BY k.id HAVING attempts > 0"
            " ORDER BY (CAST(failures AS REAL) / attempts) DESC, failures DESC LIMIT ?")
    return _rows(sql, args + [limit])


def add_misconception(concept_id: str, wrong_claim: str, correct_anchor: str) -> int:
    return _write("INSERT INTO misconceptions (concept_id, at, wrong_claim, correct_anchor)"
                  " VALUES (?,?,?,?)",
                  (concept_id, datetime.now().isoformat(), wrong_claim, correct_anchor))


def add_method_error(subject: str, slug: str, wrong_step: str, anchor: str) -> int:
    return _write("INSERT INTO method_errors (subject, method, at, wrong_step,"
                  " correct_step_anchor) VALUES (?,?,?,?,?)",
                  (subject.upper(), slug, datetime.now().isoformat(), wrong_step, anchor))


def open_misconceptions(subject: str | None = None) -> list[dict]:
    sql = ("SELECT m.*, k.name, k.subject FROM misconceptions m"
           " JOIN concepts k ON k.id = m.concept_id WHERE m.resolved = 0")
    args: list = []
    if subject:
        sql += " AND k.subject = ?"
        args.append(subject.upper())
    return _rows(sql + " ORDER BY m.at DESC", args)


def save_session(subject: str, session_id: str) -> None:
    _write("INSERT OR REPLACE INTO sessions (subject, session_id, updated_at) VALUES (?,?,?)",
           (subject.upper(), session_id, datetime.now().isoformat()))


def last_session(subject: str) -> str | None:
    rows = _rows("SELECT session_id FROM sessions WHERE subject = ?", [subject.upper()])
    return rows[0]["session_id"] if rows else None


def stats(subject: str | None = None) -> dict:
    where = " WHERE k.subject = ?" if subject else ""
    args = [subject.upper()] if subject else []
    cards = _rows("SELECT COUNT(*) n FROM cards c JOIN concepts k ON k.id = c.concept_id"
                  + where, args)[0]["n"]
    reviews = _rows("SELECT COUNT(*) n FROM reviews r JOIN cards c ON c.id = r.card_id"
                    " JOIN concepts k ON k.id = c.concept_id" + where, args)[0]["n"]
    return {"cards": cards, "reviews": reviews, "due": len(due(subject, limit=1000))}
