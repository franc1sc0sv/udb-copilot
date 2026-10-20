"""Does a solved exercise follow the teacher's method, step by step?

Two formats are checked the same way:

- Markdown exercises mark each step with `(método paso N)`.
- HTML exercises (built by `udb.rendering.exercise`) embed a JSON block with
  the method slug and the method step of every card.
"""
import json
import re
from pathlib import Path

from ..core import lang, notes
from ..core.findings import Finding
from ..core.paths import relative, subject_codes, subject_dir, subject_of_path
from ..vault import methods
from ..vault.methods import Method

META_RE = re.compile(r'<script type="application/json" id="udb-meta">(.*?)</script>', re.S)


def check_methods(code: str | None = None) -> list[Finding]:
    """A method with a bad status or no readable steps is useless; say so."""
    findings: list[Finding] = []
    for c in [code] if code else subject_codes():
        for m in methods.list_all(c):
            rel = relative(m.path)
            if not methods.valid_status(m.status):
                findings.append(Finding(rel, 1, "invalid-method-status",
                                        f"status '{m.status}' does not exist; use confirmed, "
                                        "provisional or conflict"))
            if not m.steps:
                findings.append(Finding(rel, 1, "method-without-steps",
                                        "no numbered step found under a 'Pasos' section"))
    return findings


def _method_findings(rel: str, code: str, slug: str | None) -> tuple[Method | None, list[Finding]]:
    if not slug:
        return None, [Finding(rel, 1, "no-method",
                              "the exercise does not declare 'method:'. "
                              "Run `udb method <topic>` before solving.")]
    method = methods.read(code, str(slug))
    if method is None:
        return None, [Finding(rel, 1, "missing-method",
                              f"vault/{code}/methods/{slug}.md does not exist. Extract it first.")]
    out = []
    if method.status == "conflict":
        out.append(Finding(rel, 1, "method-in-conflict",
                           f"method '{slug}' has sources that disagree; settle it with the user"))
    elif method.status == "provisional":
        out.append(Finding(rel, 1, "method-provisional",
                           f"method '{slug}' is not confirmed by the teacher", level="warning"))
    if not method.steps:
        out.append(Finding(rel, 1, "method-without-steps", f"'{slug}.md' has no numbered steps"))
        return None, out
    return method, out


def _step_findings(rel: str, method: Method, used_in_order: dict[str, list[int]],
                   declared_skips: set[int]) -> list[Finding]:
    out = []
    total = len(method.steps)
    used = set()
    for section, order in used_in_order.items():
        for n in order:
            if 1 <= n <= total:
                used.add(n)
            else:
                out.append(Finding(rel, 1, "step-outside-method",
                                   f"method step {n} does not exist; '{method.slug}' has {total}"))
        if order != sorted(order):
            out.append(Finding(rel, 1, "wrong-order",
                               f"in '{section}' the steps are not in method order: {order}"))
    skipped = [n for n in range(1, total + 1) if n not in used and n not in declared_skips]
    if skipped and used:
        out.append(Finding(rel, 1, "skipped-step",
                           f"the solution never uses steps {skipped} of '{method.slug}'. "
                           f"If they do not apply, write 'no-aplica: {','.join(map(str, skipped))}'.",
                           level="warning"))
    return out


def check_markdown(path: Path) -> list[Finding]:
    code = subject_of_path(path)
    if not code:
        return []
    raw = path.read_text(encoding="utf-8")
    rel = relative(path)
    note = notes.parse(rel, raw)
    method, findings = _method_findings(rel, code, note.front.get("method"))
    if method is None:
        return findings

    table = lang.get()
    marker = re.compile(table["step_marker"], re.IGNORECASE)
    step_block = re.compile(table["step_block"], re.IGNORECASE)
    solution = tuple(table["solution_sections"])
    by_section: dict[str, list[int]] = {}
    for block in note.blocks:
        if block.callout_kind or not block.section.strip().lower().startswith(solution):
            continue
        for offset, line in enumerate(block.lines):
            if step_block.match(line) and not marker.search(line):
                findings.append(Finding(rel, block.start_line + offset, "unmarked-step",
                                        f'this step does not say which method step it is: '
                                        f'"{line.strip()[:60]}". Add "(método paso N)".'))
        marks = [int(n) for n in marker.findall(block.text)]
        if marks:
            by_section.setdefault(block.section, []).extend(marks)
    skips = {int(n) for group in re.findall(table["not_applicable"], raw)
             for n in re.findall(r"\d+", group)}
    return findings + _step_findings(rel, method, by_section, skips)


def read_meta(path: Path) -> dict | None:
    m = META_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    return json.loads(m.group(1)) if m else None


def check_html(path: Path) -> list[Finding]:
    code = subject_of_path(path)
    meta = read_meta(path)
    if not code or meta is None:
        return []
    rel = relative(path)
    findings: list[Finding] = []
    for i, ex in enumerate(meta.get("exercises", []), 1):
        label = ex.get("title") or f"exercise {i}"
        if ex.get("method") is None and not ex.get("steps"):
            continue
        method, found = _method_findings(f"{rel} ({label})", code, ex.get("method"))
        findings += found
        if method is None:
            continue
        steps = [s for s in ex.get("steps", []) if not s.get("shortcut")]
        unmarked = [s["title"] for s in steps if s.get("method_step") is None]
        for title in unmarked:
            findings.append(Finding(rel, 1, "unmarked-step",
                                    f"{label}: step '{title}' has no method_step"))
        order = [s["method_step"] for s in steps if s.get("method_step") is not None]
        findings += _step_findings(f"{rel} ({label})", method, {label: order},
                                   set(ex.get("not_applicable", [])))
    return findings


def exercise_paths(code: str | None = None) -> list[Path]:
    out: list[Path] = []
    for c in [code] if code else subject_codes():
        root = subject_dir(c)
        out.extend(sorted((root / "exercises").rglob("*.md")))
        out.extend(sorted((root / "exercises").rglob("*.html")))
        out.extend(sorted((root / "classes").rglob("assignment.md")))
    return out


def is_exercise(path: Path) -> bool:
    path = Path(path)
    if path.suffix not in (".md", ".html"):
        return False
    return "exercises" in {p.lower() for p in path.parts} or path.name == "assignment.md"


def check_path(path: Path) -> list[Finding]:
    if not path.exists() or not is_exercise(path):
        return []
    return check_html(path) if path.suffix == ".html" else check_markdown(path)


def check_paths(paths: list[Path]) -> list[Finding]:
    return [f for p in paths for f in check_path(p)]
