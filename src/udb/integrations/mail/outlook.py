"""Outlook (Microsoft 365 or outlook.com) over Microsoft Graph.

Login is OAuth authorization code + PKCE: `udb mail login <id>` prints a
Microsoft link; sign in on any device, then paste back the `http://localhost`
URL the browser ends on (it does not need to load). From scripts or a phone,
run it in two steps: `--start` prints the link, `--finish <url>` completes it.
`--device` uses the device-code flow, which many tenants block since 2025.
The token cache is saved under the secrets folder. Needs `pip install udb-copilot[outlook]` (msal) and
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
# Files.ReadWrite is what Graph demands to read shared links (class recordings);
# udb never writes files. offline_access is added by MSAL itself.
SCOPES = ["User.Read", "Mail.Read", "Files.ReadWrite"]
REDIRECT = "http://localhost"
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


def _pending(account: dict) -> Path:
    return secret_path(account).with_suffix(".pending.json")


def login_start(account: dict) -> str:
    """Step 1: the sign-in link. The PKCE flow waits in a private file until step 2."""
    import json
    app, _, _ = _app(account)
    flow = app.initiate_auth_code_flow(SCOPES, redirect_uri=REDIRECT,
                                       login_hint=account.get("address"), prompt="select_account")
    pending = _pending(account)
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.touch(mode=0o600, exist_ok=True)
    pending.write_text(json.dumps(flow), encoding="utf-8")
    return flow["auth_uri"]


def login_finish(account: dict, redirected_url: str) -> str:
    """Step 2: the URL the browser ended on (http://localhost/?code=...)."""
    import json
    from urllib.parse import parse_qs, urlparse
    pending = _pending(account)
    if not pending.exists():
        raise MailError(f"no login in progress for {account['id']}; run --start first")
    flow = json.loads(pending.read_text(encoding="utf-8"))
    params = {k: v[0] for k, v in parse_qs(urlparse(redirected_url.strip()).query).items()}
    if "error" in params:
        raise MailError(f"Microsoft refused: {params.get('error_description', params['error'])}")
    app, cache, path = _app(account)
    result = app.acquire_token_by_auth_code_flow(flow, params)
    if "access_token" not in result:
        raise MailError(f"login failed: {result.get('error_description', result.get('error'))}")
    pending.unlink(missing_ok=True)
    _save(cache, path)
    return path.as_posix()


def login(account: dict, device: bool = False) -> str:
    if not device:
        print("Open this link, sign in, and paste the address the browser ends on "
              "(http://localhost/..., it will not load):\n")
        print(login_start(account) + "\n")
        return login_finish(account, input("URL: "))
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

