from udb import checks
from udb.checks import citations, clarity, exercises
from udb.rendering.exercise import Exercise, Row, Step, write

CLASS = "vault/DEMO/classes/01-2026-01-10/class.md"


def codes(findings, level="error"):
    return {f.code for f in findings if f.level == level}


def test_clean_class_note_passes(indexed):
    found = checks.check_file(indexed / CLASS)
    assert codes(found) == set(), [str(f) for f in found]


def test_wrong_quote_is_an_error(indexed):
    path = indexed / CLASS
    path.write_text(path.read_text().replace("multiplicada por", "dividida entre"))
    assert "quote-not-found" in codes(citations.check_paths([path]))


def test_quote_across_page_break_passes(indexed):
    path = indexed / CLASS
    text = path.read_text().replace(
        'page=1 | quote="El voltaje es igual a la corriente multiplicada por la resistencia."',
        'page=1 | quote="multiplicada por la resistencia. Para calcular la corriente"')
    path.write_text(text)
    assert "quote-not-found" not in codes(citations.check_paths([path]))


def test_superseded_and_trivial_quotes(indexed):
    path = indexed / CLASS
    text = path.read_text().replace("[^c3]: SRC-DEMO-0001 | page=3",
                                    "[^c3]: SRC-DEMO-0002 | page=3")
    text = text.replace('quote="Por último se sustituyen los valores con sus unidades."',
                        'quote="valores"')
    path.write_text(text)
    found = citations.check_paths([path])
    assert "superseded-source" in codes(found)
    assert "trivial-quote" in codes(found, "warning")


def test_uncited_paragraph(indexed):
    path = indexed / CLASS
    path.write_text(path.read_text().replace(
        "## Explicación\n", "## Explicación\n\nEsta frase no tiene ninguna cita.\n\n"))
    assert "uncited-paragraph" in codes(citations.check_paths([path]))


def test_long_sentence(indexed):
    path = indexed / CLASS
    long = " ".join(["palabra"] * 30) + "."
    path.write_text(path.read_text().replace("## Explicación\n",
                                             f"## Explicación\n\n{long}[^c1]\n\n"))
    assert "long-sentence" in codes(clarity.check_paths([path]))


def test_markdown_exercise_follows_method(indexed):
    path = indexed / "vault/DEMO/exercises/ex-01.md"
    assert codes(exercises.check_path(path)) == set()
    path.write_text(path.read_text().replace("(método paso 3)", "(método paso 7)"))
    assert "step-outside-method" in codes(exercises.check_path(path))


def test_html_exercise_meta_is_checked(indexed):
    ex = Exercise(kicker="DEMO · Clase 01", title=r"\(I = V/R\)", sub="Corriente",
                  method="ohm-current", classes=[1],
                  steps=[Step(title="Datos", method_step=1, rows=[Row("V = 20", "dato")]),
                         Step(title="Sustituir", method_step=3, rows=[Row("I = 2", "")]),
                         Step(title="Despejar", method_step=2)],
                  answer=["I = 2\\,A"], sources=["Clase 1, p. 2"])
    out = indexed / "vault/DEMO/exercises/guide.html"
    write([ex], out, subject="DEMO", offline_math=False)
    found = exercises.check_path(out)
    assert "wrong-order" in codes(found)
    assert exercises.read_meta(out)["exercises"][0]["method"] == "ohm-current"


def test_missing_method_blocks(indexed):
    path = indexed / "vault/DEMO/exercises/ex-02.md"
    path.write_text("---\nmethod: does-not-exist\nsubject: DEMO\n---\n\n## Solución\n\nx\n")
    assert "missing-method" in codes(exercises.check_path(path))


def test_report_feeds_status(indexed):
    path = indexed / CLASS
    path.write_text(path.read_text().replace("multiplicada por", "dividida entre"))
    found = checks.check_subject("DEMO")
    checks.write_report(found, "all")
    assert checks.counts_for(path)["errors"] >= 1


def test_repeated_citation_is_fixed_keeping_the_last(indexed):
    path = indexed / CLASS
    path.write_text(path.read_text().replace(
        "El voltaje es igual a la corriente por la resistencia.[^c1]",
        "El voltaje es igual a la corriente por la resistencia.[^c1] Se mide en voltios.[^c1]"))
    found = citations.check_paths([path])
    rep = [f for f in found if f.code == "repeated-citation"]
    assert len(rep) == 1 and rep[0].fix == {"old": "[^c1]", "new": ""}
    checks.apply_fixes(rep)
    assert "resistencia. Se mide en voltios.[^c1]" in path.read_text()
    assert "repeated-citation" not in codes(citations.check_paths([path]), "warning")


def test_claude_examples_and_analogies_need_no_citation(indexed):
    path = indexed / CLASS
    path.write_text(path.read_text().replace(
        "## Explicación\n",
        "## Explicación\n\n> [!analogy]\n> Piensa en una manguera: la presión empuja el agua.\n\n"))
    assert "uncited-paragraph" not in codes(citations.check_paths([path]))
