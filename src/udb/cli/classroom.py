"""The virtual classroom (Moodle), homework folders, agenda and the daily digest."""
import getpass
import time
from datetime import datetime
from pathlib import Path

import typer
from rich.table import Table

from ..core import settings
from .common import MARK, console, die, guarded, print_json


def register(app: typer.Typer) -> None:
    moodle_app = typer.Typer(help="Moodle login and courses.")
    assignment_app = typer.Typer(help="Download an assignment or your submission.")
    task_app = typer.Typer(help="Homework folders (cycles/<term>/<SUBJECT>/tasks/).")
    app.add_typer(moodle_app, name="moodle")
    app.add_typer(assignment_app, name="assignment")
    app.add_typer(task_app, name="task")

    @moodle_app.command("login")
    def moodle_login(user: str = typer.Option(None, help="Moodle username")):
        """Exchange your username and password for a token. Only the token is stored."""
        from ..moodle import client
        user = user or input("Moodle user: ").strip()
        password = getpass.getpass("Moodle password (not stored): ")
        token = guarded(client.fetch_token, user, password)
        path = guarded(client.store_token, token)
        console.print(f"[green]Token stored in {path} (mode 600).[/green]")
        console.print("For cloud sessions, put that token in the MOODLE_TOKEN variable.")

    @moodle_app.command("mcp")
    def moodle_mcp():
        """Run the read-only Moodle MCP server on stdio (Claude Code starts it from .mcp.json)."""
        from ..server import moodle
        moodle.main()

    @moodle_app.command("courses")
    def moodle_courses():
        """Your Moodle courses with their ids (for config/subjects.yaml)."""
        from ..moodle import reader
        table = Table("id", "short name", "name", "code")
        for c in guarded(reader.my_courses):
            table.add_row(str(c["id"]), c.get("short") or "", c.get("name") or "",
                          c.get("subject") or "-")
        console.print(table)

    @app.command()
    def sync(subject: str, dry_run: bool = typer.Option(False, "--dry-run")):
        """Download and index new course material from Moodle."""
        from ..moodle import sync as ms
        result = guarded(ms.sync_subject, subject.upper(), dry_run=dry_run)
        for line in result["added"]:
            console.print(f"[green]+[/green] {line}")
        console.print(f"\n{len(result['added'])} new, {result['already_there']} already there.")

    @app.command()
    def assignments(subject: str = typer.Argument(None),
                    all_: bool = typer.Option(False, "--all", help="Include submitted ones"),
                    json_out: bool = typer.Option(False, "--json")):
        """Moodle activities with due dates: what is pending, soonest first."""
        from ..moodle import reader
        items = guarded(reader.deadlines, subject.upper() if subject else None)
        if not all_:
            items = [t for t in items if t["status"] != "submitted"]
        if json_out:
            print_json(items)
            return
        zone, now = settings.get().tz, time.time()
        table = Table("subject", "due", "left", "type", "activity", "status")
        for t in items:
            if not t["due"]:
                when, left = "no date", "-"
            else:
                when = datetime.fromtimestamp(t["due"], zone).strftime("%Y-%m-%d %H:%M")
                days = (t["due"] - now) / 86400
                left = f"[red]{-days:.0f} d late[/red]" if days < 0 else f"{days:.0f} d"
            table.add_row(t["subject"], when, left, t["type"], t["name"][:60], t["status"])
        console.print(table)

    @assignment_app.command("fetch")
    def assignment_fetch(subject: str, cmid: int = typer.Argument(..., help="id= of the URL"),
                         dest: Path = typer.Argument(...)):
        """Download an assignment's description and attachments."""
        from ..moodle import sync as ms
        result = guarded(ms.fetch_assignment, subject.upper(), cmid, dest)
        console.print(f"{result['assignment']}: {result['description']}")
        for f in result["attachments"]:
            flag = "" if f["bytes"] == f["expected"] else "  [red]size differs[/red]"
            console.print(f"  {f['file']}  {f['bytes']} bytes{flag}")

    @assignment_app.command("submission")
    def assignment_submission(subject: str, cmid: int, dest: Path):
        """Download what you (or your team) submitted."""
        from ..moodle import sync as ms
        result = guarded(ms.fetch_submission, subject.upper(), cmid, dest)
        console.print(f"{result['assignment']}: {result['status']}")
        for f in result["attachments"]:
            console.print(f"  {f['file']}  {f['bytes']} bytes")
        for name in result["texts"]:
            console.print(f"  text: {name}")

    @app.command()
    def tasks(subject: str = typer.Argument(None), offline: bool = typer.Option(False)):
        """Task board: Moodle status joined with the local TASK.md folders."""
        from ..moodle import reader
        from ..planning import tasks as tb
        code = subject.upper() if subject else None
        rows = guarded(tb.board, [] if offline else guarded(reader.deadlines, code), code)
        table = Table("subject", "task", "due", "days", "moodle", "local", "methods")
        for row in sorted(rows, key=lambda r: r["due"] or 10**12):
            due = time.strftime("%Y-%m-%d", time.localtime(row["due"])) if row["due"] else "-"
            table.add_row(row["subject"], row["title"][:50], due,
                          "-" if row["days"] is None else str(row["days"]), row["moodle"],
                          row["local"], ", ".join(row["methods"]) or "-")
        console.print(table)

    @task_app.command("new")
    def task_new(subject: str, slug: str, title: str = typer.Option(""),
                 moodle_url: str = typer.Option("", "--moodle-url"),
                 term: str = typer.Option(None, help="Defaults to the subject's term"),
                 due: str = typer.Option("null", help="YYYY-MM-DD")):
        """Create cycles/<term>/<SUBJECT>/tasks/<NN-slug>/ with TASK.md, delivery/ and work/."""
        from ..core.paths import cycles, get_subject
        from ..core.text import slugify
        from ..vault import scaffold
        code = subject.upper()
        term = term or guarded(get_subject, code).get("term")
        if not term:
            die(f"{code} has no term in config/subjects.yaml; pass --term")
        base = cycles() / str(term) / code / "tasks"
        number = len(list(base.glob("*/TASK.md"))) + 1 if base.exists() else 1
        folder = base / f"{number:02d}-{slugify(slug)}"
        for sub in ("delivery", "work"):
            (folder / sub).mkdir(parents=True, exist_ok=True)
        task_md = folder / "TASK.md"
        if not task_md.exists():
            task_md.write_text(scaffold.task_file(folder.name, code, str(term), title or slug,
                                                  moodle_url, due), encoding="utf-8")
        console.print(f"[green]{folder}[/green]")

    @app.command()
    def projects(subject: str = typer.Argument(None),
                 clone: bool = typer.Option(False, "--clone", help="Clone missing repos")):
        """Project repos linked from TASK.md files (repos:), with their git state."""
        from ..planning import tasks as tb
        code = subject.upper() if subject else None
        rows = guarded(tb.clone_projects, code) if clone else guarded(tb.projects, code)
        table = Table("subject", "task", "repo", "cloned", "branch", "last commit", "dirty")
        for p in rows:
            table.add_row(p["subject"], p["task"], p["url"], MARK[p["cloned"]] if not clone
                          else p["action"], p["branch"] or "-", p["last_commit"] or "-",
                          "yes" if p["dirty"] else "-")
        console.print(table)

    @app.command()
    def agenda(subject: str = typer.Argument(None),
               offline: bool = typer.Option(False, "--offline", help="Skip mail and Calendar"),
               json_out: bool = typer.Option(False, "--json")):
        """Assessments of last week and the coming ones, from every source."""
        from ..planning import agenda as ag
        data = guarded(ag.build, subject, online=not offline)
        out = ag.render(data)
        ag.write_json(data)
        if json_out:
            print_json(ag.as_json(data))
            return
        table = Table("subject", "date", "left", "%", "state", "activity")
        for block in data["subjects"]:
            for it in block["items"]:
                if it["bucket"] == "before" and not it.get("late"):
                    continue
                left = f"{it['days']} d" if it["days"] >= 0 else f"{-it['days']} d ago"
                colour = "red" if it.get("late") else ("green" if it["state"] == "submitted"
                                                       else "yellow")
                table.add_row(block["code"], ag.fmt(it["end"]), left, str(it["weight"]),
                              f"[{colour}]{it['state']}[/{colour}]", it["label"])
        console.print(table)
        for a in data["alerts"]:
            console.print(f"[{'red' if a['level'] == 'bad' else 'yellow'}]{a['subject']}: {a['text']}[/]")
        for s in data["sources"]:
            console.print(f"{MARK[s['ok']]} {s['name']}: {s['detail']}")
        console.print(f"\nBoard: {out}")

    @app.command()
    def view(kind: str = typer.Argument(..., help="digest | status | agenda | tasks"),
             subject: str = typer.Argument(None),
             out: Path = typer.Option(None, "--out", help="Write the fragment to a file")):
        """Print the inline chat view (HTML fragment) that Claude shows with show_widget."""
        from ..rendering import views
        html = guarded(views.build, kind, subject)
        if out:
            out.write_text(html, encoding="utf-8")
            console.print(f"[green]{out}[/green]")
        else:
            print(html)

    @app.command()
    def digest(hours: int = typer.Option(24, help="Window for 'what changed'"),
               alerts: bool = typer.Option(False, "--alerts", help="Only what is new"),
               json_out: bool = typer.Option(False, "--json"),
               html: Path = typer.Option(None, "--html", help="Write the email HTML here"),
               send: str = typer.Option(None, "--send", help="Mail account id to send from"),
               to: str = typer.Option(None, "--to", help="Recipient (default: the account)")):
        """Morning summary or change alerts. No model: every line comes from a source."""
        from ..mail import base as mail
        from ..planning import digest as dg
        data = guarded(dg.build, hours=hours, alerts=alerts)
        if html:
            html.write_text(dg.as_html(data), encoding="utf-8")
        if json_out:
            print_json(data)
        else:
            console.print(dg.as_text(data))
        if send:
            if alerts and data.get("empty"):
                console.print("[dim]Nothing new: no email sent.[/dim]")
                return
            account = guarded(mail.get_account, send)
            msg_id = guarded(dg.send, data, send, to or account.get("address"))
            console.print(f"[green]Sent ({msg_id}).[/green]")
