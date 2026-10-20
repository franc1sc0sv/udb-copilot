"""Diagram catalog: which mermaid type fits which shape of idea (descriptions in Spanish)."""
CATALOG = [
    {
        "id": "flowchart",
        "use_for": "un proceso con pasos, una decisión, un algoritmo",
        "mermaid": "flowchart TD",
        "template": "flowchart TD\n  A[Inicio] --> B{¿Condición?}\n  B -->|Sí| C[Acción]\n  B -->|No| D[Otra acción]\n  C --> E[Fin]\n  D --> E",
    },
    {
        "id": "sequence",
        "use_for": "quién envía qué a quién, y en qué orden (handshakes, protocolos, APIs)",
        "mermaid": "sequenceDiagram",
        "template": "sequenceDiagram\n  participant C as Cliente\n  participant S as Servidor\n  C->>S: SYN\n  S-->>C: SYN-ACK\n  C->>S: ACK",
    },
    {
        "id": "state",
        "use_for": "algo que tiene modos y cambia entre ellos",
        "mermaid": "stateDiagram-v2",
        "template": "stateDiagram-v2\n  [*] --> Cerrado\n  Cerrado --> Escuchando: listen()\n  Escuchando --> Establecido: ACK\n  Establecido --> [*]",
    },
    {
        "id": "block",
        "use_for": "capas, una pila, partes y cómo se conectan (OSI, TCP/IP, arquitectura)",
        "mermaid": "block-beta",
        "template": "block-beta\n  columns 1\n  A[\"7 Aplicación\"]\n  B[\"4 Transporte\"]\n  C[\"3 Red\"]\n  D[\"2 Enlace\"]",
    },
    {
        "id": "packet",
        "use_for": "el formato de un paquete o una trama, campo por campo",
        "mermaid": "packet-beta",
        "template": "packet-beta\n  0-3: \"Versión\"\n  4-7: \"IHL\"\n  8-15: \"ToS\"\n  16-31: \"Longitud total\"",
    },
    {
        "id": "er",
        "use_for": "un modelo de datos, tablas y relaciones",
        "mermaid": "erDiagram",
        "template": "erDiagram\n  ALUMNO ||--o{ MATRICULA : tiene\n  MATERIA ||--o{ MATRICULA : incluye",
    },
    {
        "id": "class",
        "use_for": "clases, objetos, herencia (programación)",
        "mermaid": "classDiagram",
        "template": "classDiagram\n  class Figura {\n    +area() float\n  }\n  Figura <|-- Circulo",
    },
    {
        "id": "mindmap",
        "use_for": "un tema y sus ideas relacionadas; repaso general",
        "mermaid": "mindmap",
        "template": "mindmap\n  root((Tema))\n    Idea A\n      Detalle\n    Idea B",
    },
    {
        "id": "timeline",
        "use_for": "hechos en orden de tiempo (historia, evolución de un estándar)",
        "mermaid": "timeline",
        "template": "timeline\n  title Evolución\n  1974 : TCP\n  1981 : IPv4\n  1998 : IPv6",
    },
    {
        "id": "xychart",
        "use_for": "números que cambian; una curva, una comparación",
        "mermaid": "xychart-beta",
        "template": "xychart-beta\n  title \"Retardo\"\n  x-axis [1, 2, 3, 4]\n  y-axis \"ms\" 0 --> 100\n  line [10, 25, 60, 90]",
    },
    {
        "id": "sankey",
        "use_for": "cómo se reparte una cantidad entre varias salidas",
        "mermaid": "sankey-beta",
        "template": "sankey-beta\n  Total,Subred A,60\n  Total,Subred B,28",
    },
    {
        "id": "quadrant",
        "use_for": "comparar cosas en dos ejes",
        "mermaid": "quadrantChart",
        "template": "quadrantChart\n  title Comparación\n  x-axis Bajo --> Alto\n  y-axis Bajo --> Alto\n  Opción A: [0.3, 0.6]",
    },
    {
        "id": "argumento",
        "use_for": "una tesis, sus argumentos y su evidencia (materias humanísticas)",
        "mermaid": "flowchart TD",
        "template": "flowchart TD\n  T[\"Tesis\"] --> A1[\"Argumento 1\"]\n  T --> A2[\"Argumento 2\"]\n  A1 --> E1[\"Evidencia: cita\"]\n  A2 --> E2[\"Evidencia: cita\"]\n  T -.-> C[\"Contraargumento\"]",
    },
    {
        "id": "topologia",
        "use_for": "una red con dispositivos reales y cables",
        "mermaid": None,
        "template": "usa un archivo .excalidraw en diagrams/",
    },
    {
        "id": "formula",
        "use_for": "una fórmula, una figura geométrica, un circuito",
        "mermaid": None,
        "template": "usa <svg> en línea",
    },
]

BY_ID = {d["id"]: d for d in CATALOG}


def suggest(shape: str) -> list[dict]:
    words = {w for w in shape.lower().split() if len(w) > 3}
    scored = []
    for entry in CATALOG:
        text = (entry["use_for"] + " " + entry["id"]).lower()
        score = sum(1 for w in words if w in text)
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda p: -p[0])
    return [e for _, e in scored[:3]] or CATALOG[:3]


def catalog_table() -> str:
    lines = ["| id | use for | base |", "| --- | --- | --- |"]
    for entry in CATALOG:
        base = entry["mermaid"] or "svg / excalidraw"
        lines.append(f"| `{entry['id']}` | {entry['use_for']} | `{base}` |")
    return "\n".join(lines)
