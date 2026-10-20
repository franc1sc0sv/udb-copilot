"""Gmail over the REST API (read; send only if the account allows it)."""
from __future__ import annotations

import base64
import json
from email.message import EmailMessage
from pathlib import Path

import httpx

from ..google import oauth
from .base import MailError, Message, Query, matches, safe_name, secret_from_env, secret_path

API = "https://gmail.googleapis.com/gmail/v1/users/me"
LEGACY_DIR = Path("~/.google_workspace_mcp/credentials").expanduser()


def load_creds(account: dict) -> tuple[dict, Path | None]:
    raw = secret_from_env(account)
    if raw:
        return json.loads(raw), None
    path = secret_path(account)
    if not path.exists():
        legacy = LEGACY_DIR / f"{account.get('address')}.json"
        if legacy.exists():
            return json.loads(legacy.read_text(encoding="utf-8")), legacy
        raise MailError(f"no credentials for {account['id']}. Run: udb mail login {account['id']}")
    return json.loads(path.read_text(encoding="utf-8")), path


def token_for(account: dict) -> str:
    creds, path = load_creds(account)
    return oauth.access_token(creds, save=path)


def _header(msg: dict, name: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _parts(part: dict):
    yield part
    for child in part.get("parts", []) or []:
        yield from _parts(child)


class GmailProvider:
    def __init__(self, account: dict):
        self.account = account

    def _q(self, query: Query) -> str:
        q = [f"newer_than:{query.since_days}d"]
        if query.terms:
            q.append("(" + " OR ".join(f'"{t}"' if " " in t else t for t in query.terms) + ")")
        if query.from_domains:
            q.append("(" + " OR ".join(f"from:{d}" for d in query.from_domains) + ")")
        return " ".join(q)

    def search(self, query: Query) -> list[Message]:
        token = token_for(self.account)
        ids = oauth.get(f"{API}/messages", token,
                        {"q": self._q(query), "maxResults": query.limit}).get("messages", [])
        out = []
        for item in ids:
            msg = oauth.get(f"{API}/messages/{item['id']}", token,
                            {"format": "metadata",
                             "metadataHeaders": ["From", "Subject"]})
            files = [p["filename"] for p in _parts(msg.get("payload", {})) if p.get("filename")]
            message = Message(id=item["id"], account=self.account["id"], provider="gmail",
                              date=int(msg.get("internalDate", "0")) // 1000,
                              sender=_header(msg, "From"), subject=_header(msg, "Subject"),
                              snippet=msg.get("snippet", ""), attachments=files)
            if matches(message, Query(terms=[], from_domains=query.from_domains)):
                out.append(message)
        return out

    def attachments(self, message_id: str, dest: Path, pdf_only: bool = False) -> list[Path]:
        token = token_for(self.account)
        msg = oauth.get(f"{API}/messages/{message_id}", token, {"format": "full"})
        dest.mkdir(parents=True, exist_ok=True)
        saved = []
        for part in _parts(msg.get("payload", {})):
            name, att = part.get("filename"), part.get("body", {}).get("attachmentId")
            if not name or not att or (pdf_only and not name.lower().endswith(".pdf")):
                continue
            data = oauth.get(f"{API}/messages/{message_id}/attachments/{att}", token)["data"]
            target = dest / safe_name(name)
            target.write_bytes(base64.urlsafe_b64decode(data))
            saved.append(target)
        return saved

    def send(self, to: str, subject: str, html: str, text: str = "") -> str:
        if not self.account.get("send"):
            raise MailError(f"account {self.account['id']} is not allowed to send "
                            "(set send: true and run `udb mail login` again)")
        msg = EmailMessage()
        msg["To"], msg["From"], msg["Subject"] = to, self.account.get("address", "me"), subject
        msg.set_content(text or "Este correo necesita un lector con HTML.")
        msg.add_alternative(html, subtype="html")
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        resp = httpx.post(f"{API}/messages/send", json={"raw": raw}, timeout=oauth.TIMEOUT,
                          headers={"Authorization": f"Bearer {token_for(self.account)}"})
        if resp.status_code != 200:
            raise MailError(f"Gmail send failed: HTTP {resp.status_code}")
        return resp.json()["id"]
