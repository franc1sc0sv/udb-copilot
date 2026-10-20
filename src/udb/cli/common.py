import json
from datetime import date, datetime

import typer
from rich.console import Console

from ..core import settings

console = Console()
MARK = {True: "[green]✓[/green]", False: "[red]✗[/red]"}


def die(message: str, code: int = 1) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code)


def guarded(fn, *args, **kwargs):
    """Run fn; known failures become a red message instead of a traceback."""
    try:
        return fn(*args, **kwargs)
    except settings.HomeNotFound as exc:
        die(str(exc))
    except (RuntimeError, KeyError, ValueError, FileNotFoundError, OSError) as exc:
        die(f"{type(exc).__name__}: {exc}" if isinstance(exc, KeyError) else str(exc))


def report(findings: list, title: str) -> int:
    for f in findings:
        colour = "red" if f.level == "error" else "yellow"
        console.print(f"[{colour}]{f}[/{colour}]")
    errors = sum(1 for f in findings if f.level == "error")
    if not findings:
        console.print(f"[green]{title}: no problems.[/green]")
    else:
        console.print(f"\n{errors} errors, {len(findings) - errors} warnings.")
    return 1 if errors else 0


def print_json(data) -> None:
    def default(v):
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        return str(v)
    print(json.dumps(data, ensure_ascii=False, indent=2, default=default))
