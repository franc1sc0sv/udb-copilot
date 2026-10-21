"""Class recordings: discover, download, transcribe, frames, radar."""
from pathlib import Path

import typer
from rich.table import Table

from ..core import anchors
from .common import MARK, console, die, guarded

app = typer.Typer(help="Class recordings. Download and transcription run locally.")


@app.command()
def board(subject: str = typer.Argument(None)):
    """Which recording is downloaded, transcribed and has frames."""
    from ..integrations.recordings import catalog
    rows = [r for r in guarded(catalog.board) if not subject or r["subject"] == subject.upper()]
    if not rows:
        console.print("[yellow]Empty catalog. Run: udb recording discover[/yellow]")
        return
    table = Table("id", "subject", "date", "title", "status", "transcribed", "frames")
    for r in rows:
        table.add_row(r["id"], r["subject"], (r.get("date") or "-")[:16], r["title"][:46],
                      r["status"], MARK[r["transcribed"]], str(r["frames"] or "-"))
    console.print(table)


@app.command()
def discover(subject: str = typer.Argument(None)):
    """Find recording links in Moodle and add them to the catalog."""
    from ..integrations.recordings import catalog
    before = len(catalog.load())
    items = guarded(catalog.discover, subject)
    console.print(f"[green]{len(items) - before} new[/green], {len(items)} total.")


@app.command()
def download(recording_id: str, browser: str = typer.Option(None)):
    """Download the video (needs your Microsoft session in the browser)."""
    from ..integrations.recordings import download as dl
    path = guarded(dl.download, recording_id, browser=browser)
    console.print(f"[green]{path.name}[/green] ({path.stat().st_size / 1e6:.0f} MB)")


@app.command()
def attach(recording_id: str, file: str):
    """Link a video you downloaded yourself to its catalog entry."""
    from ..integrations.recordings import download as dl
    g = guarded(dl.attach, recording_id, file)
    console.print(f"[green]{recording_id} -> {g['source_id']}[/green]")


@app.command()
def transcribe(recording_id: str, model: str = typer.Option(None),
               backend: str = typer.Option(None), quality: str = typer.Option(None)):
    """Speech to text with timestamps, on the GPU (local, needs the asr extra)."""
    from ..integrations.recordings import asr, catalog
    from ..vault import registry
    g = guarded(catalog.find, recording_id)
    if not g.get("source_id"):
        die(f"{recording_id} is not downloaded. Run: udb recording download {recording_id}")
    video = registry.source_file(g["subject"], g["source_id"])
    console.print(f"[dim]transcribing {video.name}...[/dim]")
    out = guarded(asr.transcribe, video, g["subject"], g["source_id"], model=model,
                  backend=backend, quality=quality)
    catalog.update(recording_id, status="transcribed")
    console.print(f"[green]{out}[/green]\nNow index it: udb reindex {g['subject']}")


@app.command()
def frames(recording_id: str, threshold: float = typer.Option(None),
           every: int = typer.Option(None, help="One frame every N seconds"),
           no_ocr: bool = typer.Option(False, "--no-ocr")):
    """One frame per screen change, plus the text on each slide."""
    from ..integrations.recordings import catalog
    from ..integrations.recordings import frames as fr
    g = guarded(catalog.find, recording_id)
    if not g.get("source_id"):
        die(f"{recording_id} is not downloaded yet.")
    cfg = catalog.config()
    res = guarded(fr.extract, g["subject"], g["source_id"],
                  threshold=threshold or cfg.get("scene_threshold", cfg.get("umbral_escena", 0.35)),
                  every=every, width=cfg.get("frame_width", cfg.get("ancho_frame", 1280)))
    console.print(f"[green]{res['total']} frames[/green]")
    if not no_ocr:
        try:
            console.print(f"[green]text read in {fr.ocr(g['subject'], g['source_id'])} frames[/green]")
        except RuntimeError as exc:
            console.print(f"[yellow]{exc}[/yellow]")


@app.command()
def radar(recording_id: str, minimum: int = typer.Option(5)):
    """What the class said about exams, deadlines, date changes, grades and announcements."""
    from ..integrations.recordings import catalog, stream
    from ..integrations.recordings import radar as rd
    g = guarded(catalog.find, recording_id)
    if not g.get("source_id"):
        die(f"{recording_id} has no transcript yet (transcribe it or import-stream).")
    hits = guarded(rd.scan, g["subject"], g["source_id"], minimum=minimum,
                   on=stream.class_day(g))
    if not hits:
        console.print("[green]Nothing about exams, deadlines or announcements.[/green]")
        return
    console.print(f"[yellow]{len(hits)} mentions[/yellow] in {g['title']}\n")
    for h in sorted(hits, key=lambda h: h["t_start"]):
        dates = ", ".join(d["date"] + ("~" if d["approx"] else "") for d in h["dates"])
        console.print(f"[bold]{anchors.hhmmss(h['t_start'])}[/bold] "
                      f"[magenta]{' '.join(h['categories'])}[/magenta]"
                      + (f" [cyan]→ {dates}[/cyan]" if dates else ""))
        console.print(f"  {h['quote'][:400]}")


def _stream_file(recording_id: str) -> Path | None:
    name = f"udb-stream-{recording_id.upper()}.json"
    places = [Path.home() / "Downloads", *Path("/mnt/c/Users").glob("*/Downloads")]
    found = [p / name for p in places if (p / name).exists()]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


@app.command("stream-js")
def stream_js(recording_id: str):
    """JavaScript that saves a Stream transcript (run it on the Stream page, Claude in Chrome)."""
    from ..integrations.recordings import stream
    print(stream.extract_js(recording_id))


@app.command("import-stream")
def import_stream(recording_id: str,
                  file: Path = typer.Argument(None, help="Default: udb-stream-<ID>.json in Downloads")):
    """Turn a saved Stream transcript into the recording's citable transcript."""
    from ..integrations.recordings import stream
    file = file or _stream_file(recording_id)
    if not file:
        die(f"udb-stream-{recording_id.upper()}.json not found in Downloads; pass the path.")
    g = guarded(stream.import_transcript, recording_id, file)
    console.print(f"[green]{g['id']}: {g['segments']} segments from Stream → {g['source_id']} "
                  f"({g['title']}, {g.get('date') or 'no date'})[/green]")
    radar(recording_id, minimum=5)


@app.command()
def process(recording_id: str, browser: str = typer.Option(None)):
    """Download, transcribe, frames and radar in one go."""
    download(recording_id, browser=browser)
    transcribe(recording_id, model=None, backend=None, quality=None)
    frames(recording_id, threshold=None, every=None, no_ocr=False)
    radar(recording_id, minimum=4)
