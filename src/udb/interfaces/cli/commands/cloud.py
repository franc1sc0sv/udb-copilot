"""Cloud sessions: one secret variable, and a check that everything is reachable."""
import os
import shutil
import sys
from pathlib import Path

import typer
from rich.table import Table

from udb.config import secrets
from udb.interfaces.cli.common import MARK, console, die

app = typer.Typer(help="Configure the cloud once: secrets bundle and checks.")

HOSTS = ["www.udbvirtual.edu.sv", "oauth2.googleapis.com", "gmail.googleapis.com",
         "www.googleapis.com", "login.microsoftonline.com", "graph.microsoft.com",
         "github.com", "pypi.org"]


@app.command("secrets")
def secrets_cmd(out: str = typer.Option(None, "--out", help="Write the bundle to this file "
                                         "instead of printing it")):
    """Pack every credential (Moodle, Google, Outlook) into one value for UDB_SECRETS."""
    bundle, names = secrets.export()
    if not names:
        die("no credentials found. Run `udb moodle login` and `udb mail add` first.")
    console.print("Included: " + ", ".join(names), highlight=False)
    if out:
        secrets.write_private(Path(out), bundle)
        console.print(f"[green]Bundle written to {out} (mode 600).[/green]")
    else:
        console.print("\nPaste this as the value of [bold]UDB_SECRETS[/bold] in the cloud "
                      "environment (once). Treat it like a password.\n")
        print(bundle)


@app.command("check")
def check():
    """In a cloud session: secrets restored, hosts reachable, udb and uv present."""
    import httpx

    restored = secrets.restore()
    table = Table("check", "result")
    table.add_row("UDB_SECRETS set", MARK[bool(os.environ.get(secrets.BUNDLE_ENV))])
    table.add_row("files restored now", str(len(restored)))
    table.add_row("Google OAuth app", MARK[bool(secrets.google_client())])
    table.add_row("uv / uvx", MARK[bool(shutil.which("uvx"))])
    from udb.domain.sources import ocr
    table.add_row("OCR (scanned PDFs, figures)", MARK[ocr.available()])
    for host in HOSTS:
        try:
            httpx.head(f"https://{host}", timeout=8, follow_redirects=False)
            ok = True
        except httpx.HTTPError:
            ok = False
        table.add_row(host, MARK[ok])
    console.print(table)


def google_mcp(args: list[str]) -> None:
    """Start the Google Workspace MCP with the shared OAuth app (local or cloud)."""
    from udb.integrations.mail import base

    secrets.restore()
    env = dict(os.environ)
    env.update(secrets.google_client() or {})
    google = [a for a in base.accounts() if a.get("provider") == "gmail"]
    if google and not env.get("USER_GOOGLE_EMAIL"):
        env["USER_GOOGLE_EMAIL"] = google[0]["address"]
    uvx = shutil.which("uvx") or os.path.expanduser("~/.local/bin/uvx")
    os.execvpe(uvx, [uvx, "workspace-mcp", *(args or ["--tool-tier", "core"])], env)
    sys.exit(1)
