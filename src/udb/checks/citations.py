"""Citation checks: every anchor points at text that really is in the source.

What is verified: the source is registered and current, and the quote is in
the derived text at the stated page, time window, board still or snapshot.
What is not: that the paragraph says what the quote supports. `weak-support`
flags the cases where the two share almost no words.

Citations v3 (docs/citations-v3.md): the unit is the paragraph. One reference at
the end of a paragraph that comes from one source, quoting a passage (1 to 3
sentences) that backs the whole paragraph. The same anchor twice in a paragraph
is `repeated-citation`, and `udb verify --fix` keeps only the last one.
"""
import re
from pathlib import Path

from ..core import anchors, lang, notes
from ..core.findings import Finding
from ..core.paths import relative, subject_codes, subject_dir, subject_of_path
from ..core.text import contains, count_occurrences, normalize
from ..vault import index, registry

MODEL_BUDGET = 0.30
WINDOW_SLACK = 20.0
MIN_QUOTE_WORDS = 8
MIN_QUOTE_CHARS = 40
SAME_SOURCE_MAX = 2  # distinct anchors of one source in a paragraph before suggesting a passage
# Claude's own voice. `model` carries claims (with basis=, inside the 30 % budget);
# examples and analogies adapted to the student need no citation and are outside it,
# because the box tells the reader they are not the teacher's.
FREE_CALLOUTS = {"example", "ejemplo", "analogy", "analogia", "analogía"}
AMBIGUOUS_AFTER = 3


def locate(code: str, source_id: str, quote: str) -> list[int]:
    """Pages where the quote is, including quotes that run across a page break."""
    pages = index.load_pages(code, source_id)
    found = [p["page"] for p in pages if contains(p["text"], quote)]
    if found:
        return found
    return [a["page"] for a, b in zip(pages, pages[1:], strict=False)
            if contains(a["text"] + " " + b["text"], quote)]


def quote_in_pages(code: str, source_id: str, quote: str, page: int | None) -> bool:
    found = locate(code, source_id, quote)
    return bool(found) if page is None else page in found


def _window_text(segments: list[dict], start: float, end: float) -> str:
    return " ".join(s.get("text", "") for s in segments
                    if s.get("end", 0) >= start - WINDOW_SLACK and s.get("start", 0) <= end + WINDOW_SLACK)


def quote_in_window(code: str, source_id: str, quote: str, window: tuple[float, float]) -> bool:
    segments = index.load_segments(code, source_id)
    return bool(segments) and contains(_window_text(segments, *window), quote)


def locate_in_transcript(code: str, source_id: str, quote: str) -> tuple[float, float] | None:
    segments = index.load_segments(code, source_id)
    for i in range(len(segments)):
        span = segments[i:i + 4]
        if contains(" ".join(s.get("text", "") for s in span), quote):
            return float(span[0]["start"]), float(span[-1]["end"])
    return None


def quote_in_snapshot(code: str, source_id: str, quote: str) -> bool:
    if index.load_pages(code, source_id):
        return quote_in_pages(code, source_id, quote, None)
    try:
        path = registry.source_file(code, source_id)
    except KeyError:
        return False
    return path.exists() and contains(path.read_text(encoding="utf-8", errors="replace"), quote)


def occurrences(code: str, source_id: str, quote: str) -> int:
    return sum(count_occurrences(p["text"], quote) for p in index.load_pages(code, source_id))


