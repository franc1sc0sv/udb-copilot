"""Turn source files into page text (`derived/text/<ID>.pages.jsonl`) and index it."""
import json
from pathlib import Path

from . import index, registry

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst"}
AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".mp4", ".mov", ".mkv", ".webm"}


def extract_pdf(path: Path) -> list[dict]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return [{"page": i + 1, "text": (p.extract_text() or "").strip()}
            for i, p in enumerate(reader.pages)]


def extract_pptx(path: Path) -> list[dict]:
    from pptx import Presentation

    pages = []
    for i, slide in enumerate(Presentation(str(path)).slides):
        parts = [sh.text_frame.text for sh in slide.shapes
                 if sh.has_text_frame and sh.text_frame.text.strip()]
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            parts.append(slide.notes_slide.notes_text_frame.text)
        pages.append({"page": i + 1, "text": "\n".join(parts).strip()})
    return pages


def extract_docx(path: Path) -> list[dict]:
    import docx

    blocks, current = [], []
    for para in docx.Document(str(path)).paragraphs:
        if para.style.name.startswith("Heading") and current:
            blocks.append("\n".join(current))
            current = []
        if para.text.strip():
            current.append(para.text)
    if current:
        blocks.append("\n".join(current))
    return [{"page": i + 1, "text": b} for i, b in enumerate(blocks)]


def extract_html(path: Path) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return [{"page": 1, "text": soup.get_text("\n", strip=True)}]


def extract_text(path: Path) -> list[dict]:
    parts = [p.strip() for p in path.read_text(encoding="utf-8", errors="replace").split("\n\n")
             if p.strip()]
    return [{"page": i + 1, "text": p} for i, p in enumerate(parts)]


EXTRACTORS = {".pdf": extract_pdf, ".pptx": extract_pptx, ".docx": extract_docx,
              ".html": extract_html, ".htm": extract_html}


def extract(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix in EXTRACTORS:
        return EXTRACTORS[suffix](path)
    if suffix in TEXT_SUFFIXES:
        return extract_text(path)
    raise ValueError(f"unsupported file type: {suffix}")


def write_pages(code: str, source_id: str, pages: list[dict]) -> Path:
    out = index.pages_file(code, source_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    cursor = 0
    lines = []
    for page in pages:
        text = page.get("text", "")
        lines.append(json.dumps({"page": page["page"], "text": text, "char_start": cursor,
                                 "char_end": cursor + len(text)}, ensure_ascii=False))
        cursor += len(text) + 1
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def index_source(code: str, source_id: str) -> int:
    path = registry.source_file(code, source_id)
    if path.suffix.lower() in AUDIO_SUFFIXES:
        if not index.transcript_file(code, source_id).exists():
            raise RuntimeError(f"{source_id} is audio and has no transcript. "
                               "Run: udb recording transcribe <id> (see udb recording board)")
    else:
        write_pages(code, source_id, extract(path))

    con = index.connect()
    try:
        index.upsert_source(con, registry.get(code, source_id))
        index.clear_source(con, source_id)
        count = index.add_chunks(con, source_id, code.upper(), index.chunks_for(code, source_id))
        con.commit()
    finally:
        con.close()
    return count


def ingest_file(code: str, path: str | Path, kind: str = "course", title: str | None = None,
                class_number: int | None = None, url: str | None = None) -> dict:
    rec = registry.register(code, Path(path), kind, title=title, class_number=class_number,
                            url=url)
    return {"source": rec, "chunks": index_source(code, rec["id"])}
