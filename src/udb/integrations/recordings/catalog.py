"""Class recordings: find the links in Moodle and keep a catalog.

Recordings live in each teacher's OneDrive, behind the Microsoft login. This
module only finds and tracks them (`index/recordings.json`); `download`,
`asr`, `frames` and `radar` do the rest.
"""
import html as _html
import json
import re
from datetime import date, datetime

from ...core.paths import index_dir, load_subjects, load_yaml
from ...core.text import strip_accents
from ...vault import index

LINK_RE = re.compile(r'href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
FILE_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})")
VIDEO_RE = re.compile(r"sharepoint\.com/:v:/|meetingrecap|\.mp4", re.I)
TAIL_RE = re.compile(r"\s*\|?\s*(?:reuni[oó]n|microsoft teams|grabaci[oó]n de la reuni[oó]n)"
                     r"\s*(?:\||$)", re.I)
AUTO_RE = re.compile(r"^[a-z]{3} sesion \d+$")
# Link texts that say nothing about which recording it is.
EMPTY_TITLES = ("video", "link teams", "calendario academico de la asignatura", "grabacion",
                "grabaciones", "reunion", "ver", "aqui")

LEGACY_KEYS = {"titulo": "title", "seccion": "section", "fecha": "date",
               "curso_moodle": "moodle_course", "estado": "status", "visto_en": "seen_on",
               "archivo": "file"}
LEGACY_STATUS = {"pendiente": "pending", "bajado": "downloaded", "transcrita": "transcribed"}


def config() -> dict:
    return load_yaml("recordings.yaml")


def catalog_path():
    return index_dir() / "recordings.json"


def _canonical(item: dict) -> dict:
    out = {LEGACY_KEYS.get(k, k): v for k, v in item.items()}
    out["status"] = LEGACY_STATUS.get(out.get("status"), out.get("status"))
    return out


def load() -> list[dict]:
    path = catalog_path()
    if not path.exists():
        return []
    return [_canonical(g) for g in json.loads(path.read_text(encoding="utf-8"))]


def save(items: list[dict]) -> None:
    catalog_path().write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def find(rid: str) -> dict:
    for g in load():
        if g["id"].upper() == rid.upper():
            return g
    raise KeyError(f"unknown recording: {rid}")


def update(rid: str, **fields) -> dict:
    items = load()
    for g in items:
        if g["id"].upper() == rid.upper():
            g.update(fields)
            save(items)
            return g
    raise KeyError(f"unknown recording: {rid}")


def clean(html: str) -> str:
    text = _html.unescape(TAG_RE.sub(" ", html or "")).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def shorten(title: str) -> str:
    """Drop the tail Teams and OneDrive glue to every name."""
    out = TAIL_RE.sub(" ", title)
    out = re.sub(r"[-_]\d{8}_\d{6}.*$", "", out)
    out = re.sub(r"\.(mp4|mkv|webm|mov)$", "", out, flags=re.I)
    return re.sub(r"\s*[|\-\s]+$", "", out).strip() or title.strip()


def is_poor_title(text: str) -> bool:
    """True when the title does not tell this recording from the others."""
    plain = strip_accents(text.lower()).strip(" .-|")
    return not plain or plain in EMPTY_TITLES or len(plain) < 4 or bool(AUTO_RE.match(plain))


def url_key(url: str) -> str:
    """The video's identity without query parameters (Moodle adds ?nav=, ?e=...)."""
    return strip_accents(url.split("?", 1)[0].rstrip("/").lower())


def date_in(text: str) -> str | None:
    m = FILE_DATE_RE.search(text or "")
    if not m:
        return None
    y, mo, d, h, mi, _ = m.groups()
    try:
        return datetime(int(y), int(mo), int(d), int(h), int(mi)).isoformat(" ")
    except ValueError:
        return None


def _blocks(contents: list[dict]):
    """Every piece of course HTML where a link may hide."""
    for sec in contents:
        yield clean(sec.get("name", "")), sec.get("summary", "") or ""
        for m in sec.get("modules", []):
            name = clean(m.get("name", ""))
            yield name, m.get("description", "") or ""
            for c in m.get("contents", []) or []:
                if c.get("fileurl"):
                    yield name, f'<a href="{c["fileurl"]}">{c.get("filename", "")}</a>'


def _next(items: list[dict], code: str) -> int:
    used = [int(g["id"].rsplit("-", 1)[1]) for g in items if g["id"].startswith(code + "-")]
    return max(used, default=0) + 1


def _title(text: str, section: str, code: str, n: int) -> str:
    short = shorten(text)
    if not is_poor_title(short):
        return short[:120]
    if not is_poor_title(section):
        return f"{code} - {shorten(section)}"[:120]
    return f"{code} sesion {n}"


def discover(subject: str | None = None) -> list[dict]:
    """Walk every course in Moodle and add each recording link found."""
    from ..moodle import client

    by_course = {int(s["moodle_course_id"]): s["code"] for s in load_subjects()
                 if s.get("moodle_course_id")}
    with client.connect() as api:
        items = load()
        seen = {url_key(g["url"]): g for g in items}
        for course_id, code in by_course.items():
            if subject and code != subject.upper():
                continue
            new = 0
            for where, block in _blocks(api.course_contents(course_id)):
                for href, label in LINK_RE.findall(block):
                    href = _html.unescape(href).strip()
                    if not VIDEO_RE.search(href):
                        continue
                    text = clean(label)
                    key = url_key(href)
                    if key in seen:
                        prev, better = seen[key], shorten(text)
                        if is_poor_title(prev["title"]) and not is_poor_title(better):
                            prev["title"] = better[:120]
                            prev["date"] = prev.get("date") or date_in(text)
                        continue
                    new += 1
                    items.append({
                        "id": f"{code}-{_next(items, code):03d}", "subject": code,
                        "title": _title(text, where, code, new), "section": where[:80],
                        "url": href, "date": date_in(text) or date_in(href),
                        "moodle_course": course_id, "status": "pending", "source_id": None,
                        "seen_on": date.today().isoformat()})
                    seen[key] = items[-1]
        save(items)
        return items


def board() -> list[dict]:
    """State of every recording: downloaded, transcribed, frames extracted."""
    from .frames import frame_index

    rows = []
    for g in load():
        sid = g.get("source_id")
        rows.append({
            "id": g["id"], "subject": g["subject"], "title": g["title"], "date": g.get("date"),
            "status": g["status"], "source_id": sid,
            "transcribed": bool(sid and index.transcript_file(g["subject"], sid).exists()),
            "frames": len(frame_index(g["subject"], sid)) if sid else 0})
    return rows
