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


PASSAGE_MAX_SENTENCES = 3
PASSAGE_MIN_WORDS = 8
PASSAGE_MAX_WORDS = 90
# A line break also ends a "sentence": board text is one line per board line.
_SENTENCE_END = re.compile(r"(?<=[.!?:;])\s+|\s*\n\s*")


def passage(text: str, substring: str = "", sentences: int = PASSAGE_MAX_SENTENCES) -> str:
    """Whole sentences of `text` that hold `substring` (or open the text), grown to at
    least PASSAGE_MIN_WORDS and at most `sentences` sentences / PASSAGE_MAX_WORDS words.
    The result is a verbatim slice of `text`, so it can be quoted and verified."""
    spans, start = [], 0
    for m in _SENTENCE_END.finditer(text):
        spans.append((start, m.start()))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    if not spans:
        return text.strip()
    # Chunks are word windows and may open mid-sentence: start at a sentence start.
    first = next((i for i, (a, _) in enumerate(spans)
                  if re.match(r"[A-ZÁÉÍÓÚÑ¿¡0-9\\(\[]", text[a:a + 2])), 0)
    if substring:
        hit = normalize(text).find(normalize(substring))
        # normalize() keeps length for the common cases; fall back to the first sentence.
        if hit >= 0:
            first = next((i for i, (a, b) in enumerate(spans) if a <= hit < b + 1), 0)
    last = first
    while True:
        words = len(text[spans[first][0]:spans[last][1]].split())
        if substring:
            covered = normalize(substring) in normalize(text[spans[first][0]:spans[last][1]])
        else:
            covered = True
        if (covered and words >= PASSAGE_MIN_WORDS) or last + 1 >= len(spans) \
                or last - first + 1 >= sentences:
            break
        if len(text[spans[first][0]:spans[last + 1][1]].split()) > PASSAGE_MAX_WORDS and covered:
            break
        last += 1
    return text[spans[first][0]:spans[last][1]].strip()


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
