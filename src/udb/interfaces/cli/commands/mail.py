"""`udb mail ...`: mail accounts (Gmail, Outlook, IMAP)."""
import getpass
from datetime import datetime
from pathlib import Path

import typer
from rich.table import Table

from udb.interfaces.cli.common import MARK, console, die, guarded, print_json

mail_app = typer.Typer(help="Every mail account in config/mail.yaml.")


@mail_app.command("accounts")
def accounts():
    """Configured accounts and whether their credentials work."""
    from udb.integrations.mail import base
    table = Table("id", "provider", "address", "works")
    for acc in guarded(base.accounts):
        try:
            base.provider_for(acc).search(base.Query(since_days=1, limit=1))
            works = MARK[True]
        except Exception as exc:  # noqa: BLE001 - show why each account fails
            works = f"[red]{type(exc).__name__}: {str(exc)[:60]}[/red]"
        table.add_row(acc["id"], acc.get("provider", "?"), acc.get("address", ""), works)
    console.print(table)


@mail_app.command("add")
def add():
    """Add a mail account step by step (Gmail, Outlook or IMAP) and test it."""
    from udb.interfaces.cli.commands.wizard import mail_add
    guarded(mail_add)


@mail_app.command("login")
def login(account_id: str,
          client_secret: Path = typer.Option(None, help="Google OAuth client JSON; default: the "
                                             "Workspace MCP's app"),
          scope: list[str] = typer.Option([], help="Extra Google scopes: calendar.read, drive"),
          start: bool = typer.Option(False, "--start", help="Outlook: only print the sign-in link"),
          finish: str = typer.Option("", "--finish", help="Outlook: the localhost URL you ended on"),
          device: bool = typer.Option(False, "--device", help="Outlook: device-code flow")):
    """Store credentials for one account (outside the repo, mode 600)."""
    from udb.integrations.mail import base
    acc = guarded(base.get_account, account_id)
    kind = acc.get("provider")
    if kind == "gmail" and acc.get("auth") != "app-password":
        from udb.integrations.google import oauth
        scopes = ["gmail.read"] + (["gmail.send"] if acc.get("send") else [])
        scopes += (["calendar.read"] if acc.get("calendar") else []) + list(scope)
        if acc.get("drive") and "drive" not in scopes:
            scopes.append("drive")
        creds = guarded(oauth.login, scopes, client_secret)
        oauth.write_creds(base.secret_path(acc), creds)
    elif kind == "outlook":
        from udb.integrations.mail import outlook
        if start:
            console.print(guarded(outlook.login_start, acc), soft_wrap=True)
            console.print(f"Then: udb mail login {account_id} --finish '<localhost URL>'")
            return
        if finish:
            guarded(outlook.login_finish, acc, finish)
        else:
            guarded(outlook.login, acc, device)
    elif kind == "imap" or acc.get("auth") == "app-password":
        path = base.secret_path(acc)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600, exist_ok=True)
        path.write_text(getpass.getpass(f"App password for {acc['address']}: "), encoding="utf-8")
    else:
        die(f"unknown provider: {kind}")
    console.print(f"[green]{account_id}: credentials stored in {base.secret_path(acc)}[/green]")


@mail_app.command("search")
def search(terms: str = typer.Argument("", help="Comma-separated words, any of them"),
           days: int = typer.Option(7), account: str = typer.Option(None),
           limit: int = typer.Option(25), json_out: bool = typer.Option(False, "--json")):
    """Search every account (newest first)."""
    from udb.integrations.mail import base
    query = base.Query(since_days=days, terms=[t for t in terms.split(",") if t.strip()],
                       limit=limit)
    found, status = guarded(base.search_all, query, [account] if account else None)
    if json_out:
        print_json({"messages": [m.as_dict() for m in found], "accounts": status})
        return
    table = Table("date", "account", "from", "subject", "id")
    for m in found:
        table.add_row(datetime.fromtimestamp(m.date).strftime("%m-%d %H:%M"), m.account,
                      m.sender[:30], m.subject[:60], m.id[:16])
    console.print(table)
    for s in status:
        if not s["ok"]:
            console.print(f"[red]{s['account']}: {s['detail']}[/red]")


@mail_app.command("attachments")
def attachments(account_id: str, message_id: str, dest: Path,
                pdf_only: bool = typer.Option(False, "--pdf-only")):
    """Save a message's attachments into a NEW empty folder (they are untrusted data)."""
    from udb.integrations.mail import base
    if dest.exists() and any(dest.iterdir()):
        die(f"{dest} is not empty; use a new folder")
    provider = base.provider_for(guarded(base.get_account, account_id))
    for path in guarded(provider.attachments, message_id, dest, pdf_only):
        console.print(f"[green]{path}[/green]")
