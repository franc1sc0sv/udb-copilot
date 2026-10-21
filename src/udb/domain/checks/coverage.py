"""Does the class note cover every topic the material opens, and use all of it?

The citation check answers "is what is written true?". This answers the other
half: "is everything written that should be?". Topics come from the
structure of the material itself (headings and bold labels in the HTML pages)
and from the syllabus lines assigned to the class.

Citations v3 adds the material itself: every source assigned to the class must
be cited at least once (`source-not-used`), and pages of a cited source that no
paragraph uses are listed as ranges (`pages-not-covered`). Pages under
MIN_PAGE_WORDS (titles, agendas, blank slides) do not count.
"""
import re
from pathlib import Path

from udb.config.paths import relative, subject_codes, subject_dir
from udb.domain.notes import anchors
from udb.domain.notes import document as notes
from udb.domain.notes.findings import Finding
from udb.domain.sources import registry
from udb.domain.text.normalize import normalize

MARKS = ["h1", "h2", "h3", "h4", "h5", "strong", "b"]

# Navigation and template labels of the course site, not topics.
NOISE = re.compile(
    r"^(menu|guia de uso|unidad \d+|clase \d+\s*\|?|nota:?|introduccion de la"
    r" asignatura|inicio|anterior|siguiente|creditos|bibliografia|referencias)")

# Spanish words that carry no topic: they cannot decide coverage.
STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas", "y",
    "o", "en", "con", "para", "por", "a", "al", "su", "sus", "se", "que",
    "es", "son", "entre", "sobre", "como", "mas", "menos",
    # Presentation labels: "Ejemplo ilustrativo" says how, not what.
    "ejemplo", "ejemplos", "ejercicio", "ejercicios", "ilustracion",
    "ilustrativo", "ilustrativa", "utilizando", "usando", "aplicando",
    "observacion", "nota", "resumen", "tabla", "figura", "siguiente",
    "anterior", "veamos", "vamos", "haciendo", "uso", "mediante",
}

MIN_PAGE_WORDS = 15
COURSE_KINDS = {"course", "exercise"}
THRESHOLD = 0.6
MIN_KEYWORDS = 2
CLASS_LINE_RE = re.compile(r"^\s*[*_]*\s*Clase\s+(\d+)\b", re.IGNORECASE)
BULLET_RE = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")


def keywords(topic: str) -> list[str]:
    clean = re.sub(r"^\s*\d+(\.\d+)*\.?\s*", "", normalize(topic))
    return [w for w in re.findall(r"[a-z0-9]+", clean) if w not in STOPWORDS and len(w) > 2]


def material_topics(code: str, number: int) -> list[str]:
    from bs4 import BeautifulSoup

    rec = next((r for r in registry.read_all(code)
                if r.get("class") == number and not r.get("superseded_by")), None)
    if rec is None:
        return []
    path = registry.source_file(code, rec["id"])
    if not path.exists() or path.suffix.lower() not in {".html", ".htm"}:
        return []
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    seen: dict[str, str] = {}
    for node in soup.find_all(MARKS):
        text = " ".join(node.get_text(" ", strip=True).split())
        if not text or len(text) > 90:
            continue
        norm = normalize(text)
        if NOISE.match(norm) or len(keywords(text)) < MIN_KEYWORDS:
            continue
        seen.setdefault(norm, text)
    return list(seen.values())


def syllabus_topics(code: str, number: int) -> list[str]:
    path = subject_dir(code) / "syllabus.md"
    if not path.exists():
        return []
    topics: list[str] = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        m = CLASS_LINE_RE.match(line.strip("*_ "))
        if m:
            inside = int(m.group(1)) == number
            continue
        bullet = BULLET_RE.match(line) if inside else None
        if bullet and len(keywords(bullet.group(1))) >= MIN_KEYWORDS:
            topics.append(bullet.group(1))
    return topics


def covered(topic: str, note_text: str) -> bool:
    keys = keywords(topic)
    if len(keys) < MIN_KEYWORDS:
        return True
    return sum(1 for k in keys if k in note_text) / len(keys) >= THRESHOLD


def check_class(code: str, number: int, note_path: Path) -> list[Finding]:
    if notes.is_stub(note_path):
        return []
    text = normalize(note_path.read_text(encoding="utf-8", errors="replace"))
    rel = relative(note_path)
    from_material = material_topics(code, number)
    findings = [Finding(rel, 1, "topic-not-covered",
                        f'the material opens "{t}" and the note does not cover it')
                for t in from_material if not covered(t, text)]
    seen = {normalize(t) for t in from_material}
    findings += [Finding(rel, 1, "topic-not-covered",
                         f'the syllabus assigns "{t}" to this class and the note does not cover it')
                 for t in syllabus_topics(code, number)
                 if normalize(t) not in seen and not covered(t, text)]
    return findings


