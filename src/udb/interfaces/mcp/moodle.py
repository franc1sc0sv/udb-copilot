"""The `moodle` MCP server: the whole virtual classroom, read only.

Run with `udb moodle mcp` (stdio). Every tool goes through
`integrations.moodle.reader`, which refuses any web-service call that writes.
Nothing is submitted, posted or marked as read.
"""
import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from udb.config import paths
from udb.integrations.moodle import reader

INSTRUCTIONS = """The student's Moodle (virtual classroom), read only.
Start with `updates` or `notifications` to see what is new, `course` to browse a subject,
`activity` to read anything by its cmid. Subjects are codes from config/subjects.yaml
(IRD, AVM, ...) or Moodle course ids. Nothing here can submit or post: tell the student
to do that in Moodle. Dates are local time (udb.yaml timezone)."""

server = MCPServer(name="moodle", instructions=INSTRUCTIONS)


def ok(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, default=str)


def run(fn, *args, **kwargs) -> str:
    with reader.connect() as api:
        return ok(fn(api, *args, **kwargs))


@server.tool()
def courses() -> str:
    """Courses the student is enrolled in, with the subject code udb uses for each."""
    return run(reader.courses)


@server.tool()
def course(subject: str, section: str = "") -> str:
    """Sections and activities of a course: cmid, type, name, dates, done or not, files.
    `section` filters by section name or number."""
    with reader.connect() as api:
        return ok(reader.outline(api, reader.course_id(api, subject), section))


@server.tool()
def activity(cmid: int) -> str:
    """Full content of one activity by cmid: assignment (instructions, dates, my status,
    grade, teacher feedback), forum, quiz, page, book, url, resource or folder."""
    return run(reader.activity, int(cmid))


@server.tool()
def grades(subject: str = "") -> str:
    """Grades of every course (or one): each graded item, grade and teacher feedback,
    plus the course total."""
    return run(reader.grades, subject)


@server.tool()
def assignments(subject: str = "") -> str:
    """Every assignment with due date, my submission status and grade."""
    return run(reader.assignments, subject)


@server.tool()
def quizzes(subject: str = "") -> str:
    """Quizzes and exams: open and close times, time limit, my best grade.
    Use `activity` with the cmid for my attempts."""
    return run(reader.quizzes, subject)


@server.tool()
def forums(subject: str = "") -> str:
    """Forums of every course (or one), with how many discussions each has."""
    return run(reader.forums, subject)


@server.tool()
def discussions(forum_id: int, limit: int = 30) -> str:
    """Discussions of a forum, newest first, with a preview of the first post."""
    return run(reader.discussions, int(forum_id), limit)


@server.tool()
def discussion(discussion_id: int) -> str:
    """Every post of a discussion in order: author, date, full text, attachments."""
    return run(reader.discussion, int(discussion_id))


@server.tool()
def notifications(limit: int = 30, unread_only: bool = False) -> str:
    """Moodle notifications (grades published, submissions, forum posts, reminders)."""
    return run(reader.notifications, limit, unread_only)


@server.tool()
def conversations(limit: int = 20) -> str:
    """Private messages: one row per conversation with the last message."""
    return run(reader.conversations, limit)


@server.tool()
def conversation(conversation_id: int, limit: int = 50) -> str:
    """Messages of one conversation, oldest first."""
    return run(reader.conversation, int(conversation_id), limit)


@server.tool()
def calendar(days: int = 30, subject: str = "") -> str:
    """Moodle calendar events in the next `days`: deadlines, live sessions, quizzes."""
    return run(reader.calendar, days, subject)


@server.tool()
def updates(hours: int = 72, subject: str = "") -> str:
    """What changed in the last `hours`: new or edited activities, files, posts, grades."""
    return run(reader.updates, hours, subject)


@server.tool()
def teachers(subject: str) -> str:
    """Teachers of a course with their email."""
    return run(reader.teachers, subject)


@server.tool()
def download(url: str, subject: str = "") -> str:
    """Save a Moodle file (attachment, resource, feedback file) under index/moodle-files/
    and return its path. Course material for citing goes through `udb sync` instead."""
    dest = paths.index_dir() / "moodle-files" / (subject.upper() or "misc")
    with reader.connect() as api:
        saved = reader.download(api, url, dest)
    return ok({"path": paths.relative(saved), "bytes": saved.stat().st_size})


def main() -> None:
    from udb.config import secrets
    try:
        secrets.restore()
    except Exception:  # noqa: BLE001
        pass
    server.run()


if __name__ == "__main__":
    main()
