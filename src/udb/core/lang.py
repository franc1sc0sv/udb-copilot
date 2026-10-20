"""Words the engine reads and writes *inside* notes.

Code, commands and keys are English. Note content is in the student's
language; today that is Spanish, the language of UDB courses. Everything the
checks match against note text lives here, so another language is one more
table, not a hunt through the code.
"""

ES = {
    # Sections of a class or concept note, in order.
    "sections": {
        "summary": "En una frase",
        "why": "Por qué importa",
        "definition": "Definición",
        "explanation": "Explicación",
        "formulas": "Fórmulas",
        "units": "Unidades",
        "steps": "Paso a paso",
        "code": "Código",
        "thesis": "Tesis",
        "arguments": "Argumentos",
        "quotes": "Citas textuales",
        "example": "Ejemplo",
        "diagram": "Diagrama",
        "mistakes": "Errores comunes",
        "questions": "Preguntas",
        "related": "Relación con",
    },
    "section_hints": {
        "summary": "Una sola frase. Sin palabras difíciles. Con cita.",
        "why": "Dos frases. Para qué sirve esto en la práctica.",
        "definition": "La definición literal del profesor, entre comillas, con cita.",
        "explanation": "Párrafos cortos. Una idea por párrafo. Cada uno con cita.",
        "formulas": "La fórmula tal como la escribió el profesor. Di qué es cada letra.",
        "units": "Qué unidad tiene cada valor y cómo se convierte.",
        "steps": "Lista numerada. Un verbo por paso. Cita por paso.",
        "code": "El código como lo escribió el profesor. Sin mejoras.",
        "thesis": "La idea central que se defiende, en una frase.",
        "arguments": "Cada argumento con la cita del autor que lo sostiene.",
        "quotes": "Las palabras exactas del autor, con página.",
        "example": "Un caso real con números reales, resuelto hasta el final.",
        "diagram": "Un bloque ```mermaid```. Elige el tipo del catálogo.",
        "mistakes": "Lo que el profesor marca en rojo. Con cita.",
        "questions": "3 a 6 preguntas. La respuesta va en un bloque plegable.",
        "related": "Enlaces [[nota]] a otras notas del vault.",
    },
    # Sections every note needs, plus the extra ones per subject kind.
    "base_sections": ["summary", "why", "explanation", "example", "diagram", "questions",
                      "related"],
    "extra_sections": {
        "engineering": ["steps", "mistakes"],
        "math": ["definition", "steps", "mistakes"],
        "programming": ["steps", "code", "mistakes"],
        "physics": ["formulas", "units", "steps", "mistakes"],
        "humanities": ["thesis", "arguments", "quotes"],
        "general": [],
    },
    # Sections where an uncited paragraph is fine.
    "exempt_always": ["preguntas", "relación con", "relacion con", "diagrama", "diagramas",
                      "fuentes", "referencias"],
    "exempt_normal": ["en una frase", "por qué importa", "por que importa"],
    # Sections where one citation covers the whole section.
    "section_level": ["ejemplo", "ejemplos", "comprobación", "comprobacion",
                      "ejemplo que resolvió el profesor", "ejemplo que resolvio el profesor"],
    # Method and exercise notes.
    "method_steps_heading": r"^pasos?\b",
    "solution_sections": ["ejercicio", "solución", "solucion", "desarrollo"],
    "step_marker": r"\(m[ée]todo paso (\d+)\)",
    "step_bold": r"^\s*\*\*Paso\s+(\d+)\s*[—–:-]?\s*(.*?)\*\*",
    "step_block": r"^\s*(\*\*Paso\b|\d+\.\s)",
    "not_applicable": r"no-aplica:\s*([\d,\s]+)",
    # Callout labels in rendered pages.
    "callouts": {"model": "Añadido por Claude", "alerta": "Aviso",
                 "metodo": "Método del profesor", "método": "Método del profesor",
                 "nota": "Nota", "tip": "Consejo"},
    "passive": r"\b(fue|fueron|es|son|era|eran|será|serán|ha sido|han sido)\s+\w+"
               r"(ado|ada|ados|adas|ido|ida|idos|idas)\b",
}

LANGS = {"es": ES}


def get(language: str | None = None) -> dict:
    if language is None:
        from . import settings
        try:
            language = settings.get().language
        except settings.HomeNotFound:
            language = "es"
    return LANGS.get(language, ES)


def section(key: str, language: str | None = None) -> str:
    return get(language)["sections"][key]


def sections_for(kind: str, language: str | None = None) -> list[str]:
    """Section titles a note of this subject kind must have, in template order."""
    table = get(language)
    wanted = set(table["base_sections"]) | set(table["extra_sections"].get(kind, []))
    return [title for key, title in table["sections"].items() if key in wanted]
