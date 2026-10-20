"""Mail accounts (Gmail, Outlook, IMAP) and Google Drive."""
import getpass
from datetime import datetime
from pathlib import Path

import typer
from rich.table import Table

from .common import MARK, console, die, guarded, print_json

mail_app = typer.Typer(help="Every mail account in config/mail.yaml.")
drive_app = typer.Typer(help="Google Drive transfers, streamed from disk with an MD5 check.")


@mail_app.command("accounts")
def accounts():
    """Configured accounts and whether their credentials work."""
    from ..integrations.mail import base
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
    from .wizard import mail_add
    guarded(mail_add)


@mail_app.command("login")
def login(account_id: str,
          client_secret: Path = typer.Option(None, help="Google OAuth client JSON; default: the "
                                             "Workspace MCP's app"),
          scope: list[str] = typer.Option([], help="Extra Google scopes: calendar.read, drive")):
    """Store credentials for one account (outside the repo, mode 600)."""
    from ..integrations.mail import base
    acc = guarded(base.get_account, account_id)
    kind = acc.get("provider")
    if kind == "gmail" and acc.get("auth") != "app-password":
        from ..integrations.google import oauth
        scopes = ["gmail.read"] + (["gmail.send"] if acc.get("send") else [])
        scopes += (["calendar.read"] if acc.get("calendar") else []) + list(scope)
        if acc.get("drive") and "drive" not in scopes:
            scopes.append("drive")
        creds = guarded(oauth.login, scopes, client_secret)
        oauth.write_creds(base.secret_path(acc), creds)
    elif kind == "outlook":
        from ..integrations.mail import outlook
        guarded(outlook.login, acc)
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
    from ..integrations.mail import base
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
    from ..integrations.mail import base
    if dest.exists() and any(dest.iterdir()):
        die(f"{dest} is not empty; use a new folder")
    provider = base.provider_for(guarded(base.get_account, account_id))
    for path in guarded(provider.attachments, message_id, dest, pdf_only):
        console.print(f"[green]{path}[/green]")


@drive_app.command("upload")
def drive_upload(folder_id: str, files: list[Path],
                 as_doc: bool = typer.Option(False, "--as-doc", help="Convert .docx to Google Docs")):
    from ..integrations.google import drive
    for f in files:
        info = guarded(drive.upload, folder_id, f, as_doc)
        mark = {True: "md5 ok", False: "[red]md5 MISMATCH[/red]", None: "converted"}[info["md5_ok"]]
        console.print(f"{f.name} -> {info.get('webViewLink', info['id'])} ({mark})")


@drive_app.command("replace")
def drive_replace(file_id: str, file: Path):
    """Replace a file's content keeping its link."""
    from ..integrations.google import drive
    info = guarded(drive.replace, file_id, file)
    console.print(f"{file.name} -> {info['id']} (md5 {'ok' if info['md5_ok'] else 'n/a'})")


@drive_app.command("download")
def drive_download(dest: Path, file_ids: list[str]):
    from ..integrations.google import drive
    for fid in file_ids:
        info = guarded(drive.download, fid, dest)
        console.print(f"{info['file']} (md5 {'ok' if info['md5_ok'] else '[red]MISMATCH[/red]'})")


@drive_app.command("trash")
def drive_trash(file_ids: list[str]):
    from ..integrations.google import drive
    for fid in file_ids:
        guarded(drive.trash, fid)
        console.print(f"{fid} -> trash")
