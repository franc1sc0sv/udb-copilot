WORDS_PER_CHUNK = 220
OVERLAP_WORDS = 40


def _windows(words: list[str]) -> list[tuple[int, int]]:
    if not words:
        return []
    step = max(WORDS_PER_CHUNK - OVERLAP_WORDS, 1)
    spans = []
    start = 0
    while start < len(words):
        end = min(start + WORDS_PER_CHUNK, len(words))
        spans.append((start, end))
        if end == len(words):
            break
        start += step
    return spans


def chunk_pages(pages: list[dict]) -> list[dict]:
    out = []
    for page in pages:
        text = page.get("text", "")
        words = text.split()
        base = page.get("char_start", 0)
        for start, end in _windows(words):
            piece = " ".join(words[start:end])
            offset = len(" ".join(words[:start]))
            offset = offset + 1 if start else 0
            out.append({
                "text": piece,
                "page": page.get("page"),
                "char_start": base + offset,
                "char_end": base + offset + len(piece),
            })
    return out


def chunk_segments(segments: list[dict]) -> list[dict]:
    out = []
    buffer: list[dict] = []
    count = 0
    for seg in segments:
        buffer.append(seg)
        count += len(seg.get("text", "").split())
        if count >= WORDS_PER_CHUNK:
            out.append(_join(buffer))
            keep = max(len(buffer) // 4, 1)
            buffer = buffer[-keep:]
            count = sum(len(s.get("text", "").split()) for s in buffer)
    if buffer:
        out.append(_join(buffer))
    return out


def _join(segments: list[dict]) -> dict:
    return {
        "text": " ".join(s.get("text", "").strip() for s in segments).strip(),
        "t_start": segments[0].get("start"),
        "t_end": segments[-1].get("end"),
    }
