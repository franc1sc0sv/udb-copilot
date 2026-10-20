"""Plain-language checks: short sentences, readable text, every required section."""
import re
from pathlib import Path

from ..core import lang, notes
from ..core.findings import Finding
from ..core.paths import get_subject, load_yaml, relative, subject_of_path
from ..core.text import count_syllables_es, normalize, split_sentences

MAX_WORDS = 25
WARN_WORDS = 20
MIN_READABILITY = 65.0
MAX_PASSIVE = 0.10

LINK_RE = re.compile(r"\[\[([^\]]+)\]\]|\[([^\]]+)\]\(")
DIAGRAM_RE = re.compile(r"```mermaid|\.excalidraw|<svg")
CITE_RE = re.compile(r"\[\^[^\]]+\]|\(m[ée]todo paso \d+\)")
MATH_RE = re.compile(r"\\\[.*?\\\]|\\\(.*?\\\)|\$\$.*?\$\$|\$[^$\n]+?\$", re.DOTALL)


def prose_only(text: str) -> str:
    """The text a reader actually reads.

    Citations are metadata: removed after sentence splitting, a period followed
    by `[^c3]` would glue two short sentences into one long one. Formulas are
    not prose and would make the text look easier than it is.
    """
    return MATH_RE.sub(" ", CITE_RE.sub("", text))


def szigriszt(text: str) -> float:
    """Szigriszt-Pazos readability for Spanish (higher is easier)."""
    sentences = split_sentences(text)
    words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", text)
    if not sentences or not words:
        return 100.0
    syllables = sum(count_syllables_es(w) for w in words)
    return 206.835 - 62.3 * (syllables / len(words)) - (len(words) / len(sentences))


def load_jargon() -> set[str]:
    data = load_yaml("jargon.yaml")
    return {normalize(t) for t in data.get("terms", data.get("terminos", []))}


def subject_kind(path: Path) -> str:
    code = subject_of_path(path)
    try:
        return get_subject(code).get("kind", "general") if code else "general"
    except KeyError:
        return "general"


def wants_sections(path: Path) -> bool:
    return path.name == "class.md" or "concepts" in {p.lower() for p in path.parts}


def _skip(section: str) -> bool:
    return section.strip().lower() in {lang.section("questions").lower(),
                                       lang.section("code").lower()}


def check_sentences(note: notes.Note) -> list[Finding]:
    findings = []
    for block in note.blocks:
        if block.is_table or _skip(block.section):
            continue
        for sentence in (s for line in block.lines for s in split_sentences(prose_only(line))):
            count = len(sentence.split())
            if count > MAX_WORDS:
                findings.append(Finding(note.path, block.start_line, "long-sentence",
                                        f'{count} words (max {MAX_WORDS}): "{sentence[:70]}..."'))
            elif count > WARN_WORDS:
                findings.append(Finding(note.path, block.start_line, "long-sentence",
                                        f"{count} words (recommended {WARN_WORDS})",
                                        level="warning"))
    return findings


def check_summary(note: notes.Note) -> list[Finding]:
    title = lang.section("summary")
    if not note.has_section(title):
        return [Finding(note.path, 1, "missing-summary", f"missing section '## {title}'")]
    text = re.sub(r"\[\^[^\]]+\]", "", note.section_text(title)).strip()
    if not text:
        return [Finding(note.path, 1, "missing-summary", f"'## {title}' is empty")]
    if len(split_sentences(text)) > 1:
        return [Finding(note.path, 1, "missing-summary", f"'## {title}' must be one sentence")]
    return []


def check_sections(note: notes.Note, kind: str) -> list[Finding]:
    return [Finding(note.path, 1, "missing-section", f"missing section '## {s}'")
            for s in lang.sections_for(kind) if not note.has_section(s)]


def check_example(note: notes.Note) -> list[Finding]:
    title = lang.section("example")
    if note.has_section(title) and not note.section_text(title).strip():
        return [Finding(note.path, 1, "empty-example", f"'## {title}' is empty")]
    return []


def check_diagram(note: notes.Note, raw: str) -> list[Finding]:
    if DIAGRAM_RE.search(raw):
        return []
    return [Finding(note.path, 1, "no-diagram", "the note has no diagram (mermaid, svg or excalidraw)")]


def check_readability(note: notes.Note) -> list[Finding]:
    code = lang.section("code").lower()
    body = prose_only(" ".join(b.text for b in note.blocks
                               if not b.is_table and b.section.strip().lower() != code))
    if len(body.split()) < 40:
        return []
    score = szigriszt(body)
    if score < MIN_READABILITY:
        return [Finding(note.path, 1, "hard-to-read",
                        f"Szigriszt index {score:.0f}; minimum is {MIN_READABILITY:.0f}. "
                        "Use shorter sentences and words.")]
    return []


def check_jargon(note: notes.Note, jargon: set[str]) -> list[Finding]:
    findings, seen = [], set()
    related = lang.section("related").lower()
    for block in note.blocks:
        linked = {normalize(m.group(1) or m.group(2) or "") for m in LINK_RE.finditer(block.text)}
        for term in jargon:
            if term in seen or term not in normalize(block.text):
                continue
            seen.add(term)
            if not any(term in link for link in linked) and block.section.strip().lower() != related:
                findings.append(Finding(note.path, block.start_line, "undefined-term",
                                        f"'{term}' first appears without a link or definition"))
    return findings


def check_passive(note: notes.Note) -> list[Finding]:
    sentences = split_sentences(" ".join(b.text for b in note.blocks))
    if len(sentences) < 8:
        return []
    passive_re = re.compile(lang.get()["passive"], re.IGNORECASE)
    ratio = sum(1 for s in sentences if passive_re.search(s)) / len(sentences)
    if ratio > MAX_PASSIVE:
        return [Finding(note.path, 1, "passive-voice",
                        f"{round(100 * ratio)}% of sentences are passive; use active voice",
                        level="warning")]
    return []


def check_note(path: Path) -> list[Finding]:
    if notes.is_stub(path):
        return []
    raw = path.read_text(encoding="utf-8")
    note = notes.parse(relative(path), raw)
    if str(note.front.get("clarity", "")).lower() == "free":
        return []
    findings = check_sentences(note) + check_readability(note) + check_passive(note)
    findings += check_jargon(note, load_jargon())
    if wants_sections(path):
        findings += check_summary(note) + check_sections(note, subject_kind(path))
        findings += check_example(note) + check_diagram(note, raw)
    return findings


def check_paths(paths: list[Path]) -> list[Finding]:
    return [f for p in paths if p.exists() and p.suffix == ".md" for f in check_note(p)]
