"""Solved exercises as HTML step cards, one tab per exercise.

Build the data with `Exercise`, `Step` and `Row`, then call `write(...)`.
Formulas are TeX and are rendered to inline SVG at build time, so the page
needs no network. Each step can say which step of the teacher's method it
applies (`method_step`); `udb verify` checks that from the JSON block the page
embeds.

    ex = Exercise(kicker="AVM · Clase 04", title=r"\\(z^4 = 16\\)", sub="...",
                  method="roots-of-complex", classes=[4],
                  steps=[Step(title="Despejar", given=r"z^4=16", goal="las raíces",
                              result=r"z=2", next="-> paso 2", method_step=1,
                              rows=[Row(r"z^4 = 16", "dato")])],
                  answer=[r"z_k = 2\\,\\text{cis}(k\\pi/2)"], sources=["Clase 4, p. 3"])
    write([ex], "vault/AVM/exercises/guide-1.html", page_title="Guía 1", subject="AVM")
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from udb.rendering import math_svg


@dataclass
class Row:
    """One line of the calculation: a TeX formula (no delimiters) and where it comes from."""
    tex: str
    note: str = ""
    gap: bool = False          # extra space above this row


@dataclass
class Step:
    title: str
    given: str = ""            # TeX of what the step starts from
    given_note: str = ""
    goal: str = ""             # what the step looks for, in words
    result: str = ""           # TeX of what comes out
    next: str = ""             # "-> paso 2"
    rows: list[Row] = field(default_factory=list)
    warning: str | None = None
    svg: str | None = None     # raw SVG drawing, inserted as is
    svg_caption: str | None = None
    shortcut: bool = False     # a side shortcut, not counted in "Paso N de M"
    part: str = ""             # "a) Aceleración": opens a divider bar before this step
    part_answer: str = ""      # TeX; closes the part with its own answer box
    method_step: int | None = None


@dataclass
class Exercise:
    kicker: str
    title: str                 # TeX with \( \)
    sub: str
    steps: list[Step]
    answer: list[str]
    sources: list[str]         # plain lines for "De dónde sale"
    tab_label: str = ""
    method: str | None = None  # slug of vault/<SUBJECT>/methods/<slug>.md
    classes: list[int] = field(default_factory=list)
    not_applicable: list[int] = field(default_factory=list)


CSS = """
:root {
  color-scheme: light;
  --bg: #fbfaf8; --fg: #1d1c1a; --muted: #6b6862; --line: #e3e0da;
  --card: #ffffff; --accent: #7a4b2a; --accent-soft: #f3e9e1;
  --ok: #4f7a3a; --ok-soft: #eef4ea;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}
main { max-width: 820px; margin-inline: auto; padding: 40px 28px 100px; }
@media (max-width: 640px) { main { padding: 24px 16px 60px; } }

/* ---------- Pestañas ---------- */
.tabs { position: sticky; top: 0; z-index: 5; background: var(--bg);
  display: flex; gap: 6px; flex-wrap: wrap; padding: 14px 0 16px;
  border-bottom: 1px solid var(--line); margin-bottom: 30px; }
.tabs button { font: 600 13.5px/1.4 ui-sans-serif, system-ui, sans-serif;
  cursor: pointer; padding: 8px 16px; border-radius: 999px;
  border: 1px solid var(--line); background: var(--card); color: var(--fg); }
.tabs button.on { background: var(--accent); border-color: var(--accent); color: var(--bg); }
.sheet { display: none; }
.sheet.on { display: block; }

header.top { border-bottom: 1px solid var(--line); padding-bottom: 18px; margin-bottom: 30px; }
.kicker { font: 600 11px/1.4 ui-sans-serif, system-ui, sans-serif;
  letter-spacing: .14em; text-transform: uppercase; color: var(--muted); }
h1 { font-size: 25px; line-height: 1.3; margin: 10px 0 8px; letter-spacing: -0.01em; font-weight: 650; }
.sub { color: var(--muted); font-size: 14px; margin: 0; }

/* ---------- Literal ---------- */
.part-bar { margin: 38px 0 14px; padding: 11px 18px; background: var(--accent);
  border-radius: 10px; font: 700 14px/1.4 ui-sans-serif, system-ui, sans-serif;
  color: var(--bg); letter-spacing: .01em; }
.step:first-of-type, .part-bar:first-child { margin-top: 0; }
.part-answer { margin: 0 20px 18px; padding: 11px 16px; border: 1.5px solid var(--accent);
  border-radius: 8px; background: var(--accent-soft); font-size: 14.5px; }
.part-answer strong { color: var(--accent); }

/* ---------- Ficha de paso ---------- */
.step { border: 1px solid var(--line); border-radius: 12px; background: var(--card);
  margin-bottom: 26px; overflow: hidden; }
.step > h2 { margin: 0; padding: 13px 20px; background: var(--accent-soft);
  border-bottom: 1px solid var(--line);
  font: 650 12px/1.4 ui-sans-serif, system-ui, sans-serif;
  letter-spacing: .1em; text-transform: uppercase; color: var(--accent); }
.step > h2 .tit { color: var(--fg); text-transform: none; letter-spacing: 0;
  font-size: 15px; font-weight: 600; margin-left: 10px; }
@media (max-width: 560px) { .step > h2 .tit { display: block; margin: 5px 0 0; } }
.step.shortcut > h2 { background: var(--ok-soft); }
.step.shortcut > h2 .tit-shortcut { color: var(--ok); }
.step.shortcut { border-color: var(--ok); border-style: dashed; }

.io { padding: 14px 20px 2px; border-bottom: 1px solid var(--line); }
.io p.flow { margin: 0 0 14px; font-size: 15px; line-height: 1.65; }
.io p.flow + p.flow { margin-top: -6px; }
.io .note { color: var(--muted); font-size: 13.5px; }
.io .next { color: var(--accent); font-weight: 600; font-size: 13.5px; white-space: nowrap; }

/* ---------- Cálculo ---------- */
.calc { padding: 8px 20px 18px; }
.calc table { border-collapse: collapse; width: 100%; }
.calc td { vertical-align: baseline; padding: 3px 0; border: none; }
.calc td.m { width: 99%; }
.calc td.r { color: var(--muted); font-size: 13px; padding-left: 22px;
  text-align: right; white-space: nowrap; }
@media (max-width: 640px) {
  .calc td.r { white-space: normal; font-size: 12px; padding-left: 12px; }
}
.calc tr.gap td { padding-top: 16px; }
.calc mjx-container { margin: 0 !important; }
.calc mjx-container[display="true"] { margin: 0 !important; text-align: left !important; }
.calc mjx-container[display="true"] mjx-math { margin: 0 !important; text-align: left !important; }

/* ---------- Avisos y resultado ---------- */
.warning { margin: 0 20px 18px; padding: 11px 15px; border-left: 3px solid var(--accent);
  background: var(--accent-soft); border-radius: 0 8px 8px 0; font-size: 14px; }
.warning strong { color: var(--accent); }
.check { color: var(--ok); font-weight: 700; }
.answer { border: 2px solid var(--accent); border-radius: 12px; padding: 8px 24px 20px;
  margin: 34px 0 26px; background: var(--card); }
.answer h2 { font: 650 12px/1.4 ui-sans-serif, system-ui, sans-serif;
  letter-spacing: .12em; text-transform: uppercase; color: var(--accent); margin: 16px 0 4px; }
.answer .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 28px; }
@media (max-width: 560px) { .answer .grid { grid-template-columns: 1fr; } }

