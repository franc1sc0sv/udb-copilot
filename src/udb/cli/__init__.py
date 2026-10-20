"""The `udb` command."""
import typer

from . import classes, classroom, mail, recordings, vault

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Study vault with mandatory citations, wired to your virtual classroom.")

vault.register(app)
classes.register(app)
classroom.register(app)
app.add_typer(mail.mail_app, name="mail")
app.add_typer(mail.drive_app, name="drive")
app.add_typer(recordings.app, name="recording")


def main() -> None:
    app()
