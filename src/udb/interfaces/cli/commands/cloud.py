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
         "www.googleapis.com", "github.com", "pypi.org"]
# What the cloud environment must allow (Network access: Custom).
ALLOWED = ["www.udbvirtual.edu.sv", "*.googleapis.com", "accounts.google.com", "github.com",
           "codeload.github.com", "objects.githubusercontent.com", "pypi.org",
           "files.pythonhosted.org", "astral.sh", "registry.npmjs.org"]
CLIP = ("clip.exe", "/mnt/c/Windows/System32/clip.exe", "pbcopy", "wl-copy")


@app.command("secrets")
def secrets_cmd(out: str = typer.Option(None, "--out", help="Write the bundle to this file "
                                         "instead of printing it")):
    """Pack every credential (Moodle, Google) into one value for UDB_SECRETS."""
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


@app.command("setup")
def setup(user: str = typer.Option(None, help="Moodle username")):
    """Once, on your computer: Moodle login if the token is dead, the UDB_SECRETS bundle on
    the clipboard, and what to paste in the cloud environment."""
    import getpass
    import subprocess

    from udb.integrations.mail import base as mail
    from udb.integrations.moodle import client

    try:
        with client.connect() as api:
            who = api.site_info().get("fullname")
        console.print(f"Moodle token works ({who}).", highlight=False)
    except (client.MissingCredentials, client.MoodleError) as exc:
        console.print(f"[yellow]Moodle token missing or dead: {exc}[/yellow]", highlight=False)
        user = user or input("Moodle user: ").strip()
        password = getpass.getpass("Moodle password (not stored): ")
        try:
            client.store_token(client.fetch_token(user, password))
        except (client.MoodleError, OSError) as err:
            die(str(err))
        console.print("[green]New Moodle token stored.[/green]")
    if not secrets.google_client() or not any(a.get("provider") == "gmail"
                                              for a in mail.accounts()):
        console.print("[yellow]No Gmail account or Google OAuth app: the cloud will have no "
                      "mail, Calendar or Drive. Run `udb mail add` first.[/yellow]")

    bundle, names = secrets.export()
    path = secrets.write_private(secrets.secrets_dir() / secrets.BUNDLE_FILE, bundle)
    console.print("Packed: " + ", ".join(names), highlight=False)
    copied = False
    for exe in CLIP:
        found = shutil.which(exe) or (exe if os.path.isfile(exe) else None)
        if found:
            copied = subprocess.run([found], input=bundle.encode(), check=False).returncode == 0
            break
    console.print(f"[green]UDB_SECRETS is {'on your clipboard and ' if copied else ''}in "
                  f"{path} (mode 600).[/green] Treat it like a password.\n")
    console.print("[bold]claude.ai/code → environment udb-copilot → edit:[/bold]")
    console.print("1. Network access: Custom (keep the default package registries), allow:")
    print("\n".join(ALLOWED))
    console.print("2. Environment variables: UDB_SECRETS=<paste>")
    console.print("No setup script is needed: the vault installs udb by itself. Use this one "
                  "environment for the phone and every routine.")
    console.print("\nThen, in a cloud session on the vault repo: [bold]udb cloud check[/bold]. "
                  "Run this again only after a new login or a new mail account.")


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
