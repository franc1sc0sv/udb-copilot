"""The one Jinja environment every page uses."""
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def env() -> Environment:
    from udb.rendering import dates_es

    environment = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                              autoescape=select_autoescape(["html", "j2"]))
    environment.filters.update(dates_es.FILTERS)
    return environment
