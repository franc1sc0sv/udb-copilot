import base64
import json

from udb.core import secrets


def test_bundle_roundtrip(home, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "me@gmail.com.json").write_text('{"refresh_token": "r"}')
    env_file = tmp_path / "workspace-env"
    env_file.write_text("GOOGLE_OAUTH_CLIENT_ID=cid\nGOOGLE_OAUTH_CLIENT_SECRET='sec'\n")
    monkeypatch.setattr(secrets, "WORKSPACE_DIR", workspace)
    monkeypatch.setattr(secrets, "WORKSPACE_ENV", env_file)
    monkeypatch.setattr(secrets, "LEGACY_MOODLE", tmp_path / "none")
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    secrets.write_private(secrets.secrets_dir() / "moodle-token", "tok")

    assert secrets.google_client() == {"GOOGLE_OAUTH_CLIENT_ID": "cid",
                                       "GOOGLE_OAUTH_CLIENT_SECRET": "sec"}
    bundle, names = secrets.export()
    assert set(names) == {"udb/moodle-token", "workspace/me@gmail.com.json",
                          "udb/google-client.env"}
    assert json.loads(base64.b64decode(bundle))["version"] == 1

    # A fresh cloud container: nothing on disk, only the variable.
    for path in [*secrets.secrets_dir().iterdir(), *workspace.iterdir()]:
        path.unlink()
    monkeypatch.setattr(secrets, "WORKSPACE_ENV", tmp_path / "missing")
    monkeypatch.setenv("UDB_SECRETS", bundle)
    restored = secrets.restore()
    assert len(restored) == 3
    assert (secrets.secrets_dir() / "moodle-token").read_text() == "tok"
    assert (workspace / "me@gmail.com.json").stat().st_mode & 0o777 == 0o600
    assert secrets.google_client()["GOOGLE_OAUTH_CLIENT_ID"] == "cid"
    assert secrets.restore() == []  # idempotent


def test_restore_rejects_path_tricks(home, monkeypatch, tmp_path):
    raw = {"version": 1, "files": {"udb/../evil": "x", "other/file": "x", "udb/.hidden": "x"}}
    monkeypatch.setenv("UDB_SECRETS", base64.b64encode(json.dumps(raw).encode()).decode())
    assert secrets.restore() == []
