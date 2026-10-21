"""Canonical keys and values for everything the engine parses.

Vault files use English keys (`subject`, `class`, `status: conflict`); their text
content is Spanish. Values are compared lowercase.
"""
from __future__ import annotations

KINDS = ("engineering", "math", "physics", "programming", "humanities", "general")
METHOD_STATES = ("confirmed", "provisional", "conflict")
CITATION_MODES = ("free", "normal", "strict")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
LOWERCASE_VALUES = ("status", "citations", "clarity", "kind", "type")


def normalize_front(front: dict) -> dict:
    """Front matter with lowercase enum values."""
    out = dict(front or {})
    for key in LOWERCASE_VALUES:
        if isinstance(out.get(key), str):
            out[key] = out[key].lower()
    if "slug" in out and "method" not in out and out.get("type") == "method":
        out["method"] = out["slug"]
    return out


def normalize_subject(raw: dict) -> dict:
    s = dict(raw)
    kind = str(s.get("kind") or "general").lower()
    s["kind"] = kind if kind in KINDS else "general"
    s["days"] = [str(d).lower()[:3] for d in s.get("days") or []]
    s["code"] = str(s["code"]).upper()
    return s