/* ---------- Gráfica ---------- */
figure { margin: 0; padding: 4px 20px 18px; }
figcaption { color: var(--muted); font-size: 13px; text-align: center; margin-top: 6px; }
svg { display: block; margin: 0 auto; max-width: 100%; height: auto; }

footer { margin-top: 44px; padding-top: 18px; border-top: 1px solid var(--line);
  color: var(--muted); font-size: 13px; }
footer ul { padding-left: 18px; margin: 8px 0 0; }
footer li { margin-bottom: 3px; }
mjx-container { overflow-x: auto; overflow-y: hidden; max-width: 100%; position: relative; }
"""

JS_TABS = """
function show(i) {
  document.querySelectorAll('.sheet').forEach((el, n) => el.classList.toggle('on', n === i));
  document.querySelectorAll('.tabs button').forEach((el, n) => el.classList.toggle('on', n === i));
}
"""


def _inline(tex: str) -> str:
    return f"\\({tex}\\)"


def _display(tex: str) -> str:
    return f"\\[{tex}\\]"


def _row(r: Row) -> str:
    cls = ' class="gap"' if r.gap else ""
    return f'<tr{cls}><td class="m">{_display(r.tex)}</td><td class="r">{escape(r.note)}</td></tr>'


def _flow(s: Step) -> str:
    """Connected prose: where I start, what I look for, where I land. No bare labels."""
    out = []
    if s.given:
        note = f' <span class="note">({escape(s.given_note)})</span>' if s.given_note else ""
        goal = f", y busco {escape(s.goal)}" if s.goal else ""
        out.append(f'  <p class="flow">Parto de {_inline(s.given)}{note}{goal}.</p>')
    elif s.goal:
        out.append(f'  <p class="flow">Busco {escape(s.goal)}.</p>')
    if s.result:
        nxt = f' <span class="next">{escape(s.next)}</span>' if s.next else ""
        out.append(f'  <p class="flow">Con eso, {_inline(s.result)}{nxt}.</p>')
    return "\n".join(out)


def _step(s: Step, n: int, total: int) -> str:
    if s.shortcut:
        head = (f'<span class="tit-shortcut">Atajo — no usar en el examen</span> '
                f'<span class="tit">{escape(s.title)}</span>')
    else:
        head = f'Paso {n} de {total} <span class="tit">{escape(s.title)}</span>'
    out = [f'<section class="step{" shortcut" if s.shortcut else ""}">', f"  <h2>{head}</h2>",
           '  <div class="io">']
    flow = _flow(s)
    if flow:
        out.append(flow)
    out.append("  </div>")
    if s.rows:
        out += ['  <div class="calc"><table>', *(f"    {_row(r)}" for r in s.rows),
                "  </table></div>"]
    if s.warning:
        out.append(f'  <p class="warning"><strong>Ojo.</strong> {s.warning}</p>')
    if s.svg:
        out += ["  <figure>", f"    {s.svg}"]
        if s.svg_caption:
            out.append(f"    <figcaption>{s.svg_caption}</figcaption>")
        out.append("  </figure>")
    out.append("</section>")
    if s.part_answer:
        out.append(f'<div class="part-answer"><strong>Respuesta.</strong> {_inline(s.part_answer)}</div>')
    html = "\n".join(out)
    return f'<div class="part-bar">{escape(s.part)}</div>\n{html}' if s.part else html


def _sheet(e: Exercise, idx: int) -> str:
    total = len([s for s in e.steps if not s.shortcut])
    cards, n = [], 0
    for s in e.steps:
        n += 0 if s.shortcut else 1
        cards.append(_step(s, n, total))
    answer = "\n    ".join(f"<div>{_display(r)}</div>" for r in e.answer)
    sources = "\n    ".join(f"<li>{escape(s)}</li>" for s in e.sources)
    return f"""<section class="sheet{' on' if idx == 0 else ''}" id="sheet-{idx}">
