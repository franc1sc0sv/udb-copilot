"""Citation anchors: `[^c1]: SRC-IRD-0003 | page=14 | quote="..."`."""
import re
from dataclasses import dataclass, field

REF_RE = re.compile(r"\[\^([A-Za-z0-9_-]+)\](?!:)")
DEF_RE = re.compile(r"^\[\^([A-Za-z0-9_-]+)\]:\s*(.+)$")
FIELD_RE = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|(\S+))')
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})$")
SOURCE_ID_RE = re.compile(r"^SRC-[A-Z0-9]+-\d{4}$")

# Locators the verifier can actually check; an anchor that cannot be checked is
# rejected. `frame=` (a board still of a recording) is checked against the text read
# from that still, so it always travels with `t=`.
LOCATORS = ("page", "t", "url", "frame")


@dataclass
class Anchor:
    key: str
    line: int
    raw: str
    source_id: str | None = None
    is_model: bool = False
    fields: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    @property
    def quote(self) -> str:
        return self.fields.get("quote", "")


def to_seconds(value: str) -> float | None:
    m = TIME_RE.match(value.strip())
    if not m:
        return None
    h, mnt, s = (int(g) for g in m.groups())
    return h * 3600 + mnt * 60 + s


def parse_window(value: str) -> tuple[float, float] | None:
    if "-" not in value:
        return None
    start, _, end = value.partition("-")
    a, b = to_seconds(start), to_seconds(end)
    if a is None or b is None or b < a:
        return None
    return a, b


def parse_definition(key: str, body: str, line: int) -> Anchor:
    anchor = Anchor(key=key, line=line, raw=body)
    head, _, rest = body.partition("|")
    head = head.strip()

    for m in FIELD_RE.finditer(rest):
        anchor.fields[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)

    if head.upper() == "MODEL":
        anchor.is_model = True
        if not anchor.fields.get("reason"):
            anchor.error = "unjustified-model-claim: missing reason="
        elif not anchor.fields.get("basis"):
            anchor.error = "unjustified-model-claim: missing basis="
        return anchor

    if not SOURCE_ID_RE.match(head):
        anchor.error = f"malformed-anchor: invalid source id '{head}'"
        return anchor

    anchor.source_id = head
    if not anchor.quote:
        anchor.error = 'malformed-anchor: missing quote="..."'
        return anchor

    if not set(LOCATORS) & set(anchor.fields):
        anchor.error = "malformed-anchor: missing a locator (page=, t=, frame= or url=)"
    elif "frame" in anchor.fields and not anchor.fields["frame"].isdigit():
        anchor.error = f"malformed-anchor: frame={anchor.fields['frame']} is not a number"
    return anchor


def parse(text: str) -> tuple[dict[str, Anchor], set[str]]:
    definitions: dict[str, Anchor] = {}
    used: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        m = DEF_RE.match(line.strip())
        if m:
            definitions[m.group(1)] = parse_definition(m.group(1), m.group(2), number)
        else:
            used.update(REF_RE.findall(line))
    return definitions, used


def format_anchor(key: str, source_id: str, quote: str, page: int | None = None,
                  t_start: float | None = None, t_end: float | None = None,
                  url: str | None = None, retrieved: str | None = None,
                  frame: int | None = None) -> str:
    parts = [source_id]
    if page is not None:
        parts.append(f"page={page}")
    if t_start is not None and t_end is not None:
        parts.append(f"t={hhmmss(t_start)}-{hhmmss(t_end)}")
    if frame is not None:
        parts.append(f"frame={frame}")
    if url:
        parts.append(f"url={url}")
    if retrieved:
        parts.append(f"retrieved={retrieved}")
    # One line per definition: board text and passages may carry line breaks.
    clean = re.sub(r"\s+", " ", quote.replace('"', "'")).strip()
    parts.append(f'quote="{clean}"')
    return f"[^{key}]: " + " | ".join(parts)


def hhmmss(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"
