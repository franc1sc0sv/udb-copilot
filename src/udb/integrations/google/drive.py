"""Google Drive: upload, replace, download and trash files, streamed from disk.

File content never passes through the chat, so it cannot be corrupted by
copying base64 around. Every transfer is checked against Drive's MD5.
Uses the Google account marked `drive: true` in `config/mail.yaml`
(login with `udb mail login <id> --scope drive`).
"""
import hashlib
import json
import mimetypes
from pathlib import Path

import httpx

from ..mail import base
from ..mail.gmail import token_for

API = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
DOCS_MIME = "application/vnd.google-apps.document"
FIELDS = "id,name,size,md5Checksum,mimeType,webViewLink"
TIMEOUT = 120.0


def drive_account() -> dict:
    for acc in base.accounts():
        if acc.get("provider") == "gmail" and acc.get("drive"):
            return acc
    raise base.MailError("no mail account has drive: true in config/mail.yaml")


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _headers() -> dict:
    return {"Authorization": f"Bearer {token_for(drive_account())}"}


def _send(method: str, url: str, metadata: dict, path: Path) -> dict:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    headers = _headers()
    start = httpx.request(method, url, params={"uploadType": "resumable", "fields": FIELDS},
                          headers={**headers, "X-Upload-Content-Type": mime,
                                   "Content-Type": "application/json; charset=UTF-8"},
                          content=json.dumps(metadata), timeout=TIMEOUT)
    if start.status_code != 200:
        raise base.MailError(f"Drive refused the upload: HTTP {start.status_code}")
    with path.open("rb") as fh:
        done = httpx.put(start.headers["Location"], content=fh, timeout=TIMEOUT,
                         headers={**headers, "Content-Type": mime})
    if done.status_code not in (200, 201):
        raise base.MailError(f"Drive upload failed: HTTP {done.status_code}")
    return done.json()


def _verified(info: dict, path: Path) -> dict:
    if info.get("mimeType") == DOCS_MIME:
        info["md5_ok"] = None  # converted documents have no checksum
    else:
        info["md5_ok"] = info.get("md5Checksum") == md5(path)
    return info


def upload(folder_id: str, path: Path, as_doc: bool = False) -> dict:
    meta = {"name": path.stem if as_doc else path.name, "parents": [folder_id]}
    if as_doc:
        meta["mimeType"] = DOCS_MIME
    return _verified(_send("POST", UPLOAD, meta, path), path)


def replace(file_id: str, path: Path) -> dict:
    """New content, same link."""
    return _verified(_send("PATCH", f"{UPLOAD}/{file_id}", {}, path), path)


def download(file_id: str, dest: Path) -> dict:
    headers = _headers()
    meta = httpx.get(f"{API}/{file_id}", params={"fields": "name,md5Checksum,size"},
                     headers=headers, timeout=TIMEOUT).json()
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / base.safe_name(meta["name"])
    with httpx.stream("GET", f"{API}/{file_id}", params={"alt": "media"}, headers=headers,
                      timeout=TIMEOUT) as resp:
        if resp.status_code != 200:
            raise base.MailError(f"Drive download failed: HTTP {resp.status_code}")
        with target.open("wb") as fh:
            for block in resp.iter_bytes():
                fh.write(block)
    return {"file": str(target), "md5_ok": md5(target) == meta.get("md5Checksum")}


def trash(file_id: str) -> None:
    resp = httpx.patch(f"{API}/{file_id}", json={"trashed": True}, headers=_headers(),
                       timeout=TIMEOUT)
    if resp.status_code != 200:
        raise base.MailError(f"Drive trash failed: HTTP {resp.status_code}")
