"""How well each source was read, and what to do about the rest.

Claude asks this instead of guessing. A source is one of:

- ok            all its pages have text
- needs-ocr     scanned pages with no text layer yet
- images        an HTML page whose figures were not downloaded or read yet
- embeds        a page with embedded videos or widgets whose content is not read yet
- no-text       nothing could be extracted (a video link, an empty page)
- unsupported   a format the engine does not read (.rar, .zip...)
- transcript    a recording with its transcript
- missing       the registry points at a file that is not there
"""
from udb.config.paths import subject_codes, subject_dir
from udb.domain.sources import index, ingest, ocr, registry

ADVICE = {
    "needs-ocr": "udb sources fix {sid}",
    "images": "udb sources fix {sid}",
    "unsupported": "extract it by hand and run: udb ingest {code} <file>",
    "no-text": "nothing to read; look at the source title or URL",
    "missing": "the file is gone; download it again (udb sync {code})",
    "stale": "udb sources fix {sid}",
    "embeds": "{embed_advice}",
}


def health(code: str, rec: dict) -> dict:
    sid = rec["id"]
    path = subject_dir(code) / rec["path"]
    suffix = path.suffix.lower()
    pages = index.load_pages(code, sid)
    meta = ingest.load_meta(code, sid)
    text_pages = [p for p in pages if p.get("kind") != "figure"]
    chars = sum(len(p["text"]) for p in text_pages)
    empty = [p["page"] for p in text_pages if len(p["text"].strip()) < ingest.EMPTY_PAGE]
    images = meta.get("images", [])
    read_images = sum(1 for i in images if i.get("status") == "done")
    unread, videos = _unread_embeds(meta.get("embeds", []))
    row = {"id": sid, "subject": code, "title": rec.get("title"), "type": suffix.lstrip("."),
           "class": rec.get("class"), "pages": len(text_pages), "chars": chars,
           "empty_pages": len(empty), "ocr_pages": sum(1 for p in pages if p.get("ocr")),
           "images": len(images), "images_read": read_images,
           "embeds": len(meta.get("embeds", [])), "embeds_unread": len(unread),
           "superseded": bool(rec.get("superseded_by"))}
    if not path.exists():
        state = "missing"
    elif index.load_segments(code, sid):
        state = "transcript"
    elif suffix in ingest.UNSUPPORTED:
        state = "unsupported"
    elif pages and meta.get("extractor") != ingest.EXTRACTOR:
        state = "stale"
    elif meta.get("needs_ocr"):
        state = "needs-ocr"
    elif chars < ingest.EMPTY_PAGE:
        state = "no-text"
    elif images and read_images < len(images):
        state = "images"
    elif unread:
        state = "embeds"
    else:
        state = "ok"
    row["state"] = state
    advice = (f"udb recording process {' '.join(videos[:3])}" if videos
              else "embedded widget: open the course page to see it")
    row["fix"] = ADVICE.get(state, "").format(sid=sid, code=code, embed_advice=advice) or None
    return row


def _unread_embeds(embeds: list[dict]) -> tuple[list[dict], list[str]]:
    """Embedded content whose text is not in the vault: YouTube videos not processed yet
    (by catalog id) and any other widget (H5P, Genially...)."""
    from udb.integrations.media import catalog
    by_key = {catalog.url_key(g["url"]): g for g in catalog.load()}
    unread, videos = [], []
    for e in embeds:
        g = by_key.get(catalog.url_key(e.get("src") or ""))
        if g and g.get("source_id"):
            continue
        unread.append(e)
        if g:
            videos.append(g["id"])
    return unread, videos


def report(code: str | None = None, source_id: str | None = None) -> list[dict]:
    if source_id:
        rec = registry.lookup(source_id)
        return [health(registry.subject_of(source_id), rec)] if rec else []
    return [health(c, rec) for c in ([code.upper()] if code else subject_codes())
            for rec in registry.read_all(c) if not rec.get("superseded_by")]


def fix(code: str | None = None, source_id: str | None = None, images: bool = True,
        progress=None) -> list[dict]:
    """Re-extract stale sources, OCR scanned pages, download and read HTML figures."""
    out = []
    for row in report(code, source_id):
        if row["state"] not in ("stale", "needs-ocr", "images") and not source_id:
            continue
        if progress:
            progress(row)
        sub = row["subject"]
        try:
            ingest.index_source(sub, row["id"])
            if images and row["type"] in ("html", "htm"):
                ingest.fetch_images(sub, row["id"])
            out.append({**health(sub, registry.get(sub, row["id"])), "error": None})
        except Exception as exc:  # noqa: BLE001 - report per source and keep going
            out.append({**row, "error": f"{type(exc).__name__}: {exc}"})
    return out


def summary(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return {"sources": len(rows), "by_state": counts, "ocr_available": ocr.available(),
            "images": sum(r["images"] for r in rows),
            "images_read": sum(r["images_read"] for r in rows),
            "embeds": sum(r["embeds"] for r in rows),
            "embeds_unread": sum(r["embeds_unread"] for r in rows)}
