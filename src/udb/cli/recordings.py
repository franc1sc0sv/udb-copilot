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
def discover(subject: str = typer.Argument(None),
             youtube: bool = typer.Option(True, help="Also the YouTube videos in course pages")):
    """Find recording links in Moodle (and YouTube embeds) and add them to the catalog."""
    from ..integrations.recordings import catalog
    before = len(catalog.load())
    items = guarded(catalog.discover, subject)
    if youtube:
        items = guarded(catalog.discover_youtube, subject)
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
def frames(recording_id: str,
           scenes: bool = typer.Option(False, "--scenes", help="Old mode: every scene change"),
           threshold: float = typer.Option(None), every: int = typer.Option(None),
           no_ocr: bool = typer.Option(False, "--no-ocr")):
    """One still per complete board (last state before erase or slide change)."""
    from ..integrations.recordings import catalog
    from ..integrations.recordings import frames as fr
    g = guarded(catalog.find, recording_id)
    if not g.get("source_id"):
        die(f"{recording_id} is not downloaded yet.")
    if not scenes and not every:
        res = guarded(fr.extract_boards, g["subject"], g["source_id"])
        console.print(f"[green]{res['total']} stills, {res['complete']} complete boards[/green]")
        return
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


def _stream_file(recording_id: str, kind: str = "stream") -> Path | None:
    # Browsers save repeats as "name (1).json": take the newest.
    stem = f"udb-{kind}-{recording_id.upper()}"
    places = [Path.home() / "Downloads", *Path("/mnt/c/Users").glob("*/Downloads")]
    found = [f for p in places if p.is_dir() for f in p.glob(f"{stem}*.json")]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


@app.command("stream-js")
def stream_js(recording_id: str):
    """JavaScript that saves a Stream transcript (run it on the Stream page, Claude in Chrome)."""
    from ..integrations.recordings import stream
    print(stream.extract_js(recording_id))


@app.command("boards-js")
def boards_js(recording_id: str, step: int = typer.Option(3, help="Seconds between looks")):
    """JavaScript that keeps a still of every complete board while stepping through Stream."""
    from ..integrations.recordings import stream
    print(stream.boards_js(recording_id, step))


@app.command("import-boards")
def import_boards(recording_id: str,
                  file: Path = typer.Argument(None, help="Default: udb-boards-<ID>.json in Downloads")):
    """Store the board stills saved from Stream as the recording's frames."""
    from ..integrations.recordings import stream
    file = file or _stream_file(recording_id, "boards")
    if not file:
        die(f"udb-boards-{recording_id.upper()}.json not found in Downloads; pass the path.")
    g = guarded(stream.import_boards, recording_id, file)
    console.print(f"[green]{g['id']}: {g['frames']} board stills stored. "
                  f"Read them with: udb recording read-boards {g['id']}[/green]")


@app.command("read-boards")
def read_boards(recording_id: str, all_frames: bool = typer.Option(False, "--all")):
    """Read every complete board with the local vision model (GPU, local only)."""
    from ..integrations.recordings import catalog, vision
    g = guarded(catalog.find, recording_id)
    if not g.get("source_id"):
        die(f"{recording_id} has no frames yet.")
    n = guarded(vision.read_frames, g["subject"], g["source_id"], not all_frames)
    console.print(f"[green]{n} boards read for {g['id']}.[/green]")


@app.command("stream")
def stream_cmd(recording_id: str,
               boards: bool = typer.Option(True, help="Also take stills of the boards"),
               read: bool = typer.Option(True, help="Read the boards with the local model")):
    """A view-only Teams recording, end to end, in udb's own Chrome: transcript,
    board stills (dense where an exercise is solved), board reading and radar."""
    from ..integrations.recordings import browser, catalog, stream
    g = guarded(catalog.find, recording_id)
    console.print(f"Opening {g['id']} in udb's Chrome…")
    transcript, stills = guarded(browser.read_stream, g["url"], boards,
                                 on_transcript=lambda t: console.print(
                                     f"  transcript: {len(t['entries'])} entries"))
    g = guarded(stream.import_transcript_data, recording_id, transcript)
    console.print(f"[green]{g['segments']} segments → {g['source_id']} ({g.get('date')})[/green]")
    if stills:
        g = guarded(stream.import_boards_data, recording_id, stills)
        console.print(f"[green]{g['frames']} board stills[/green]")
        if read:
            try:
                read_boards(recording_id, all_frames=False)
            except (SystemExit, typer.Exit):
                console.print("[yellow]Boards not read (needs the vision extra and a GPU).[/yellow]")
    radar(recording_id, minimum=5)


@app.command("stream-all")
def stream_all(subject: str = typer.Argument(None),
               redo: bool = typer.Option(False, help="Also recordings already transcribed")):
    """Every Teams recording of a subject (or all) through `udb recording stream`."""
    from ..integrations.recordings import catalog
    todo = [g for g in catalog.load() if "-YT-" not in g["id"]
            and (not subject or g["subject"] == subject.upper())
            and (redo or not g.get("source_id"))]
    console.print(f"{len(todo)} recordings")
    for g in todo:
        try:
            stream_cmd(g["id"], boards=True, read=True)
        except (SystemExit, typer.Exit):
            console.print(f"[red]{g['id']} failed; continuing[/red]")


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
    """Everything for one class video: download (if needed), transcript, boards,
    board reading (local GPU) and the radar."""
    from ..integrations.recordings import catalog
    g = guarded(catalog.find, recording_id)
    if not g.get("file"):  # attach sets it; a Stream transcript alone has no video
        download(recording_id, browser=browser)
    transcribe(recording_id, model=None, backend=None, quality=None)
    frames(recording_id, scenes=False, threshold=None, every=None, no_ocr=True)
    try:
        read_boards(recording_id, all_frames=False)
    except (SystemExit, typer.Exit):
        console.print("[yellow]Boards not read (needs the vision extra and a GPU).[/yellow]")
    from ..vault import index
    index.reindex_subject(g["subject"])
    radar(recording_id, minimum=5)


browser_app = typer.Typer(help="udb's own Chrome (Stream recordings).")


@browser_app.command("login")
def browser_login():
    """Open udb's Chrome once to sign in to Microsoft (the session is kept)."""
    from ..integrations.recordings import browser
    guarded(browser.login)
    console.print("[green]Signed in. udb recording stream <ID> now runs without you.[/green]")
