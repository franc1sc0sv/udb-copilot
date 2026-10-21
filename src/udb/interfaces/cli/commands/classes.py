"""Classes, methods, notes, exercises and study sessions."""
import asyncio
from datetime import date
from pathlib import Path

import typer
from rich.table import Table

from udb.domain.text.normalize import slugify
from udb.interfaces.cli.common import console, die, guarded, print_json

STAGE_COLOUR = {"complete": "green", "no material": "dim", "render lesson": "cyan"}


def register(app: typer.Typer) -> None:
    class_app = typer.Typer(help="Class folders: create, write, render.")
    method_app = typer.Typer(help="The teacher's methods.")
    note_app = typer.Typer(help="Concept notes.")
    app.add_typer(class_app, name="class")
    app.add_typer(method_app, name="method")
    app.add_typer(note_app, name="note")

    @app.command()
    def status(subject: str = typer.Argument(None),
               json_out: bool = typer.Option(False, "--json"),
               html: bool = typer.Option(False, "--html", help="Also write index/status.html")):
        """State of every class and the next step. Offline."""
        from udb.domain.planning import status as st
        data = guarded(st.build, subject)
        if json_out:
            print_json(data)
            return
        for s in data["subjects"]:
            table = Table(title=f"{s['code']} — {s['name']}", title_justify="left", pad_edge=False,
                          padding=(0, 1))
            for col in ("#", "date", "mat", "cov", "rec", "note", "methods", "ex", "task",
                        "html", "err", "stage"):
                table.add_column(col, no_wrap=True)
            for r in s["classes"]:
                colour = STAGE_COLOUR.get(r["stage"], "yellow")
                cov = r.get("material_covered")
                table.add_row(f"{r['class']:02d}", r["date"][5:], str(r["material"]),
                              "-" if cov is None else f"{cov}%", r["recording"][:5], r["explanation"][:5],
                              (f"{len(r['methods'])}" + ("!" if any(m["status"] == "conflict"
                                                                    for m in r["methods"]) else ""))
                              if r["methods"] else "-",
                              str(len(r["exercises"]) or "-"), r["assignment"][:4],
                              "✓" if r["lesson"] else "-", str(r["verify_errors"] or "-"),
                              f"[{colour}]{r['stage']}[/{colour}]")
            if s["classes"]:
                console.print(table)
            else:
                console.print(f"[bold]{s['code']} — {s['name']}[/bold]: no class folders.")
            if s["hint"]:
                console.print(f"  [yellow]{s['hint']}[/yellow]")
            if s["next"]:
                console.print(f"  next: [bold]{s['next']}[/bold]\n")
        if html:
            console.print(f"Board: {st.render(data)}")

    @class_app.command("new")
    def class_new(subject: str, when: str = typer.Argument(None, help="YYYY-MM-DD (default today)"),
                  number: int = typer.Option(None, "--n"), title: str = typer.Option("")):
        """Create a class folder with the class.md template."""
        from udb.domain.study import classes, scaffold
        code = subject.upper()
        number = number or classes.next_number(code)
        folder = classes.create(code, number, when or date.today().isoformat())
        target = folder.path / "class.md"
        if not target.exists():
            target.write_text(scaffold.class_note(code, number, folder.date,
                                                  classes.subject_kind(code), title),
                              encoding="utf-8")
        console.print(f"[green]{folder.path}[/green]")

    @class_app.command("write")
    def class_write(number: int, subject: str, budget: float = typer.Option(2.0)):
        """Write the explanation of a class with Claude (needs the agent extra)."""
        from udb.domain.study import classes
        from udb.interfaces.claude import runner
        code = subject.upper()
        folder = classes.get_class(code, number)
        if not folder:
            die(f"class {number} of {code} does not exist. Run: udb class new {code} <date>")
        sources = classes.sources_for(code, number)
        if not sources:
            die(f"class {number} has no material. Run: udb ingest {code} <file> --class {number}")
        prompt = (f"Write the explanation of class {number} of {code} (subject kind: "
                  f"{classes.subject_kind(code)}). Use the 'scribe' subagent. Output file: "
                  f"{folder.path / 'class.md'}. Sources of this class: {[s['id'] for s in sources]}. "
                  "Keep the template sections and front matter. Every claim with its anchor from "
                  "vault_quote. At least one mermaid diagram and one example with real numbers. "
                  f"If the class teaches a procedure, say at the end: udb method extract <topic> {code}")
        result = guarded(runner.go, prompt, subject=code, budget=budget)
        console.print(f"\n[dim]cost {result['cost']:.3f} USD[/dim]")

    @class_app.command("lesson")
    def class_lesson(number: int, subject: str):
        """Render the HTML lesson page of a class."""
        from udb.domain.study import classes
        from udb.rendering import lesson
        folder = classes.get_class(subject.upper(), number)
        if not folder or not folder.has("class.md"):
            die(f"class {number} has no written class.md")
        console.print(f"[green]{guarded(lesson.write_lesson, folder.path / 'class.md')}[/green]")

    @method_app.command("new")
    def method_new(subject: str, slug: str, title: str = typer.Option(""),
                   classes_: list[int] = typer.Option([], "--class")):
        """Create an empty method from the template."""
        from udb.domain.study import methods, scaffold
        path = methods.path_for(subject.upper(), slugify(slug))
        if path.exists():
            die(f"{path} already exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(scaffold.method_note(slugify(slug), title or slug, subject.upper(),
                                             classes_), encoding="utf-8")
        console.print(f"[green]{path}[/green]")

    @method_app.command("extract")
    def method_extract(topic: str, subject: str, budget: float = typer.Option(1.5)):
        """Extract the teacher's method for a topic with Claude."""
        from udb.domain.study import methods
        from udb.interfaces.claude import runner
        code, slug = subject.upper(), slugify(topic)
        prompt = (f"Extract the teacher's method for '{topic}' in {code}. Use the 'methodist' "
                  f"subagent. Output file: {methods.path_for(code, slug)}. Find the example the "
                  "teacher solved, in the slides and the recording. Copy the steps, in order, with "
                  "the teacher's words, one citation per step. If sources disagree set "
                  "status: conflict and ask me. Never invent a step.")
        result = guarded(runner.go, prompt, subject=code, budget=budget)
        console.print(f"\n[dim]cost {result['cost']:.3f} USD[/dim]")

    @method_app.command("list")
    def method_list(subject: str):
        """Methods of a subject with their status."""
        from udb.domain.study import methods
        table = Table("slug", "status", "steps", "classes")
        for m in methods.list_all(subject.upper()):
            table.add_row(m.slug, m.status, str(len(m.steps)), ", ".join(map(str, m.classes)))
        console.print(table)

    @note_app.command("new")
    def note_new(subject: str, term: str, class_number: int = typer.Option(None, "--class")):
        """Create a concept note from the template for the subject kind."""
        from udb.config.paths import subject_dir
        from udb.domain.study import classes, scaffold
        code = subject.upper()
        path = subject_dir(code) / "concepts" / f"{slugify(term)}.md"
        if path.exists():
            die(f"{path} already exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(scaffold.concept_note(classes.subject_kind(code), term, code,
                                              class_number), encoding="utf-8")
        console.print(f"[green]{path}[/green]")

    @app.command()
    def exercise(path: Path, budget: float = typer.Option(1.5)):
        """Solve an assignment following the teacher's method, with Claude."""
        from udb.config.paths import subject_of_path
        from udb.interfaces.claude import runner
        if not path.exists():
            die(f"{path} does not exist")
        prompt = (f"Solve the assignment in {path}. Use the 'methodist' subagent. Call method_get "
                  "first: NOT_FOUND means do not solve, tell me which method is missing and stop. "
                  "Build the HTML step cards with method_step on every step and finish with "
                  "method_check.")
        guarded(runner.go, prompt, subject=subject_of_path(path), budget=budget)

    @app.command()
    def study(subject: str = typer.Argument(None), budget: float = typer.Option(2.0)):
        """Interactive study session (the tutor asks, you answer)."""
        from udb.interfaces.claude import runner
        opening = (f"Start a study session{' for ' + subject.upper() if subject else ''}. Use the "
                   "'tutor' subagent. Call ledger_due and ledger_weak. Ask ONE question and wait "
                   "for my answer. Then correct me with the quote and record the result.")
        guarded(lambda: asyncio.run(runner.chat(opening, subject=subject, budget=budget)))

    @app.command()
    def explain(topic: str, subject: str = typer.Argument(None), budget: float = typer.Option(1.0)):
        """Feynman method: you explain, the tutor corrects with citations."""
        from udb.interfaces.claude import runner
        opening = (f"I will explain '{topic}'. Use the 'tutor' subagent. First ask me to explain "
                   "it in my words. Then compare with the cited material: what I got right, what "
                   "I missed, what I said backwards, each with its exact quote.")
        guarded(lambda: asyncio.run(runner.chat(opening, subject=subject, budget=budget)))

    @app.command()
    def ask(question: str, subject: str = typer.Argument(None), budget: float = typer.Option(1.0),
            follow: bool = typer.Option(False, "--follow", help="Continue the last conversation")):
        """Ask the vault. Answers only with what is cited."""
        from udb.domain.study import ledger
        from udb.interfaces.claude import runner
        resume = ledger.last_session(subject) if follow and subject else None
        prompt = (f"{question}\n\nAnswer ONLY with what is in the indexed material, citing every "
                  "claim with its source and page or minute. If the material does not cover it, "
                  "say so clearly.")
        guarded(runner.go, prompt, subject=subject, budget=budget, resume=resume)

    @app.command()
    def stats(subject: str = typer.Argument(None)):
        """Study progress (cards, reviews, due today)."""
        from udb.domain.study import ledger
        table = Table("metric", "value")
        for key, value in ledger.stats(subject).items():
            table.add_row(key, str(value))
        console.print(table)
