"""`udb recording ...`: class videos into citable text.

Downloadable videos (YouTube embeds, shared files): `process` runs download,
Whisper, board stills, board reading and the radar. View-only Teams recordings are
read in the student's own Chrome with Claude in Chrome: `url`, `stream-js` and
`import-stream`.
"""
from pathlib import Path

import typer
from rich.table import Table

from udb.domain.notes import anchors
from udb.interfaces.cli.common import MARK, console, die, guarded

app = typer.Typer(help="Class recordings: catalog, transcripts, board stills, radar.")

# Need the video on disk, the GPU or the student's Chrome: off in cloud mode.
LOCAL_ONLY = {"download", "attach", "transcribe", "frames", "read-boards", "process",
              "stream-js", "import-stream"}


@app.callback()
def _cloud_guard(ctx: typer.Context):
    from udb.config import settings
    if ctx.invoked_subcommand in LOCAL_ONLY:
        guarded(settings.require_local, f"udb recording {ctx.invoked_subcommand}")


def _found(recording_id: str) -> dict:
    from udb.integrations.media import catalog
    g = guarded(catalog.find, recording_id)
    if not g.get("source_id"):
        die(f"{recording_id} has no video or transcript yet "
            f"(udb recording process|stream {recording_id}).")
    return g


@app.command()
def board(subject: str = typer.Argument(None)):
    """Which recording is downloaded, transcribed and has board stills."""
    from udb.integrations.media import catalog
    rows = [r for r in guarded(catalog.board) if not subject or r["subject"] == subject.upper()]
    if not rows:
        console.print("[yellow]Empty catalog. Run: udb recording discover[/yellow]")
        return
    table = Table("id", "subject", "date", "title", "status", "transcribed", "boards")
    for r in rows:
        table.add_row(r["id"], r["subject"], (r.get("date") or "-")[:16], r["title"][:46],
                      r["status"], MARK[r["transcribed"]], str(r["frames"] or "-"))
    console.print(table)


@app.command()
def discover(subject: str = typer.Argument(None)):
    """Find Teams recordings in Moodle and YouTube videos in course pages."""
    from udb.integrations.media import catalog
    before = len(catalog.load())
    guarded(catalog.discover, subject)
    items = guarded(catalog.discover_youtube, subject)
    console.print(f"[green]{len(items) - before} new[/green], {len(items)} total.")


@app.command()
def download(recording_id: str):
    """Download a video (YouTube or another public link)."""
    from udb.integrations.media import download as dl
    path = guarded(dl.download, recording_id)
    console.print(f"[green]{path.name}[/green] ({path.stat().st_size / 1e6:.0f} MB)")


@app.command()
def attach(recording_id: str, file: str):
    """Link a video you downloaded yourself to its catalog entry."""
    from udb.integrations.media import download as dl
    g = guarded(dl.attach, recording_id, file)
    console.print(f"[green]{recording_id} -> {g['source_id']}[/green]")


@app.command()
def transcribe(recording_id: str, model: str = typer.Option(None, help="large (default) or turbo")):
    """Speech to text with timestamps (Whisper on the GPU, local only)."""
    from udb.domain.sources import registry
    from udb.integrations.media import asr, catalog
    g = _found(recording_id)
    video = registry.source_file(g["subject"], g["source_id"])
    console.print(f"[dim]transcribing {video.name}...[/dim]")
    guarded(asr.transcribe, video, g["subject"], g["source_id"], model=model)
    catalog.update(recording_id, status="transcribed")
    console.print("[green]transcribed[/green]")


@app.command()
def frames(recording_id: str):
    """One still per complete board (the last state before an erase or a slide change)."""
    from udb.integrations.media import frames as fr
    g = _found(recording_id)
    res = guarded(fr.extract_boards, g["subject"], g["source_id"])
    console.print(f"[green]{res['total']} stills, {res['complete']} complete boards[/green]")


@app.command("read-boards")
def read_boards(recording_id: str, all_frames: bool = typer.Option(False, "--all")):
    """Read every complete board with the local vision model (GPU, local only)."""
    from udb.integrations.media import vision
    g = _found(recording_id)
    n = guarded(vision.read_frames, g["subject"], g["source_id"], not all_frames)
    console.print(f"[green]{n} boards read for {g['id']}.[/green]")


@app.command()
def radar(recording_id: str, minimum: int = typer.Option(5)):
    """What the class said about exams, deadlines, date changes, grades and announcements."""
    from udb.integrations.media import radar as rd
    from udb.integrations.media import stream
    g = _found(recording_id)
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


def _read_and_finish(recording_id: str) -> None:
    from udb.domain.sources import index
    from udb.integrations.media import catalog
    try:
        read_boards(recording_id, all_frames=False)
    except (SystemExit, typer.Exit):
        console.print("[yellow]Boards not read (needs the vision extra and a GPU).[/yellow]")
    index.reindex_subject(guarded(catalog.find, recording_id)["subject"])
    radar(recording_id, minimum=5)


@app.command()
def process(recording_id: str):
    """A downloadable video end to end: download, Whisper, board stills, board reading,
    index and radar."""
    from udb.integrations.media import catalog
    if not guarded(catalog.find, recording_id).get("file"):
        download(recording_id)
    transcribe(recording_id, model=None)
    frames(recording_id)
    _read_and_finish(recording_id)


# Teams recordings, in Claude in Chrome: open `url`, run the `stream-js` script on that tab,
# then import the JSON it saves to Downloads.

@app.command()
def url(recording_id: str):
    """The address that opens the recording in Stream's player (for Claude in Chrome)."""
    from udb.integrations.media import catalog
    print(catalog.player_url(guarded(catalog.find, recording_id)["url"]))


def _downloaded(recording_id: str, kind: str) -> Path:
    stem = f"udb-{kind}-{recording_id.upper()}"
    places = [Path.home() / "Downloads", *Path("/mnt/c/Users").glob("*/Downloads")]
    found = [f for p in places if p.is_dir() for f in p.glob(f"{stem}*.json")]
    if not found:
        die(f"{stem}.json not found in Downloads; pass the path.")
    return max(found, key=lambda p: p.stat().st_mtime)  # "name (1).json" is the newest


@app.command("stream-js")
def stream_js(recording_id: str, boards: bool = typer.Option(False, "--boards")):
    """The script for Claude in Chrome: transcript (default) or board stills (--boards)."""
    from udb.integrations.media import stream
    print(stream.boards_js(recording_id) if boards else stream.extract_js(recording_id))


@app.command("import-stream")
def import_stream(recording_id: str, file: Path = typer.Argument(None),
                  boards: bool = typer.Option(False, "--boards")):
    """Import what the script saved: the transcript, or the board stills with --boards."""
    from udb.integrations.media import stream
    kind = "boards" if boards else "stream"
    file = file or _downloaded(recording_id, kind)
    if boards:
        g = guarded(stream.import_boards, recording_id, file)
        console.print(f"[green]{g['frames']} board stills stored[/green]")
        _read_and_finish(recording_id)
        return
    g = guarded(stream.import_transcript, recording_id, file)
    console.print(f"[green]{g['segments']} segments from Stream → {g['source_id']} "
                  f"({g['title']}, {g.get('date') or 'no date'})[/green]")
    radar(recording_id, minimum=5)