def check_anchor(code: str, anchor: anchors.Anchor, path: str) -> list[Finding]:
    if anchor.error:
        head, _, detail = anchor.error.partition(": ")
        return [Finding(path, anchor.line, head, detail or anchor.error)]
    if anchor.is_model:
        basis = anchor.fields["basis"]
        if not registry.lookup(basis):
            return [Finding(path, anchor.line, "unjustified-model-claim",
                            f"basis={basis} is not in the registry")]
        return []

    source_id = anchor.source_id
    owner = registry.subject_of(source_id)
    record = registry.get(owner, source_id)
    if not record:
        return [Finding(path, anchor.line, "unknown-source",
                        f"{source_id} is not in the {owner} registry")]
    if record.get("superseded_by"):
        return [Finding(path, anchor.line, "superseded-source",
                        f"{source_id} was replaced by {record['superseded_by']}; cite the new one")]

    quote = anchor.quote
    out: list[Finding] = []
    if "frame" in anchor.fields:
        return out + _check_frame(owner, source_id, anchor, path)

    if "t" in anchor.fields:
        window = anchors.parse_window(anchor.fields["t"])
        if not window:
            return out + [Finding(path, anchor.line, "malformed-anchor",
                                  f"t={anchor.fields['t']} is not HH:MM:SS-HH:MM:SS")]
        if not quote_in_window(owner, source_id, quote, window):
            moved = locate_in_transcript(owner, source_id, quote)
            if moved:
                new = f"{anchors.hhmmss(moved[0])}-{anchors.hhmmss(moved[1])}"
                out.append(Finding(path, anchor.line, "quote-moved",
                                   f"{source_id}: the quote is at t={new}, not t={anchor.fields['t']}",
                                   level="warning",
                                   fix={"old": f"t={anchor.fields['t']}", "new": f"t={new}"}))
            else:
                out.append(Finding(path, anchor.line, "quote-not-in-window",
                                   f'{source_id} t={anchor.fields["t"]} does not contain: "{quote}"'))
        return out

    if "url" in anchor.fields and "page" not in anchor.fields:
        if not quote_in_snapshot(owner, source_id, quote):
            out.append(Finding(path, anchor.line, "quote-not-in-snapshot",
                               f'the saved copy of {source_id} does not contain: "{quote}"'))
        return out

    raw_page = anchor.fields.get("page", "")
    page = int(raw_page) if raw_page.isdigit() else None
    found = locate(owner, source_id, quote)
    if not found:
        where = f"p.{page}" if page else "the document"
        out.append(Finding(path, anchor.line, "quote-not-found",
                           f'{source_id} {where} does not contain: "{quote}"'))
    elif page is not None and page not in found:
        # The text is there but on another page: the source was re-extracted (HTML now
        # splits by section, scanned pages got OCR). `udb verify --fix` updates it.
        new = min(found, key=lambda p: abs(p - page))
        out.append(Finding(path, anchor.line, "quote-moved",
                           f"{source_id}: the quote is on page {new}, not {page}", level="warning",
                           fix={"old": f"page={page}", "new": f"page={new}"}))
    elif page is None and occurrences(owner, source_id, quote) > AMBIGUOUS_AFTER:
        out.append(Finding(path, anchor.line, "ambiguous-quote",
                           f'"{quote}" appears in many places of {source_id}; add page=',
                           level="warning"))
    return out


def _check_frame(code: str, source_id: str, anchor: anchors.Anchor, path: str) -> list[Finding]:
    """A board still: the quote must be in the text read from that still."""
    from ..integrations.recordings.frames import frame_index
    n = int(anchor.fields["frame"])
    frame = next((f for f in frame_index(code, source_id) if int(f["n"]) == n), None)
    if frame is None:
        return [Finding(path, anchor.line, "quote-not-found", f"{source_id} has no frame {n}")]
    board, _, figure = (frame.get("text") or "").partition("Figura:")
    if contains(board, anchor.quote):
        return []
    if contains(figure, anchor.quote):
        # The model's description of a drawing is not on the board: never quotable.
        return [Finding(path, anchor.line, "figure-description-quoted",
                        f"{source_id} frame {n}: that text is the automatic description of a "
                        "drawing, not something on the board; describe it in your own words "
                        "in a > [!model] block instead")]
    return [Finding(path, anchor.line, "quote-not-found",
                    f'{source_id} frame {n} does not contain: "{anchor.quote}"')]


MATH_RE = re.compile(r"\\\[.*?\\\]|\\\(.*?\\\)|\$\$.*?\$\$|\$[^$\n]+?\$", re.DOTALL)
REF_SPLIT_RE = re.compile(r"\[\^([A-Za-z0-9_-]+)\]")


def _stems(text: str) -> set[str]:
    """Five-letter stems of the prose words (formulas removed)."""
    prose = MATH_RE.sub(" ", text)
    return {w[:5] for w in re.findall(r"[a-z]{5,}", normalize(prose))}


def _prose(text: str) -> str:
    return REF_SPLIT_RE.sub(" ", text)


def check_support(note: notes.Note, definitions: dict[str, anchors.Anchor]) -> list[Finding]:
    """A reference whose passage shares no word stem with its paragraph: probably the
    wrong quote. The whole paragraph counts (v2 compared one sentence, which pushed
    writers to cite every sentence); formulas are ignored on both sides."""
    out = []
    for block in note.blocks:
        claim = _stems(_prose(block.text))
        for key in dict.fromkeys(block.refs):
            anchor = definitions.get(key)
            if not anchor or anchor.is_model or anchor.error:
                continue
            quote = _stems(anchor.quote)
            if len(claim) >= 4 and len(quote) >= 4 and not claim & quote:
                out.append(Finding(note.path, block.start_line, "weak-support",
                                   f"[^{key}] shares no word with its paragraph: "
                                   f'"{_prose(block.text).strip()[:60]}"', level="warning"))
    return out


def check_density(note: notes.Note, definitions: dict[str, anchors.Anchor]) -> list[Finding]:
    """The paragraph rule: one anchor per source per paragraph."""
    out = []
    for block in note.blocks:
        seen: dict[str, int] = {}
        for line in block.lines:
            for key in REF_SPLIT_RE.findall(line):
                seen.setdefault(key, 0)
                seen[key] += 1
        for i, line in enumerate(block.lines):
            for key in REF_SPLIT_RE.findall(line):
                if seen[key] > 1:
                    # Not the last use in the paragraph: drop it.
                    seen[key] -= 1
                    out.append(Finding(note.path, block.start_line + i, "repeated-citation",
                                       f"[^{key}] already backs this paragraph; keep one, "
                                       "at its end", level="warning",
                                       fix={"old": f"[^{key}]", "new": ""}))
        by_source: dict[str, set] = {}
        for key in set(block.refs):
            a = definitions.get(key)
            if a and a.source_id:
                by_source.setdefault(a.source_id, set()).add(key)
        for source_id, keys in by_source.items():
            if len(keys) > SAME_SOURCE_MAX:
                out.append(Finding(note.path, block.start_line, "many-citations",
                                   f"{len(keys)} anchors of {source_id} in one paragraph; quote "
                                   "one passage (1-3 sentences) that backs it all",
                                   level="warning"))
    return out


