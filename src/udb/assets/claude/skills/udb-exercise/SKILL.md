---
name: udb-exercise
description: Solves a graded exercise following the teacher's method, as HTML step cards with formulas rendered offline. Use it for every homework or graded exercise.
---

# /udb-exercise

Call `method_get` first.
- `NOT_FOUND`: do **not** solve. Say which method is missing and offer `/udb-method`.
- `conflict`: **stop and ask**.

With a method, launch `methodist` and build the page with `udb.rendering.exercise`:

```python
from udb.rendering.exercise import Exercise, Step, Row, write

ex = Exercise(kicker="AVM · Clase 04 · Guía 1", tab_label="Ej. 1", title=r"\(z^4=16\)",
              sub="Raíces cuartas", method="complex-roots", classes=[4],
              steps=[Step(title="Despejar", given=r"z^4=16", goal="el módulo", result=r"|z|=2",
                          next="-> paso 2", method_step=1,
                          rows=[Row(r"|z|^4 = 16", "módulo a ambos lados")])],
              answer=[r"z_k = 2\,\mathrm{cis}(k\pi/2)"], sources=["Clase 4, diapositiva 3"])
write([ex], "vault/AVM/exercises/guide-1.html", page_title="Guía 1", subject="AVM")
```

Rules: one table row per change, reason of eight words or fewer; prose header, never bare
"Entra/Busco/Sale" labels; a drawing the problem asks for goes in `Step.svg`; several exercises
of one guide are tabs of one page; a shortcut is a `Step(shortcut=True)`, never part of the
solution. Save the build script next to the HTML. `write` renders math to SVG and fails on raw
TeX or external scripts. Finish with `method_check` on the HTML.
