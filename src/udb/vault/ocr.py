"""Text inside images: scanned PDF pages and figures of the course site.

Uses RapidOCR (CPU, the `ocr` extra). Without it the engine still works: the
source report says which pages need OCR and the command that adds it.
"""
from functools import lru_cache

MIN_CONFIDENCE = 0.5


class OcrUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise OcrUnavailable("OCR engine missing: reinstall udb-copilot") from exc
    return RapidOCR()


def available() -> bool:
    try:
        _engine()
        return True
    except OcrUnavailable:
        return False


def read(image: bytes) -> str:
    """Text lines of an image, top to bottom. Empty string when there is none."""
    result, _ = _engine()(image)
    lines = [(box[0][1], box[0][0], text) for box, text, score in (result or [])
             if text.strip() and float(score) >= MIN_CONFIDENCE]
    lines.sort(key=lambda r: (round(r[0] / 12), r[1]))
    return "\n".join(t for _, _, t in lines)
