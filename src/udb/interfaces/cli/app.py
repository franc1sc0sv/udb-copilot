"""The `udb` command."""
import typer

from udb.interfaces.cli.commands import classes, classroom, cloud, drive, mail, media, vault

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Study vault with mandatory citations, wired to your virtual classroom.")

vault.register(app)
classes.register(app)
classroom.register(app)
app.add_typer(mail.mail_app, name="mail")
app.add_typer(drive.drive_app, name="drive")
app.add_typer(media.app, name="recording")
app.add_typer(media.browser_app, name="browser")
app.add_typer(cloud.app, name="cloud")


@app.command("google-mcp", context_settings={"allow_extra_args": True,
                                             "ignore_unknown_options": True})
def google_mcp(ctx: typer.Context):
    """Run the Google Workspace MCP with the shared OAuth app (used from .mcp.json)."""
    cloud.google_mcp(list(ctx.args))


def main() -> None:
    from udb.config import secrets
    try:
        secrets.restore()  # cloud sessions: unpack UDB_SECRETS once, before anything runs
    except Exception:  # noqa: BLE001 - a broken bundle must not block the CLI
        pass
    app()