def check_trivial(text: str, path: str, definitions: dict[str, anchors.Anchor]) -> list[Finding]:
    """Short quotes prove that words exist, not that a paragraph is faithful. A short
    quote is fine when the note shows it literally ("..."), as a definition."""
    out = []
    body = "\n".join(ln for ln in text.splitlines() if not anchors.DEF_RE.match(ln.strip()))
    shown = [normalize(m) for m in re.findall(r'["“«]([^"”»\n]{2,200})["”»]', _prose(body))]
    for anchor in definitions.values():
        q = anchor.quote
        if anchor.is_model or anchor.error or not q:
            continue
        if len(q.split()) >= MIN_QUOTE_WORDS or len(q) >= MIN_QUOTE_CHARS:
            continue
        if any(normalize(q) in m or m in normalize(q) for m in shown if len(m) > 3):
            continue
        out.append(Finding(path, anchor.line, "trivial-quote",
                           f'quote "{q}" is too short to back a paragraph; quote the passage '
                           "(1-3 sentences) the paragraph explains", level="warning"))
    return out


def check_coverage(note: notes.Note, mode: str) -> list[Finding]:
    if mode == "free":
        return []
    table = lang.get()
    exempt = set(table["exempt_always"])
    if mode == "normal":
        exempt |= set(table["exempt_normal"])
    section_level = set(table["section_level"])
    findings = []
    model_words = claim_words = 0
    by_section: dict[str, list[notes.Block]] = {}
    for block in note.blocks:
        section = block.section.strip().lower()
        if section in exempt or block.is_table or block.callout_kind in FREE_CALLOUTS:
            continue
        words = len(block.text.split())
        claim_words += words
        if block.callout_kind == "model":
            model_words += words
        if section in section_level:
            by_section.setdefault(section, []).append(block)
            continue
        if not block.refs:
            findings.append(Finding(note.path, block.start_line, "uncited-paragraph",
                                    f'no citation: "{block.lines[0].strip()[:70]}"'))
    for section, blocks in by_section.items():
        if not any(b.refs for b in blocks):
            findings.append(Finding(note.path, blocks[0].start_line, "uncited-section",
                                    f"section '{section}' has no citation at all"))
    if claim_words and model_words / claim_words > MODEL_BUDGET:
        pct = round(100 * model_words / claim_words)
        findings.append(Finding(note.path, 1, "model-content-over-budget",
                                f"{pct}% of the words were added by Claude; the limit is "
                                f"{round(MODEL_BUDGET * 100)}%", level="warning"))
    return findings


def default_mode(path: Path) -> str:
    parts = {p.lower() for p in path.parts}
    return "strict" if {"concepts", "methods", "exercises"} & parts else "normal"


def check_note(path: Path) -> list[Finding]:
    code = subject_of_path(path)
    if not code or notes.is_stub(path):
        return []
    text = path.read_text(encoding="utf-8")
    rel = relative(path)
    note = notes.parse(rel, text)
    definitions, used = anchors.parse(text)
    findings: list[Finding] = []
    for key in sorted(used - set(definitions)):
        line = next((i for i, ln in enumerate(text.splitlines(), 1) if f"[^{key}]" in ln), 1)
        findings.append(Finding(rel, line, "undefined-anchor", f"[^{key}] is used but never defined"))
    for key, anchor in definitions.items():
        findings.extend(check_anchor(code, anchor, rel))
        if key not in used:
            findings.append(Finding(rel, anchor.line, "unused-anchor",
                                    f"[^{key}] is defined but never used", level="warning"))
    mode = str(note.front.get("citations", default_mode(path)))
    findings.extend(check_coverage(note, mode))
    findings.extend(check_support(note, definitions))
    findings.extend(check_density(note, definitions))
    findings.extend(check_trivial(text, rel, definitions))
    return findings


NOTE_FOLDERS = ("classes", "concepts", "methods", "exercises", "notes")


def note_paths(code: str | None = None) -> list[Path]:
    out: list[Path] = []
    for c in [code] if code else subject_codes():
        root = subject_dir(c)
        for folder in NOTE_FOLDERS:
            out.extend(sorted((root / folder).rglob("*.md")))
    return out


def check_paths(paths: list[Path]) -> list[Finding]:
    return [f for p in paths if p.exists() and p.suffix == ".md" for f in check_note(p)]


def check_subject(code: str | None = None) -> list[Finding]:
    return check_paths(note_paths(code))
