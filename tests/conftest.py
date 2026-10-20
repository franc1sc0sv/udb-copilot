import shutil
from pathlib import Path

import pytest

from udb.core import settings

FIXTURE = Path(__file__).parent / "fixtures" / "home"


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """A fresh copy of the demo vault, active as UDB_HOME."""
    target = tmp_path / "home"
    shutil.copytree(FIXTURE, target)
    monkeypatch.setenv("UDB_HOME", str(target))
    monkeypatch.setenv("UDB_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.delenv("MOODLE_TOKEN", raising=False)
    settings.reset()
    yield target
    settings.reset()


@pytest.fixture
def indexed(home) -> Path:
    from udb.vault import index
    index.reindex_all()
    return home
