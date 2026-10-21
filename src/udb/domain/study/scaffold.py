"""Templates for new notes. Keys are English; the visible text is in the note language."""
from udb.domain.text import lang


def _sections(kind: str) -> list[str]:
    table = lang.get()
    keys = {v: k for k, v in table["sections"].items()}
    out = []
    for title in lang.sections_for(kind):
        out += [f"## {title}", "", f"<!-- {table['section_hints'][keys[title]]} -->", ""]
    return out


ANCHOR_HELP = [
    "<!-- Anclas. Una por cita. Formato:", "",
    '[^c1]: SRC-XXX-0001 | page=1 | quote="texto exacto de la fuente"',
    '[^c2]: SRC-XXX-0002 | t=00:10:00-00:10:20 | quote="lo que dijo el profesor"',
    '[^c3]: MODEL | reason="por qué el material no lo cubre" | basis=SRC-XXX-0001',
    "-->", "",
]


def concept_note(kind: str, title: str, subject: str, class_number: int | None = None) -> str:
    front = ["type: concept", f'title: "{title}"', f"subject: {subject}", f"kind: {kind}"]
    if class_number is not None:
        front.append(f"class: {class_number}")
    front.append("citations: strict")
    return "\n".join(["---", *front, "---", "", f"# {title}", "", *_sections(kind),
                      *ANCHOR_HELP])


def class_note(subject: str, number: int, date: str, kind: str, title: str = "") -> str:
    head = ["---", "type: class", f"subject: {subject}", f"class: {number}", f"date: {date}",
            f'title: "{title}"', "unit: null", "sources: []", "methods: []", "concepts: []",
            "tasks: []", "expects_assignment: false", "status: pending",
            "citations: normal", "---", "", f"# Clase {number:02d} — {title or date}", ""]
    return "\n".join(head + _sections(kind) + ANCHOR_HELP)


METHOD = """---
type: method
slug: {slug}
subject: {subject}
title: "{title}"
classes: [{classes}]
sources: [{source}]
status: provisional
---

# Método: {title}

## En una frase

<!-- Qué resuelve este método, en una frase. -->

## Pasos (orden obligatorio)

<!-- Lista numerada. Cada paso viene del profesor y lleva su cita.
     No añadas pasos que el profesor no dijo. No quites ninguno. -->

1. <!-- paso 1 -->[^m1]

## Ejemplo que resolvió el profesor

<!-- El mismo ejercicio que hizo en clase, paso por paso, con anclas. -->

## Errores que el profesor marca

<!-- Lo que dijo que está mal. Con cita. -->

[^m1]: {source} | page=1 | quote=""
"""

ASSIGNMENT = """---
type: assignment
subject: {subject}
class: {number}
method: {slug}
citations: normal
---

# Tarea — Clase {number:02d}

## Enunciado

<!-- Copia literal del enunciado, con su cita. -->

## Solución

<!-- Cada paso empieza con **Paso N — nombre** y lleva (método paso N).
     No uses ningún paso que no esté en el método. -->

**Paso 1 — ** (método paso 1)[^c1]

## Comprobación

<!-- Cómo saber que el resultado está bien. -->
"""

TASK = """---
id: {id}
subject: {subject}
term: {term}
title: "{title}"
moodle_url: {moodle_url}
status: todo
due: {due}
methods: []
deliverables: []
repos: []
grade: null
---

# {title}

## Indicaciones

## Notas
"""


def method_note(slug: str, title: str, subject: str, classes: list[int] | None = None,
                source: str = "SRC-XXX-0001") -> str:
    return METHOD.format(slug=slug, title=title, subject=subject, source=source,
                         classes=", ".join(str(c) for c in classes or []))


def assignment_note(subject: str, number: int, slug: str) -> str:
    return ASSIGNMENT.format(subject=subject, number=number, slug=slug)


def task_file(task_id: str, subject: str, term: str, title: str, moodle_url: str = "",
              due: str = "null") -> str:
    return TASK.format(id=task_id, subject=subject, term=term, title=title.replace('"', "'"),
                       moodle_url=moodle_url or "null", due=due)
