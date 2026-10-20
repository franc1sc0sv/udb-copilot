"""Google OAuth for an installed app, with nothing but httpx.

`login()` runs the loopback flow once: it prints a URL, you approve in any
browser, and Google redirects to a local port with a code. The result is an
"authorized user" JSON (refresh token, client id and secret), the same format
Google's own libraries use. `access_token()` refreshes it when needed.
"""
from __future__ import annotations

import json
import secrets
import time
import webbrowser
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TIMEOUT = 20.0

SCOPES = {
    "gmail.read": "https://www.googleapis.com/auth/gmail.readonly",
    "gmail.send": "https://www.googleapis.com/auth/gmail.send",
    "calendar.read": "https://www.googleapis.com/auth/calendar.readonly",
    "drive": "https://www.googleapis.com/auth/drive",
}


class GoogleError(RuntimeError):
    pass


def _expired(expiry: str | None) -> bool:
    if not expiry:
        return True
    try:
        when = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.timestamp() < time.time() + 60


def access_token(creds: dict, save: Path | None = None) -> str:
    """A valid access token. Refreshes, and writes the refreshed creds to `save`."""
    if creds.get("token") and not _expired(creds.get("expiry")):
        return creds["token"]
    if not all(creds.get(k) for k in ("refresh_token", "client_id", "client_secret")):
        raise GoogleError("Google credentials cannot be refreshed; run `udb mail login` again")
    resp = httpx.post(creds.get("token_uri") or TOKEN_URL, data={
        "grant_type": "refresh_token", "refresh_token": creds["refresh_token"],
        "client_id": creds["client_id"], "client_secret": creds["client_secret"]},
        timeout=TIMEOUT)
    if resp.status_code != 200:
        reason = resp.json().get("error", "") if resp.headers.get("content-type", "").startswith(
            "application/json") else ""
        hint = " (revoked or expired: run `udb mail login` again)" if reason == "invalid_grant" else ""
        raise GoogleError(f"Google refused the token refresh: HTTP {resp.status_code} {reason}{hint}")
    data = resp.json()
    creds["token"] = data["access_token"]
    creds["expiry"] = datetime.fromtimestamp(time.time() + data.get("expires_in", 3600),
                                             UTC).isoformat()
    if save is not None:
        try:
            write_creds(save, creds)
        except OSError:
            pass  # read-only secret mount in cloud: refresh again next time
    return creds["token"]


def write_creds(path: Path, creds: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(json.dumps(creds), encoding="utf-8")


def login(scopes: list[str], client_secret_file: Path | None = None, port: int = 8765) -> dict:
    """Run the loopback consent flow and return authorized-user credentials.

    The OAuth app is the one the Google Workspace MCP uses (GOOGLE_OAUTH_CLIENT_ID and
    GOOGLE_OAUTH_CLIENT_SECRET), unless a client JSON file is given.
    """
    from ...core import secrets as udb_secrets

    if client_secret_file:
        raw = json.loads(Path(client_secret_file).read_text(encoding="utf-8"))
        app = raw.get("installed") or raw.get("web") or raw
        client_id, client_secret = app["client_id"], app["client_secret"]
    else:
        client = udb_secrets.google_client()
        if not client:
            raise GoogleError("no Google OAuth app found: set GOOGLE_OAUTH_CLIENT_ID and "
                              "GOOGLE_OAUTH_CLIENT_SECRET (the Workspace MCP's), or pass a client JSON")
        client_id, client_secret = client["GOOGLE_OAUTH_CLIENT_ID"], client["GOOGLE_OAUTH_CLIENT_SECRET"]
    redirect = f"http://localhost:{port}/"
    state = secrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES.get(s, s) for s in scopes), "access_type": "offline",
        "prompt": "consent", "state": state})

    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            query = parse_qs(urlparse(self.path).query)
            result.update({k: v[0] for k, v in query.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Listo. Ya puedes cerrar esta pestaña.".encode())

        def log_message(self, *args):
            pass

    print(f"\nOpen this URL and approve access:\n\n{url}\n")
    webbrowser.open(url)
    server = HTTPServer(("localhost", port), Handler)
    while "code" not in result and "error" not in result:
        server.handle_request()
    server.server_close()
    if result.get("state") != state:
        raise GoogleError("OAuth state mismatch; try again")
    if "error" in result:
        raise GoogleError(f"Google login failed: {result['error']}")

    resp = httpx.post(TOKEN_URL, data={
        "code": result["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code"}, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise GoogleError(f"token exchange failed: HTTP {resp.status_code}")
    data = resp.json()
    return {"token": data["access_token"], "refresh_token": data.get("refresh_token"),
            "client_id": client_id, "client_secret": client_secret, "token_uri": TOKEN_URL,
            "scopes": scopes,
            "expiry": datetime.fromtimestamp(time.time() + data.get("expires_in", 3600),
                                             UTC).isoformat()}


def get(url: str, token: str, params: dict | None = None) -> dict:
    resp = httpx.get(url, params=params, headers={"Authorization": f"Bearer {token}"},
                     timeout=TIMEOUT)
    if resp.status_code == 403:
        raise GoogleError("HTTP 403: missing permission; run `udb mail login` with that scope")
    if resp.status_code != 200:
        raise GoogleError(f"HTTP {resp.status_code} from {urlparse(url).path.rsplit('/', 1)[-1]}")
    return resp.json()
