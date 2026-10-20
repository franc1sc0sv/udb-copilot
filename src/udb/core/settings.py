"""Where the user's data lives and how this installation is configured.

The engine is installed once; the data (vault, config, tasks) lives in a
separate folder, usually a private git repo. That folder is marked by a
`udb.yaml` file at its root. Commands find it in this order:

1. the `UDB_HOME` environment variable;
2. the nearest `udb.yaml` walking up from the current directory.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

MARKER = "udb.yaml"

DEFAULTS: dict = {
    "schema": 1,
    "timezone": "America/El_Salvador",
    "language": "es",
    "institution": {
        "name": "Universidad Don Bosco",
        "moodle_url": "https://www.udbvirtual.edu.sv/auladigital",
        "moodle_service": "moodle_mobile_app",
        "guard_domains": ["udbvirtual.edu.sv"],
    },
    "paths": {"vault": "vault", "config": "config", "index": "index", "cycles": "cycles"},
    "secrets_dir": "~/.config/udb",
    "rate_limit_seconds": 1.0,
}


class HomeNotFound(RuntimeError):
    pass


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def find_home(start: Path | None = None) -> Path:
    env = os.environ.get("UDB_HOME")
    if env:
        path = Path(env).expanduser().resolve()
        if not (path / MARKER).exists():
            raise HomeNotFound(f"UDB_HOME={path} has no {MARKER}. Run: udb init {path}")
        return path
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / MARKER).exists():
            return folder
    raise HomeNotFound(
        f"no {MARKER} found in {here} or its parents. "
        "Run `udb init <folder>` or set UDB_HOME.")


@dataclass(frozen=True)
class Settings:
    home: Path
    data: dict = field(default_factory=dict)

    def _path(self, key: str) -> Path:
        return (self.home / self.data["paths"][key]).resolve()

    @property
    def vault(self) -> Path:
        return self._path("vault")

    @property
    def config(self) -> Path:
        return self._path("config")

    @property
    def index(self) -> Path:
        return self._path("index")

    @property
    def cycles(self) -> Path:
        return self._path("cycles")

    @property
    def secrets(self) -> Path:
        return Path(os.environ.get("UDB_SECRETS_DIR") or self.data["secrets_dir"]).expanduser()

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.data["timezone"])

    @property
    def language(self) -> str:
        return self.data["language"]

    @property
    def institution(self) -> dict:
        return self.data["institution"]


def load(home: Path) -> Settings:
    raw = yaml.safe_load((home / MARKER).read_text(encoding="utf-8")) or {}
    return Settings(home=home, data=_merge(DEFAULTS, raw))


@lru_cache(maxsize=1)
def get() -> Settings:
    return load(find_home())


def reset() -> None:
    """Forget the cached settings (tests and `udb init` switch homes)."""
    get.cache_clear()
