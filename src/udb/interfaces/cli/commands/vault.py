"""Setup, sources, index and checks."""
from pathlib import Path

import typer
from rich.table import Table

from udb.interfaces.cli.common import console, guarded, report


def register(app: typer.Typer) -> None:
    setup_app = typer.Typer(help="Guided setup, or wire udb into tools (Claude Code, MathJax).",
                            invoke_without_command=True)
    app.add_typer(setup_app, name="setup")

    @app.command()
    def init(folder: Path = typer.Argument(Path("."), help="Data folder to create or adopt")):
        """Create a data home: udb.yaml, config examples, vault/, cycles/, Claude Code setup."""
        from udb.interfaces.claude import setup
        home = setup.init(folder)
        console.print(f"[green]Data home ready at {home}[/green]")
        console.print(f"Next: cd {home} && udb setup")

    @setup_app.callback()
    def setup_wizard(ctx: typer.Context):
        """Guided setup: Moodle login, subjects from your courses, mail accounts, Claude Code."""
        if ctx.invoked_subcommand:
            return
        from udb.interfaces.cli.commands.wizard import setup_all
        guarded(setup_all)

    @setup_app.command("claude")
    def setup_claude(folder: Path = typer.Argument(None)):
        """Write skills, agents, hooks, .mcp.json and the CLAUDE.md block into the data home."""
        from udb.config import settings
        from udb.interfaces.claude import setup
        home = folder.resolve() if folder else guarded(settings.get).home
        console.print("Updated: " + ", ".join(setup.setup_claude(home)))

    @setup_app.command("mathjax")
    def setup_mathjax():
        """Install MathJax (Node) used to render formulas to SVG. Runs once per machine."""
        from udb.rendering import math_svg
        console.print(f"[green]{guarded(math_svg.install)}[/green]")

    @app.command()
    def mcp():
        """Run the vault MCP server on stdio (Claude Code starts it from .mcp.json)."""
        from udb.interfaces.mcp.vault import main
        main()

    @app.command(hidden=True)
    def hook(event: str = typer.Argument(..., help="pre | post | session")):
        """Claude Code hook entry point (reads the hook JSON on stdin)."""
        from udb.interfaces.claude import hooks
        raise typer.Exit(hooks.run(event))

    @app.command()
    def subjects():
        """List the configured subjects."""
        from udb.config.paths import load_subjects
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
        from udb.domain.sources import ingest as ing
        result = guarded(ing.ingest_file, subject.upper(), path, kind=kind,
                         class_number=class_number, title=title)
        console.print(f"[green]{result['source']['id']}[/green] · {result['chunks']} chunks")

    @app.command()
    def reindex(subject: str = typer.Argument(None, help="Empty = every subject")):
        """Rebuild the search index from derived/ text."""
        from udb.domain.sources import index
        counts = guarded(index.reindex_all) if not subject else {
            subject.upper(): guarded(index.reindex_subject, subject.upper())}
        for code, n in counts.items():
            console.print(f"{code}: [green]{n} chunks[/green]")

    @app.command()
    def verify(subject: str = typer.Argument(None),
               path: Path = typer.Option(None, "--path", help="Check one file"),
               fix: bool = typer.Option(False, "--fix", help="Repair citations whose quote moved"),
               deep: bool = typer.Option(False, "--deep", help="Also ask a small model whether "
                                         "each paragraph says what its passages say")):
        """Check citations, plain language, methods and coverage. No model unless --deep."""
        from udb.domain import checks
        if fix:
            target = [path] if path else None
            found = checks.check_file(path) if target else checks.check_subject(
                subject.upper() if subject else None)
            for line in checks.apply_fixes(found):
                console.print(f"[green]fixed[/green] {line}")
        if path:
            found = guarded(checks.check_file, path)
            scope = str(path)
        else:
            found = guarded(checks.check_subject, subject.upper() if subject else None)
            scope = f"vault/{subject.upper()}" if subject else "all"
        if deep:
            from udb.domain.checks import citations
            from udb.domain.checks import deep as deep_check
            targets = [path] if path else citations.note_paths(subject.upper() if subject else None)
            for note in targets:
                if note.suffix == ".md":
                    found += guarded(deep_check.check_path, note)
        checks.write_report(found, scope)
        raise typer.Exit(report(found, "Vault"))

    sources_app = typer.Typer(help="How well each source was read, and fixes.",
                              invoke_without_command=True)
    app.add_typer(sources_app, name="sources")

    @sources_app.callback()
    def sources_report(ctx: typer.Context,
                       subject: str = typer.Option(None, "--subject", "-s", help="One subject"),
                       all_: bool = typer.Option(False, "--all", help="Also list the ok ones")):
        """Source health: ok, needs-ocr, images, no-text, unsupported, missing."""
        if ctx.invoked_subcommand:
            return
        from rich.table import Table as T

        from udb.domain.sources import health as sources
        rows = guarded(sources.report, subject)
        shown = rows if all_ else [r for r in rows if r["state"] not in ("ok", "transcript")]
        table = T("source", "type", "pages", "chars", "imgs read", "embeds", "state", "fix")
        for r in shown:
            colour = {"ok": "green", "transcript": "green"}.get(r["state"], "yellow")
            table.add_row(r["id"], r["type"], str(r["pages"]), str(r["chars"]),
                          f"{r['images_read']}/{r['images']}", str(r["embeds"]),
                          f"[{colour}]{r['state']}[/{colour}]", r["fix"] or "")
        console.print(table)
        summ = sources.summary(rows)
        console.print(f"{summ['sources']} sources: {summ['by_state']} · figures read "
                      f"{summ['images_read']}/{summ['images']} · embedded content unread "
                      f"{summ['embeds_unread']}/{summ['embeds']} · OCR "
                      f"{'available' if summ['ocr_available'] else 'missing'}")

    @sources_app.command("fix")
    def sources_fix(target: str = typer.Argument(None, help="SUBJECT, a SRC id, or empty for all"),
                    no_images: bool = typer.Option(False, "--no-images")):
        """Re-extract stale sources, OCR scanned pages, download and read HTML figures."""
        from udb.domain.sources import health as sources
        sid = target if target and target.upper().startswith("SRC-") else None
        code = target.upper() if target and not sid else None
        rows = guarded(sources.fix, code, sid, images=not no_images,
                       progress=lambda r: console.print(f"[dim]{r['id']} ({r['state']})...[/dim]"))
        for r in rows:
            mark = f"[red]{r['error']}[/red]" if r["error"] else f"[green]{r['state']}[/green]"
            console.print(f"{r['id']}: {mark}  figures {r['images_read']}/{r['images']}")

    @sources_app.command("classes")
    def sources_classes(subject: str = typer.Argument(None, help="SUBJECT or empty for all")):
        """Assign each course file to its class from its Moodle name (never overrides)."""
        from udb.config.paths import subject_codes
        from udb.domain.sources import index, registry
        for code in [subject.upper()] if subject else subject_codes():
            done = guarded(registry.assign_classes, code)
            if done:
                index.reindex_subject(code)
            console.print(f"{code}: {len(done)} sources assigned"
                          + (f" ({', '.join(f'{s}→{n}' for s, n in done[:6])}"
                             + ("…" if len(done) > 6 else "") + ")" if done else ""))

    @app.command()
    def coverage(subject: str = typer.Argument(None)):
        """Topics the material opens that the class note does not cover."""
        from udb.domain.checks import coverage as cov
        raise typer.Exit(report(guarded(cov.check_subject, subject), "Coverage"))

    @app.command()
    def figures(subject: str, source: str = typer.Option(None, help="Only this SRC id"),
                dpi: int = typer.Option(110)):
        """Extract figures (PDF pages, HTML images) to vault/<SUBJECT>/figures/."""
        from udb.domain.sources import figures as fig
        result = guarded(fig.extract, subject.upper(), source, fetch=fig.http_fetch, dpi=dpi)
        for sid, info in result.items():
            saved = len(info.get("pages", [])) + len(info.get("images", []))
            if saved or info.get("pending"):
                console.print(f"{sid}  {info['title']}: {saved} saved, "
                              f"{len(info.get('pending', []))} pending")

    @app.command()
    def diagrams():
        """The diagram catalog."""
        from udb.rendering import diagrams as dg
        table = Table("id", "use for", "base")
        for entry in dg.CATALOG:
            table.add_row(entry["id"], entry["use_for"], entry["mermaid"] or "svg/excalidraw")
        console.print(table)

