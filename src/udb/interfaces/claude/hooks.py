"""Claude Code hooks, in one place.

`udb hook pre` (PreToolUse) blocks three things:
1. opening course originals (`vault/*/sources`, `vault/*/derived`): cite via the tools;
2. reading secret values (tokens, credentials, cookies, .env files);
3. reaching the virtual classroom by browser, curl, wget or a fetch tool.

`udb hook post` (PostToolUse on Write/Edit) runs the vault checks on the file
just written and blocks on errors so Claude fixes them.

The hook command in settings.json fails closed: if `udb` cannot run, the
tool call is blocked instead of silently allowed.
"""
import json
import re
import shlex
import sys
from pathlib import Path

from udb.config import settings

SECRET_PATH_RE = re.compile(
    r"(^|/)(\.env(\.[\w-]+)?|id_rsa|id_ed25519|[\w.-]*\.pem|moodle-token|cookies\.txt|"
    r"state\.json|mail-[\w-]+\.json|credentials/[^/\s]+\.json)$", re.IGNORECASE)
SECRET_CMD_RE = re.compile(r"\b(printenv|env)\s*($|\|)|\becho\s+\$\{?(MOODLE_TOKEN|UNI_PASS|"
                           r"[A-Z_]*(TOKEN|SECRET|PASSWORD|KEY)[A-Z_]*)\b")
PROTECTED_RE = re.compile(r"(^|/)vault/[^/\s]+/(sources|derived)(/|\b)")
BROWSER_TOOLS = re.compile(r"^(mcp__chrome__(navigate_page|new_page)|"
                           r"mcp__claude-in-chrome__(navigate|tabs_create_mcp)|WebFetch)$")
# Commands that can read or copy a file's content. `git`, `ls` and `du` are fine.
READ_CMD_RE = re.compile(r"\b(cat|head|tail|less|more|bat|sed|awk|grep|rg|strings|xxd|od|cp|mv|"
                         r"tar|zip|base64|python[\d.]*|node|jq|pdftotext|pdftoppm|vim?|nano|"
                         r"code|open|xdg-open|wslview|ffmpeg|ffprobe|dd|install)\b")
NET_CMD_RE = re.compile(r"\b(curl|wget|xdg-open|wslview|chromium|google-chrome|firefox|"
                        r"playwright|selenium|httpie|http)\b")

USE_TOOLS = ("Use mcp__vault__vault_search to find the chunk and mcp__vault__vault_quote "
             "to get the exact text with its anchor.")
USE_UDB = ("The classroom (Moodle) is read only through udb: mcp__vault__moodle_assignments, "
           "status, agenda, digest, or `udb sync`. Never with a browser. If a fact is missing, "
           "say so.")


def classroom_domains() -> list[str]:
    try:
        return settings.get().institution.get("guard_domains", [])
    except settings.HomeNotFound:
        return ["udbvirtual.edu.sv"]


def _hits_classroom(text: str) -> bool:
    return any(d.lower() in text.lower() for d in classroom_domains())


def _protected(text: str, cwd: Path) -> str | None:
    from udb.config.paths import is_protected

    for token in re.split(r"[\s'\"=<>|;&()]+", text):
        if not token:
            continue
        if PROTECTED_RE.search(token):
            return token
        try:
            if is_protected(token, cwd):
                return token
        except settings.HomeNotFound:
            return None
    return None


def check_pre(tool: str, args: dict, cwd: Path) -> str | None:
    """Reason to block the call, or None."""
    blob = json.dumps(args, ensure_ascii=False)
    if BROWSER_TOOLS.match(tool) and _hits_classroom(blob):
        return f"Do not open the classroom in a browser. {USE_UDB}"

    if tool == "Bash":
        command = args.get("command", "")
        if _hits_classroom(command) and NET_CMD_RE.search(command):
            return f"Do not reach the classroom over the network by hand. {USE_UDB}"
        if SECRET_CMD_RE.search(command):
            return "This command would print a secret. Reading secret values is forbidden."
        try:
            words = shlex.split(command)
        except ValueError:
            words = command.split()
        if any(SECRET_PATH_RE.search(w) for w in words):
            return "That file holds a secret. Its content is not read."
        hit = _protected(command, cwd) if READ_CMD_RE.search(command) else None
        if hit:
            return f"'{hit}' is course source material. {USE_TOOLS}"
        return None

    if tool in ("Read", "Grep", "Glob", "NotebookEdit", "Edit", "Write"):
        targets = [args.get(k) for k in ("file_path", "path", "notebook_path", "pattern", "glob")]
        for target in filter(None, targets):
            if tool in ("Read", "NotebookEdit") and SECRET_PATH_RE.search(str(target)):
                return "That file holds a secret. Its content is not read."
            if tool in ("Read", "Grep", "Glob", "NotebookEdit"):
                hit = _protected(str(target), cwd)
                if hit:
                    return f"'{hit}' is course source material and cannot be opened. {USE_TOOLS}"
    return None


