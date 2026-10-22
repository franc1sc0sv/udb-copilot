"""Guided setup: Moodle, subjects and mail accounts, one question at a time."""
import getpass
import re

from rich.prompt import Confirm, IntPrompt, Prompt

from udb.config import schema
from udb.config.paths import load_yaml, save_yaml
from udb.interfaces.cli.common import console

APP_PASSWORD_URL = "https://myaccount.google.com/apppasswords"
KINDS_ES = {"engineering": "ingeniería", "math": "matemática", "physics": "física",
            "programming": "programación", "humanities": "humanidades", "general": "general"}


def _store_secret(account: dict, value: str) -> None:
    from udb.integrations.mail import base
    path = base.secret_path(account)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(value.replace(" ", ""), encoding="utf-8")


def _save_account(account: dict) -> None:
    data = load_yaml("mail.yaml") or {}
    accounts = [a for a in data.get("accounts", []) if a.get("id") != account["id"]]
    data["accounts"] = accounts + [account]
    data.setdefault("filters", [{"name": "teachers", "from_domains": ["udb.edu.sv"]},
                                {"name": "classroom", "from": ["udbvirtual.edu.sv"]}])
    save_yaml("mail.yaml", data)


def _test(account: dict) -> bool:
    from udb.integrations.mail import base
    try:
        base.provider_for(account).search(base.Query(since_days=2, limit=1))
        console.print("[green]Connected: the account works.[/green]")
        return True
    except Exception as exc:  # noqa: BLE001 - show the reason and let the user retry
        console.print(f"[red]It did not connect: {exc}[/red]")
        return False


def mail_add() -> dict | None:
    """Add one mail account interactively. Returns the saved account."""
    choice = Prompt.ask(
        "Account type\n  1 Gmail (Google login with your OAuth app, works in the cloud)\n"
        "  2 Gmail with an app password (only on this computer)\n"
        "  3 Other (IMAP)\nChoose",
        choices=["1", "2", "3"], default="1")
    address = Prompt.ask("Email address").strip()
    suggested = re.sub(r"[^a-z0-9]+", "-", address.split("@")[0].lower()).strip("-") or "mail"
    account_id = Prompt.ask("Short name for this account", default=suggested)
    send = Confirm.ask("Use it to send you the daily summary?", default=choice in ("1", "2"))

    if choice == "2":
        account = {"id": account_id, "provider": "gmail", "auth": "app-password",
                   "address": address, "send": send}
        console.print(f"\n1. Open {APP_PASSWORD_URL} (two-step verification must be on).\n"
                      "2. Create a password named udb and copy the 16 letters.\n")
        _store_secret(account, getpass.getpass("Paste the app password (hidden): "))
    elif choice == "1":
        from udb.integrations.google import oauth
        from udb.integrations.mail import base
        account = {"id": account_id, "provider": "gmail", "address": address, "send": send,
                   "calendar": Confirm.ask("Read Google Calendar too?", default=True),
                   "drive": Confirm.ask("Use Google Drive too?", default=False)}
        scopes = ["gmail.read"] + (["gmail.send"] if send else [])
        scopes += (["calendar.read"] if account["calendar"] else []) + (
            ["drive"] if account["drive"] else [])
        oauth.write_creds(base.secret_path(account), oauth.login(scopes))
    else:
        account = {"id": account_id, "provider": "imap", "address": address,
                   "host": Prompt.ask("IMAP server", default=f"imap.{address.split('@')[-1]}"),
                   "port": IntPrompt.ask("Port", default=993), "send": False}
        _store_secret(account, getpass.getpass("Password or app password (hidden): "))

    if not _test(account) and not Confirm.ask("Save it anyway?", default=False):
        return None
    _save_account(account)
    console.print(f"[green]Saved {account_id} in config/mail.yaml.[/green]")
    return account


def _pick_courses() -> None:
    from udb.integrations.moodle import reader
    courses = reader.my_courses()
    current = {s["moodle_course_id"]: s for s in load_yaml("subjects.yaml").get("subjects", [])
               if s.get("moodle_course_id")}
    console.print("\nYour Moodle courses:")
    for i, c in enumerate(courses, 1):
        mark = "✓" if c["id"] in current else " "
        console.print(f"  {mark} {i:2d}  {c['name']}  [dim]({c['short']})[/dim]")
    picked = Prompt.ask("Numbers of the courses you take this term, separated by commas",
                        default=",".join(str(i) for i, c in enumerate(courses, 1)
                                         if c["id"] in current))
    term = Prompt.ask("Term (example 2026-2)")
    subjects = []
    for raw in [p.strip() for p in picked.split(",") if p.strip().isdigit()]:
        course = courses[int(raw) - 1]
        old = current.get(course["id"], {})
        code = Prompt.ask(f"\n{course['name']}\n  code", default=old.get(
            "code", re.sub(r"[^A-Z]", "", (course["short"] or "").upper())[:3] or "SUB"))
        kind = Prompt.ask("  kind (" + ", ".join(f"{k}={v}" for k, v in KINDS_ES.items()) + ")",
                          choices=list(schema.KINDS), default=old.get("kind", "general"))
        days = Prompt.ask("  class days (mon,tue,wed,thu,fri,sat)",
                          default=",".join(old.get("days", [])))
        subjects.append({**old, "code": code.upper(), "name": course["name"], "kind": kind,
                         "term": term, "moodle_course_id": course["id"],
                         "days": [d.strip()[:3] for d in days.split(",") if d.strip()]})
    save_yaml("subjects.yaml", {"subjects": subjects})
    console.print(f"[green]{len(subjects)} subjects saved in config/subjects.yaml.[/green]")


def setup_all() -> None:
    """Moodle login, subjects, mail accounts, Claude Code wiring."""
    from udb.config import settings
    from udb.integrations.moodle import client
    from udb.interfaces.claude import setup

    home = settings.get().home
    console.print(f"[bold]udb setup[/bold] in {home}\n")
    try:
        client.read_token()
        console.print("[green]Moodle: token found.[/green]")
    except client.MissingCredentials:
        console.print("Moodle: log in once; only a token is stored.")
        user = Prompt.ask("Moodle user")
        client.store_token(client.fetch_token(user, getpass.getpass("Password (not stored): ")))
        console.print("[green]Moodle token stored.[/green]")
    if Confirm.ask("\nChoose your subjects from Moodle now?", default=True):
        _pick_courses()
    while Confirm.ask("\nAdd a mail account?", default=not load_yaml("mail.yaml").get("accounts")):
        mail_add()
    console.print("\nClaude Code: " + ", ".join(setup.setup_claude(home)))
    console.print("\n[bold]Done.[/bold] Try: udb status · udb digest · or ask Claude "
                  "\"¿qué tengo pendiente?\"")
