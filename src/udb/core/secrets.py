"""Every credential udb needs, packed into one environment variable for the cloud.

Locally, secrets are files under the secrets folder (`~/.config/udb`, mode 600)
plus the Google Workspace MCP's own folder. `udb cloud secrets` packs them into
one base64 string; paste it once as `UDB_SECRETS` in the cloud environment.
Each cloud session unpacks it back into the same files (`restore`), so every
part of udb, and the Google Workspace MCP, finds its credentials as at home.
Run the export again only when you add an account or renew a token.
"""
import base64
import json
import os
from pathlib import Path

from . import settings

BUNDLE_ENV = "UDB_SECRETS"
WORKSPACE_DIR = Path("~/.google_workspace_mcp/credentials").expanduser()
WORKSPACE_ENV = Path("~/.config/workspace-mcp/env").expanduser()
CLIENT_KEYS = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET")


def secrets_dir() -> Path:
    try:
        return settings.get().secrets
    except settings.HomeNotFound:
        return Path(os.environ.get("UDB_SECRETS_DIR") or "~/.config/udb").expanduser()


def write_private(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(text, encoding="utf-8")
    return path


def _env_file(path: Path) -> dict[str, str]:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and key and not key.startswith("#"):
                out[key.strip()] = value.strip().strip("'\"")
    return out


def google_client() -> dict[str, str] | None:
    """The Google OAuth app (client id and secret) shared with the Workspace MCP."""
    found = {k: os.environ[k] for k in CLIENT_KEYS if os.environ.get(k)}
    if len(found) < 2:
        found = {k: v for k, v in _env_file(WORKSPACE_ENV).items() if k in CLIENT_KEYS}
    if len(found) < 2:
        found = {k: v for k, v in _env_file(secrets_dir() / "google-client.env").items()
                 if k in CLIENT_KEYS}
    return found if len(found) == 2 else None


def export() -> tuple[str, list[str]]:
    """(bundle, names included). Never print the bundle anywhere but to the user."""
    files: dict[str, str] = {}
    folder = secrets_dir()
    if folder.exists():
        for path in folder.iterdir():
            if path.is_file():
                files[f"udb/{path.name}"] = path.read_text(encoding="utf-8")
    if WORKSPACE_DIR.exists():
        for path in WORKSPACE_DIR.glob("*.json"):
            if "@" in path.name:
                files[f"workspace/{path.name}"] = path.read_text(encoding="utf-8")
    client = google_client()
    if client:
        files["udb/google-client.env"] = "".join(f"{k}={v}\n" for k, v in client.items())
    raw = json.dumps({"version": 1, "files": files}).encode()
    return base64.b64encode(raw).decode(), sorted(files)


def restore(bundle: str | None = None) -> list[str]:
    """Unpack UDB_SECRETS into the secret files. Existing newer files are kept."""
    bundle = bundle or os.environ.get(BUNDLE_ENV)
    if not bundle:
        return []
    data = json.loads(base64.b64decode(bundle))
    written = []
    for name, text in data.get("files", {}).items():
        area, _, filename = name.partition("/")
        base = secrets_dir() if area == "udb" else WORKSPACE_DIR if area == "workspace" else None
        if base is None or "/" in filename or filename.startswith("."):
            continue
        target = base / filename
        if not target.exists():
            write_private(target, text)
            written.append(name)
    return written
