"""`udb verify --deep`: does each paragraph say what its passages say?

The model-free checks prove that every quote is really in the source. They
cannot prove that the paragraph around it is faithful. This asks a small Claude
model, once per paragraph, to compare the paragraph with the passages it cites:
supported, partial or unsupported, with a one-line reason. Research on these
judges (AutoAIS, ExpertQA) shows they miss real support often, so the result is
a warning, never an error. Verdicts are cached by the hash of the paragraph and
its passages in `index/deep.json`: a note is judged again only when it changes.
Needs the `agent` extra and a Claude login.
"""
import asyncio
import hashlib
import json
import re
from pathlib import Path

from udb.config.paths import index_dir, relative
from udb.domain.notes import anchors
from udb.domain.notes import document as notes
from udb.domain.notes.findings import Finding

MODEL = "haiku"
REF_RE = re.compile(r"\[\^([A-Za-z0-9_-]+)\]")
PROMPT = """You check study notes written in Spanish against the course material they cite.
For each item, decide whether the PARAGRAPH is backed by its PASSAGES (quoted from the
material): "supported" if everything the paragraph claims is in the passages or is a
faithful rewording of them; "partial" if some claim goes beyond them; "unsupported" if the
passages do not back the paragraph at all or contradict it. Ignore style, examples labelled
as such and formulas copied from the passages. Answer ONLY with a JSON array, one object per
item, in order: {"id": <id>, "verdict": "supported|partial|unsupported", "reason": "<one
short sentence in Spanish naming what is not backed>"}.

ITEMS:
"""


def _cache_path() -> Path:
    return index_dir() / "deep.json"


def _load_cache() -> dict:
    path = _cache_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def items_for(path: Path) -> list[dict]:
    """Paragraphs with at least one source citation, with their passages."""
    text = path.read_text(encoding="utf-8")
    note = notes.parse(relative(path), text)
    definitions, _ = anchors.parse(text)
    out = []
    for block in note.blocks:
        keys = list(dict.fromkeys(REF_RE.findall(block.text)))
        passages = [definitions[k].quote for k in keys
                    if k in definitions and definitions[k].source_id and not definitions[k].error]
        if not passages:
            continue
        paragraph = REF_RE.sub("", block.text).strip()
        digest = hashlib.sha1(json.dumps([paragraph, passages]).encode()).hexdigest()[:16]
        out.append({"id": digest, "line": block.start_line, "paragraph": paragraph,
                    "passages": passages})
    return out


async def _ask(items: list[dict]) -> list[dict]:
    try:
        import claude_agent_sdk as sdk
    except ImportError as exc:
        raise RuntimeError("--deep needs the agent extra: uv tool install "
                           "'udb-copilot[agent]'") from exc
    body = json.dumps([{"id": i["id"], "paragraph": i["paragraph"], "passages": i["passages"]}
                       for i in items], ensure_ascii=False, indent=1)
    opts = sdk.ClaudeAgentOptions(model=MODEL, allowed_tools=[], max_turns=1,
                                  system_prompt="You are a strict, literal fact checker.")
    answer = ""
    async for message in sdk.query(prompt=PROMPT + body, options=opts):
        if isinstance(message, sdk.ResultMessage) and message.subtype == "success":
            answer = message.result or ""
    match = re.search(r"\[.*\]", answer, re.S)
    return json.loads(match.group(0)) if match else []


def check_path(path: Path) -> list[Finding]:
    items = items_for(path)
    if not items:
        return []
    cache = _load_cache()
    todo = [i for i in items if i["id"] not in cache]
    if todo:
        for verdict in asyncio.run(_ask(todo)):
            if isinstance(verdict, dict) and verdict.get("id"):
                cache[verdict["id"]] = {"verdict": verdict.get("verdict"),
                                        "reason": verdict.get("reason", "")}
        _cache_path().write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    out = []
    for i in items:
        v = cache.get(i["id"]) or {}
        if v.get("verdict") in ("partial", "unsupported"):
            out.append(Finding(relative(path), i["line"], f"deep-{v['verdict']}",
                               f"{v.get('reason', '')} «{i['paragraph'][:70]}»",
                               level="warning"))
    return out
