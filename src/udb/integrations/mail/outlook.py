"""Outlook (Microsoft 365 or outlook.com) over Microsoft Graph.

Login uses the device-code flow: `udb mail login <id>` prints a short code,
you approve it on any device (your phone works), and the token cache is saved
under the secrets folder. Needs `pip install udb-copilot[outlook]` (msal) and
an app registration's client id in the account:

    - id: udb
      provider: outlook
      address: me@udb.edu.sv
      tenant: organizations      # organizations | consumers | <tenant id>
      client_id: 00000000-0000-0000-0000-000000000000

University tenants may require admin consent for new apps. If login says
so, forward that mailbox to Gmail instead.
"""
from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from .base import MailError, Message, Query, matches, safe_name, secret_from_env, secret_path

GRAPH = "https://graph.microsoft.com/v1.0/me"
SCOPES = ["Mail.Read", "User.Read"]
TIMEOUT = 20.0


def _app(account: dict):
    try:
        import msal
    except ImportError as exc:
        raise MailError("Outlook needs msal: uv tool install 'udb-copilot[outlook]'") from exc
    if not account.get("client_id"):
        raise MailError(f"account {account['id']} needs client_id (an Entra app registration)")
    cache = msal.SerializableTokenCache()
    raw = secret_from_env(account)
    path = secret_path(account)
    if raw:
        cache.deserialize(base64.b64decode(raw).decode() if not raw.startswith("{") else raw)
    elif path.exists():
        cache.deserialize(path.read_text(encoding="utf-8"))
    authority = f"https://login.microsoftonline.com/{account.get('tenant', 'organizations')}"
    return msal.PublicClientApplication(account["client_id"], authority=authority,
                                        token_cache=cache), cache, path


def _save(cache, path: Path) -> None:
    if cache.has_state_changed:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(mode=0o600, exist_ok=True)
            path.write_text(cache.serialize(), encoding="utf-8")
        except OSError:
            pass


def login(account: dict) -> str:
    app, cache, path = _app(account)
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise MailError(f"device flow failed: {flow.get('error_description', flow)}")
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise MailError(f"login failed: {result.get('error_description', result.get('error'))}")
    _save(cache, path)
    return path.as_posix()


def token_for(account: dict) -> str:
    app, cache, path = _app(account)
    found = app.get_accounts(username=account.get("address")) or app.get_accounts()
    result = app.acquire_token_silent(SCOPES, account=found[0]) if found else None
    if not result or "access_token" not in result:
        raise MailError(f"no valid Outlook session for {account['id']}. "
                        f"Run: udb mail login {account['id']}")
    _save(cache, path)
    return result["access_token"]


def _get(url: str, token: str, params: dict | None = None) -> dict:
    resp = httpx.get(url, params=params, timeout=TIMEOUT,
                     headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        raise MailError(f"Graph HTTP {resp.status_code}")
    return resp.json()


class OutlookProvider:
    def __init__(self, account: dict):
        self.account = account

    def search(self, query: Query) -> list[Message]:
        token = token_for(self.account)
        since = (datetime.now(UTC) - timedelta(days=query.since_days))
        data = _get(f"{GRAPH}/messages", token, {
            "$filter": f"receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "$orderby": "receivedDateTime desc", "$top": max(query.limit * 3, 50),
            "$select": "id,receivedDateTime,from,subject,bodyPreview,hasAttachments"})
        out = []
        for m in data.get("value", []):
            sender = (m.get("from") or {}).get("emailAddress") or {}
            when = datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00"))
            msg = Message(id=m["id"], account=self.account["id"], provider="outlook",
                          date=int(when.timestamp()),
                          sender=f"{sender.get('name', '')} <{sender.get('address', '')}>",
                          subject=m.get("subject") or "", snippet=m.get("bodyPreview") or "",
                          attachments=["(attachments)"] if m.get("hasAttachments") else [])
            if matches(msg, query):
                out.append(msg)
            if len(out) >= query.limit:
                break
        return out

    def attachments(self, message_id: str, dest: Path, pdf_only: bool = False) -> list[Path]:
        token = token_for(self.account)
        data = _get(f"{GRAPH}/messages/{message_id}/attachments", token)
        dest.mkdir(parents=True, exist_ok=True)
        saved = []
        for att in data.get("value", []):
            name = att.get("name") or "attachment"
            if "contentBytes" not in att or (pdf_only and not name.lower().endswith(".pdf")):
                continue
            target = dest / safe_name(name)
            target.write_bytes(base64.b64decode(att["contentBytes"]))
            saved.append(target)
        return saved

