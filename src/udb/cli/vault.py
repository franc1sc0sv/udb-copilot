"""Setup, sources, index and checks."""
from pathlib import Path

import typer
from rich.table import Table

from .common import console, guarded, report


def register(app: typer.Typer) -> None:
    setup_app = typer.Typer(help="Wire udb into tools (Claude Code, MathJax).")
    app.add_typer(setup_app, name="setup")

    @app.command()
    def init(folder: Path = typer.Argument(Path("."), help="Data folder to create or adopt")):
        """Create a data home: udb.yaml, config examples, vault/, cycles/, Claude Code setup."""
        from .. import setup
        home = setup.init(folder)
        console.print(f"[green]Data home ready at {home}[/green]")
        console.print("Next: edit config/subjects.yaml, then `udb moodle login`.")

    @setup_app.command("claude")
    def setup_claude(folder: Path = typer.Argument(None)):
        """Write skills, agents, hooks, .mcp.json and the CLAUDE.md block into the data home."""
        from .. import setup
        from ..core import settings
        home = folder.resolve() if folder else guarded(settings.get).home
        console.print("Updated: " + ", ".join(setup.setup_claude(home)))

    @setup_app.command("mathjax")
    def setup_mathjax():
        """Install MathJax (Node) used to render formulas to SVG. Runs once per machine."""
        from ..rendering import math_svg
        console.print(f"[green]{guarded(math_svg.install)}[/green]")

    @app.command()
    def mcp():
        """Run the vault MCP server on stdio (Claude Code starts it from .mcp.json)."""
        from ..server.app import main
        main()

    @app.command(hidden=True)
    def hook(event: str = typer.Argument(..., help="pre | post | session")):
        """Claude Code hook entry point (reads the hook JSON on stdin)."""
        from ..agent import guards
        raise typer.Exit(guards.run(event))

    @app.command()
    def subjects():
        """List the configured subjects."""
        from ..core.paths import load_subjects
        table = Table("code", "name", "kind", "term", "moodle", "days")
        for s in guarded(load_subjects):
            table.add_row(s["code"], s["name"], s["kind"], str(s.get("term") or "-"),
                          str(s.get("moodle_course_id") or "-"), ", ".join(s["days"]))
        console.print(table)

    @app.command()
    def ingest(subject: str, path: Path, kind: str = typer.Option("course"),
               class_number: int = typer.Option(None, "--class"),
               title: str = typer.Option(None)):
        """Register and index a local file."""
        from ..vault import ingest as ing
        result = guarded(ing.ingest_file, subject.upper(), path, kind=kind,
                         class_number=class_number, title=title)
        console.print(f"[green]{result['source']['id']}[/green] · {result['chunks']} chunks")

    @app.command()
    def reindex(subject: str = typer.Argument(None, help="Empty = every subject")):
        """Rebuild the search index from derived/ text."""
        from ..vault import index
        counts = guarded(index.reindex_all) if not subject else {
            subject.upper(): guarded(index.reindex_subject, subject.upper())}
        for code, n in counts.items():
            console.print(f"{code}: [green]{n} chunks[/green]")

    @app.command()
    def verify(subject: str = typer.Argument(None),
               path: Path = typer.Option(None, "--path", help="Check one file")):
        """Check citations, plain language, methods and coverage. No model."""
        from .. import checks
        if path:
            found = guarded(checks.check_file, path)
            scope = str(path)
        else:
            found = guarded(checks.check_subject, subject.upper() if subject else None)
            scope = f"vault/{subject.upper()}" if subject else "all"
        checks.write_report(found, scope)
        raise typer.Exit(report(found, "Vault"))

    @app.command()
    def coverage(subject: str = typer.Argument(None)):
        """Topics the material opens that the class note does not cover."""
        from ..checks import coverage as cov
        raise typer.Exit(report(guarded(cov.check_subject, subject), "Coverage"))

    @app.command()
    def figures(subject: str, source: str = typer.Option(None, help="Only this SRC id"),
                dpi: int = typer.Option(110)):
        """Extract figures (PDF pages, HTML images) to vault/<SUBJECT>/figures/."""
        from ..vault import figures as fig
        result = guarded(fig.extract, subject.upper(), source, fetch=fig.http_fetch, dpi=dpi)
        for sid, info in result.items():
            saved = len(info.get("pages", [])) + len(info.get("images", []))
            if saved or info.get("pending"):
                console.print(f"{sid}  {info['title']}: {saved} saved, "
                              f"{len(info.get('pending', []))} pending")

    @app.command()
    def migrate(dry_run: bool = typer.Option(False, "--dry-run")):
        """Rewrite pre-0.1 Spanish keys (front matter, registry, catalogs) to English."""
        from .. import migrate as mig
        changed = guarded(mig.run, dry_run=dry_run)
        for line in changed:
            console.print(line)
        console.print(f"{len(changed)} files {'would change' if dry_run else 'changed'}.")

    @app.command()
    def diagrams():
        """The diagram catalog."""
        from ..rendering import diagrams as dg
        table = Table("id", "use for", "base")
        for entry in dg.CATALOG:
            table.add_row(entry["id"], entry["use_for"], entry["mermaid"] or "svg/excalidraw")
        console.print(table)

