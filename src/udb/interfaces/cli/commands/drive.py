"""`udb drive ...`: Google Drive transfers, streamed from disk with an MD5 check."""
from pathlib import Path

import typer

from udb.interfaces.cli.common import console, guarded

drive_app = typer.Typer(help="Google Drive transfers, streamed from disk with an MD5 check.")


@drive_app.command("upload")
def drive_upload(folder_id: str, files: list[Path],
                 as_doc: bool = typer.Option(False, "--as-doc", help="Convert .docx to Google Docs")):
    from udb.integrations.google import drive
    for f in files:
        info = guarded(drive.upload, folder_id, f, as_doc)
        mark = {True: "md5 ok", False: "[red]md5 MISMATCH[/red]", None: "converted"}[info["md5_ok"]]
        console.print(f"{f.name} -> {info.get('webViewLink', info['id'])} ({mark})")


@drive_app.command("replace")
def drive_replace(file_id: str, file: Path):
    """Replace a file's content keeping its link."""
    from udb.integrations.google import drive
    info = guarded(drive.replace, file_id, file)
    console.print(f"{file.name} -> {info['id']} (md5 {'ok' if info['md5_ok'] else 'n/a'})")


@drive_app.command("download")
def drive_download(dest: Path, file_ids: list[str]):
    from udb.integrations.google import drive
    for fid in file_ids:
        info = guarded(drive.download, fid, dest)
        console.print(f"{info['file']} (md5 {'ok' if info['md5_ok'] else '[red]MISMATCH[/red]'})")


@drive_app.command("trash")
def drive_trash(file_ids: list[str]):
    from udb.integrations.google import drive
    for fid in file_ids:
        guarded(drive.trash, fid)
        console.print(f"{fid} -> trash")