<header class="top">
  <div class="kicker">{escape(e.kicker)}</div>
  <h1>{e.title}</h1>
  <p class="sub">{escape(e.sub)}</p>
</header>

{chr(10).join(cards)}

<div class="answer">
  <h2>Respuesta</h2>
  <div class="grid">
    {answer}
  </div>
</div>

<footer>
  <strong>De dónde sale</strong>
  <ul>
    {sources}
  </ul>
</footer>
</section>"""


def meta(exercises: list[Exercise], subject: str | None) -> dict:
    """What `udb verify` and `udb status` read back from the page."""
    return {
        "type": "exercise", "subject": subject,
        "classes": sorted({c for e in exercises for c in e.classes}),
        "exercises": [{
            "title": e.tab_label or e.kicker, "method": e.method, "classes": e.classes,
            "not_applicable": e.not_applicable, "sources": e.sources,
            "steps": [{"title": s.title, "method_step": s.method_step, "shortcut": s.shortcut}
                      for s in e.steps]} for e in exercises]}


def render(exercises: list[Exercise], page_title: str = "Ejercicios",
           subject: str | None = None) -> str:
    tabs = ""
    if len(exercises) > 1:
        buttons = "\n    ".join(
            f'<button class="{"on" if i == 0 else ""}" onclick="show({i})">'
            f"{escape(e.tab_label or e.kicker)}</button>" for i, e in enumerate(exercises))
        tabs = f'<nav class="tabs">\n    {buttons}\n  </nav>'
    sheets = "\n\n".join(_sheet(e, i) for i, e in enumerate(exercises))
    data = json.dumps(meta(exercises, subject), ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{escape(page_title)}</title>
<style>{CSS}</style>
<script>{JS_TABS}</script>
<script type="application/json" id="udb-meta">{data}</script>
</head>
<body>
<main>
{tabs}
{sheets}
</main>
</body>
</html>
"""


def write(exercises: list[Exercise], out_path: Path | str, page_title: str = "Ejercicios",
          subject: str | None = None, offline_math: bool = True) -> Path:
    out_path = Path(out_path)
    html = render(exercises, page_title, subject)
    if offline_math:
        html = math_svg.render_html(html)
        issues = math_svg.problems(html)
        if issues:
            raise math_svg.MathError(f"{out_path.name}: " + ", ".join(issues))
    out_path.write_text(html, encoding="utf-8")
    return out_path