def check_post(args: dict) -> dict | None:
    """Hook output for a written file, or None when it is clean."""
    from udb.config.paths import vault
    from udb.domain import checks

    raw = args.get("file_path") or args.get("path")
    if not raw:
        return None
    path = Path(raw)
    try:
        path.resolve().relative_to(vault())
    except (ValueError, settings.HomeNotFound):
        return None
    if not path.exists() or path.suffix not in (".md", ".html"):
        return None
    found = checks.check_file(path)
    errors = [f for f in found if f.level == "error"]
    if errors:
        detail = "\n".join(str(f) for f in errors)
        return {"decision": "block", "reason":
                f"The file breaks the vault rules. Fix it before going on.\n\n{detail}\n\n"
                "Every claim needs its anchor from mcp__vault__vault_quote; sentences of 25 "
                "words or fewer; a solution step is valid only if it comes from the teacher's "
                "method."}
    warnings = [f for f in found if f.level == "warning"]
    if warnings:
        return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
                                       "Warnings:\n" + "\n".join(str(w) for w in warnings[:10])
                                       + (f"\n(+{len(warnings) - 10} more)" if len(warnings) > 10
                                          else "")}}
    return None


def run(event: str) -> int:
    """Entry point of `udb hook pre|post`: reads the hook JSON from stdin."""
    payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    tool = payload.get("tool_name", "")
    args = payload.get("tool_input") or {}
    cwd = Path(payload.get("cwd") or ".")
    if event == "pre":
        reason = check_pre(tool, args, cwd)
        if reason:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": reason}}))
        return 0
    if event == "session":
        return session_start()
    if event == "prompt":
        return prompt_context(payload.get("prompt", ""))
    out = check_post(args)
    if out:
        print(json.dumps(out))
    return 0


SYNC_TIMEOUT = 150   # seconds; a full sync takes about 35


def session_start() -> int:
    """Build the search index when a fresh clone (cloud session) has none, then sync the
    classroom: every session starts with Moodle up to date and says what was left out."""
    import os
    import shutil
    import subprocess

    from udb.domain.sources import index

    try:
        if index.is_empty():
            counts = index.reindex_all()
            print(f"udb: search index built ({sum(counts.values())} chunks).")
        if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
            return 0
        from udb.config.paths import index_dir, load_subjects
        from udb.integrations.moodle import sync as ms

        exe = shutil.which("udb")
        if not exe or not any(s.get("moodle_course_id") for s in load_subjects()):
            return 0
        try:
            with (index_dir() / "sync.log").open("w", encoding="utf-8") as log:
                done = subprocess.run([exe, "sync"], stdout=log, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL, timeout=SYNC_TIMEOUT)
            ok = done.returncode == 0
        except subprocess.TimeoutExpired:
            ok = False
        if not ok:
            print("udb: Moodle sync FAILED or timed out (see index/sync.log). Say so to the "
                  "student; do not assume the vault is up to date.")
            return 0
        gaps = sum(len(v) for v in ms.last_sync().get("gaps", {}).values())
        print(f"udb: Moodle synced. {gaps} item(s) left out (see `udb sync` or index/sync.log).")
    except settings.HomeNotFound:
        pass
    return 0


CLASSROOM_RE = re.compile(
    r"\b(tareas?|pendientes?|entregas?|entregar|parcial(es)?|ex[aá]men(es)?|pruebas?|quiz|"
    r"foros?|aula|moodle|vence|vencen|fecha|deadline|due|assignments?|homework|notas?|"
    r"calificaci[oó]n|agenda|hoy|ma[ñn]ana|semana|horario|evaluaci[oó]n|desaf[ií]o|gu[ií]a)\b",
    re.IGNORECASE)
CACHE_MINUTES = 30


def prompt_context(prompt: str) -> int:
    """Classroom questions always get the real classroom state, so it is never skipped.

    Runs the digest (no model) and injects it as context. Cached for 30 minutes
    in index/classroom_cache.json so repeated questions stay fast.
    """
    import time

    if not CLASSROOM_RE.search(prompt or ""):
        return 0
    try:
        from udb.config.paths import index_dir
        from udb.domain.planning import digest

        cache = index_dir() / "classroom_cache.json"
        data = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        if time.time() - data.get("at", 0) > CACHE_MINUTES * 60:
            built = digest.build(hours=24)
            data = {"at": time.time(), "checked": built["generated"],
                    "text": digest.as_text(built)}
            cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        context = (f"Classroom state checked by udb at {data['checked']} (Moodle, mail, routes; "
                   "no model). Use it; call the digest or moodle_assignments tool for detail.\n\n"
                   + data["text"])
    except settings.HomeNotFound:
        return 0
    except Exception as exc:  # noqa: BLE001 - tell Claude the check failed instead of hiding it
        context = (f"udb could not check the classroom ({type(exc).__name__}: {exc}). "
                   "Say so, and call moodle_assignments before answering about deadlines.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                             "additionalContext": context}}, ensure_ascii=False))
    return 0
