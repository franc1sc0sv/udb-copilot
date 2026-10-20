"""Builds tests/fixtures/home: a tiny, license-free demo vault (subject DEMO)."""
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])

PAGES = [
    "La ley de Ohm relaciona tres magnitudes de un circuito: el voltaje, la corriente y la resistencia. "
    "El voltaje es igual a la corriente multiplicada por la resistencia.",
    "Para calcular la corriente se divide el voltaje entre la resistencia. "
    "Primero se identifican los datos del circuito. Después se despeja la incógnita. "
    "Por último se sustituyen los valores con sus unidades.",
    'El profesor dijo: "la unidad de resistencia es el ohmio". Un resistor de 10 ohmios con 20 voltios '
    "deja pasar 2 amperios.",
]


def write(rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


write("udb.yaml", "schema: 1\ntimezone: America/El_Salvador\nlanguage: es\n"
      "institution:\n  name: Demo University\n  moodle_url: https://moodle.example.edu\n"
      "  guard_domains: [moodle.example.edu]\n")
write("config/subjects.yaml", "subjects:\n- code: DEMO\n  name: Circuitos de ejemplo\n"
      "  tipo: ingenieria\n  term: 2026-1\n  moodle_course_id: 101\n  dias: [lunes, jueves]\n")
write("config/agenda.yaml", "passing_grade: 6.0\nsubjects:\n  DEMO:\n    source: SRC-DEMO-0001\n"
      "    items:\n      - {key: demo-t1, label: 'Tarea 1', weight: 20, kind: entrega, "
      "end: 2026-03-10, moodle: ['tarea 1'], evidence: 'ley de Ohm'}\n")

source_text = "\n\n".join(PAGES)
write("vault/DEMO/sources/SRC-DEMO-0001.txt", source_text)
digest = hashlib.sha256(source_text.encode()).hexdigest()
records = [
    {"id": "SRC-DEMO-0001", "subject": "DEMO", "kind": "course", "title": "Ley de Ohm",
     "path": "sources/SRC-DEMO-0001.txt", "original_name": "ohm.txt", "url": None, "clase": 1,
     "moodle_id": None, "sha256": digest, "retrieved_at": "2026-01-10", "superseded_by": None},
    {"id": "SRC-DEMO-0002", "subject": "DEMO", "kind": "course", "title": "Versión vieja",
     "path": "sources/SRC-DEMO-0001.txt", "original_name": "old.txt", "url": None, "clase": 1,
     "moodle_id": None, "sha256": "0" * 64, "retrieved_at": "2026-01-01",
     "superseded_by": "SRC-DEMO-0001"},
]
write("vault/DEMO/registry.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
cursor, lines = 0, []
for i, page in enumerate(PAGES, 1):
    lines.append(json.dumps({"page": i, "text": page, "char_start": cursor,
                             "char_end": cursor + len(page)}, ensure_ascii=False))
    cursor += len(page) + 1
for sid in ("SRC-DEMO-0001", "SRC-DEMO-0002"):
    write(f"vault/DEMO/derived/text/{sid}.pages.jsonl", "\n".join(lines) + "\n")

write("vault/DEMO/methods/ohm-current.md", """---
metodo: ohm-current
asignatura: DEMO
clase: 1
estado: confirmado
---

# Método: corriente con la ley de Ohm

## En una frase

Se calcula la corriente dividiendo el voltaje entre la resistencia.[^m1]

## Pasos (orden obligatorio)

1. Identificar los datos del circuito.[^m1]
2. Despejar la incógnita.[^m1]
3. Sustituir los valores con sus unidades.[^m1]

[^m1]: SRC-DEMO-0001 | page=2 | quote="Primero se identifican los datos del circuito."
""")

write("vault/DEMO/classes/01-2026-01-10/class.md", """---
asignatura: DEMO
clase: 1
fecha: 2026-01-10
tipo: ingenieria
citas: normal
titulo: Ley de Ohm
---

# Clase 01 — Ley de Ohm

## En una frase

La ley de Ohm une voltaje, corriente y resistencia.[^c1]

## Por qué importa

Sirve para saber cuánta corriente pasa por un resistor.[^c2]

## Explicación

El voltaje es igual a la corriente por la resistencia.[^c1]

## Paso a paso

1. Identifica los datos del circuito.[^c2]

## Ejemplo

Un resistor de 10 ohmios con 20 voltios deja pasar 2 amperios.[^c3]

## Diagrama

```mermaid
flowchart LR
  V[Voltaje] --> I[Corriente]
```

## Errores comunes

Olvidar las unidades al sustituir los valores.[^c2]

## Preguntas

- ¿Qué pasa si la resistencia se duplica?

## Relación con

- [[resistencia]]

[^c1]: SRC-DEMO-0001 | page=1 | quote="El voltaje es igual a la corriente multiplicada por la resistencia."
[^c2]: SRC-DEMO-0001 | page=2 | quote="Por último se sustituyen los valores con sus unidades."
[^c3]: SRC-DEMO-0001 | page=3 | quote="Un resistor de 10 ohmios con 20 voltios deja pasar 2 amperios."
""")

write("vault/DEMO/exercises/ex-01.md", """---
metodo: ohm-current
asignatura: DEMO
clase: 1
citas: libre
---

# Ejercicio 1

## Solución

**Paso 1 — Datos** (método paso 1): V = 20 V y R = 10 Ω.

**Paso 2 — Despejar** (método paso 2): I = V / R.

**Paso 3 — Sustituir** (método paso 3): I = 20 / 10 = 2 A.
""")

write("cycles/2026-1/DEMO/tasks/01-tarea-1/TASK.md", """---
title: Tarea 1
moodle_url: https://moodle.example.edu/mod/assign/view.php?id=1
status: pending
method: ohm-current
deliverable: informe en PDF
---

# Tarea 1
""")
write("cycles/2026-1/DEMO/tasks/02-proyecto/TASK.md", """---
id: 02-proyecto
subject: DEMO
term: 2026-1
title: Proyecto final
moodle_url: null
status: in-progress
methods: []
repos:
  - url: https://github.com/example/demo-project.git
    path: work/demo-project
---
""")
print("fixture written to", root)
