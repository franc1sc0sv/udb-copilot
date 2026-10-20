import re
import unicodedata

WS = re.compile(r"\s+")
# Straight and curly double quotes all fold to the single quote: anchors store
# quotes with ' (a " would end the quote="..." field), so the source text must
# compare equal after the same folding.
QUOTES = str.maketrans({"“": "'", "”": "'", '"': "'", "‘": "'", "’": "'",
                        "«": "'", "»": "'", "–": "-", "—": "-"})


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def normalize(text: str) -> str:
    text = text.translate(QUOTES)
    text = strip_accents(text).lower()
    return WS.sub(" ", text).strip()


# Placeholders the extractor writes where an image or embedded object was. A quote
# may run across them, so matching ignores them.
MARKER_RE = re.compile(r"\s*\[(?:Figura \d+[^\]]*|Contenido incrustado[^\]]*)\]\s*")


def strip_markers(text: str) -> str:
    return MARKER_RE.sub(" ", text)


def contains(haystack: str, needle: str) -> bool:
    return normalize(strip_markers(needle)) in normalize(strip_markers(haystack))


def count_occurrences(haystack: str, needle: str) -> int:
    return normalize(strip_markers(haystack)).count(normalize(strip_markers(needle)))


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"(?<=[.!?:;])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])", text)
    return [p.strip() for p in parts if p.strip()]


def count_syllables_es(word: str) -> int:
    word = strip_accents(word).lower()
    groups = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in "aeiou"
        if is_vowel and not prev_vowel:
            groups += 1
        prev_vowel = is_vowel
    return max(groups, 1)


def slugify(text: str, limit: int = 60) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", strip_accents(text).lower()).strip("-")
    return base[:limit] or "item"