def _ranges(numbers: list[int]) -> str:
    out, run = [], []
    for n in sorted(numbers):
        if run and n == run[-1] + 1:
            run.append(n)
        else:
            if run:
                out.append(f"{run[0]}–{run[-1]}" if len(run) > 1 else str(run[0]))
            run = [n]
    if run:
        out.append(f"{run[0]}–{run[-1]}" if len(run) > 1 else str(run[0]))
    return ", ".join(out)


def _citable_pages(code: str, source_id: str) -> list[int]:
    from udb.domain.sources import index
    return [p["page"] for p in index.load_pages(code, source_id)
            if len((p.get("text") or "").split()) >= MIN_PAGE_WORDS]


def _cited(note_path: Path) -> dict[str, set]:
    """source id -> pages cited (an empty set for time or frame anchors)."""
    definitions, _ = anchors.parse(note_path.read_text(encoding="utf-8", errors="replace"))
    out: dict[str, set] = {}
    for a in definitions.values():
        if a.source_id and not a.error:
            pages = out.setdefault(a.source_id, set())
            if a.fields.get("page", "").isdigit():
                pages.add(int(a.fields["page"]))
    return out


def material_coverage(code: str, number: int, note_path: Path) -> dict:
    """How much of the class material the note uses: per source and overall."""
    from udb.domain.sources import index
    from udb.domain.study import classes
    cited = _cited(note_path) if note_path.exists() else {}
    per_source, total, used = [], 0, 0
    for rec in classes.sources_for(code, number):
        pages = _citable_pages(code, rec["id"])
        timed = bool(index.load_segments(code, rec["id"]))
        if not pages and not timed:
            continue  # nothing readable to cite (unsupported file, empty page)
        hit = cited.get(rec["id"])
        if pages:
            covered = sorted(set(pages) & (hit or set()))
            total += len(pages)
            used += len(covered)
        else:
            covered = []
        per_source.append({"id": rec["id"], "title": rec.get("title"), "kind": rec.get("kind"),
                           "cited": hit is not None, "pages": pages, "covered": covered,
                           "timed": timed})
    return {"sources": per_source,
            "percent": round(100 * used / total) if total else None}


def check_material(code: str, number: int, note_path: Path) -> list[Finding]:
    if notes.is_stub(note_path):
        return []
    rel = relative(note_path)
    out = []
    for s in material_coverage(code, number, note_path)["sources"]:
        label = f"{s['id']} ({(s['title'] or '')[:50]})"
        if not s["cited"]:
            out.append(Finding(rel, 1, "source-not-used",
                               f"{label} belongs to this class and is never cited",
                               level="error" if s["kind"] in COURSE_KINDS else "warning"))
            continue
        missing = [p for p in s["pages"] if p not in s["covered"]]
        if missing and s["covered"]:
            out.append(Finding(rel, 1, "pages-not-covered",
                               f"{label}: pages {_ranges(missing)} are not used by any paragraph",
                               level="warning"))
    return out


def check_subject(code: str | None = None) -> list[Finding]:
    if code is None:
        return [f for c in subject_codes() for f in check_subject(c)]
    base = subject_dir(code) / "classes"
    findings: list[Finding] = []
    if not base.exists():
        return findings
    for folder in sorted(base.iterdir()):
        note = folder / "class.md"
        m = re.match(r"(\d+)", folder.name)
        if note.exists() and m:
            findings.extend(check_class(code, int(m.group(1)), note))
            findings.extend(check_material(code, int(m.group(1)), note))
    return findings


def syllabus_report(code: str) -> dict:
    """Syllabus topics with no note that covers them."""
    from udb.domain.checks.citations import note_paths

    syllabus = subject_dir(code) / "syllabus.md"
    if not syllabus.exists():
        return {"message": f"no syllabus.md in vault/{code}"}
    topics = [ln.strip("-*# ").strip() for ln in syllabus.read_text(encoding="utf-8").splitlines()
              if ln.strip().startswith(("-", "*", "#"))]
    text = normalize(" ".join(p.read_text(encoding="utf-8", errors="replace")
                              for p in note_paths(code)))
    missing = [t for t in topics if t and not covered(t, text)]
    return {"total": len(topics), "covered": len(topics) - len(missing), "missing": missing}
