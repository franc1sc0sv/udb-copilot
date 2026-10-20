"""`udb init` and `udb setup claude`: create a data home and wire Claude Code into it.

The engine ships the skills, agents, hooks and CLAUDE.md. Setup copies them
into the data repo's `.claude/` (and `.mcp.json`), so they work the same in a
local session and in a cloud session that only clones the data repo.
Run `udb setup claude` again after upgrading udb.
"""
import json
import shutil
from importlib import resources
from pathlib import Path

import yaml

from .agent import prompts
from .core import settings

START, END = "<!-- udb:start -->", "<!-- udb:end -->"
MANAGED = ".udb-managed"

INSTALL_SPEC = "udb-copilot[outlook] @ git+https://github.com/franc1sc0sv/udb-copilot"
PATH_FIX = 'export PATH="$HOME/.local/bin:$PATH"; '
HOOK_PRE = (PATH_FIX + "command -v udb >/dev/null 2>&1 || { echo 'udb is not installed: "
            "blocking for safety' >&2; exit 2; }; udb hook pre")
HOOK_POST = PATH_FIX + "command -v udb >/dev/null 2>&1 || exit 0; udb hook post"
# In a cloud session (fresh container) install udb first, then build the index.
HOOK_SESSION = (PATH_FIX + 'if ! command -v udb >/dev/null 2>&1 && [ "$CLAUDE_CODE_REMOTE" = true ]; '
                f'then uv tool install -q "${{UDB_INSTALL_SPEC:-{INSTALL_SPEC}}}"; fi; '
                '[ -n "$CLAUDE_ENV_FILE" ] && echo \'export PATH="$HOME/.local/bin:$PATH"\' '
                '>> "$CLAUDE_ENV_FILE"; command -v udb >/dev/null 2>&1 && udb hook session; exit 0')
HOOK_PROMPT = PATH_FIX + "command -v udb >/dev/null 2>&1 || exit 0; udb hook prompt"
PRE_MATCHER = ("Read|Grep|Glob|Bash|NotebookEdit|WebFetch|mcp__chrome__.*|"
               "mcp__claude-in-chrome__.*")

SUBJECTS_EXAMPLE = {"subjects": [{
    "code": "IRD", "name": "Interconexión de Redes", "kind": "engineering", "term": "2026-2",
    "moodle_course_id": None, "days": ["tue", "thu"],
    "asr_vocabulary": "VLAN, VTP, IPv6, subred, router, switch, trunk"}]}
MAIL_EXAMPLE = {
    "accounts": [
        {"id": "personal", "provider": "gmail", "address": "you@gmail.com",
         "calendar": True, "drive": True, "send": True},
        {"id": "udb", "provider": "outlook", "address": "you@udb.edu.sv",
         "tenant": "organizations", "client_id": "<entra-app-client-id>"},
    ],
    "filters": [{"name": "teachers", "from_domains": ["udb.edu.sv"]},
                {"name": "classroom", "from": ["udbvirtual.edu.sv"]}],
}
GITIGNORE = """# udb: generated or local-only
index/*
!index/ledger.db
!index/recordings.json
.claude/settings.local.json
**/work/assembly-tmp/
**/work/chapters/
.env
.env.*
"""


def _assets() -> Path:
    return Path(str(resources.files("udb") / "assets" / "claude"))


def _merge_hooks(settings_path: Path) -> None:
    data = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    hooks = data.setdefault("hooks", {})

    def put(event: str, matcher: str | None, command: str) -> None:
        entries = [e for e in hooks.get(event, [])
                   if not any("udb hook" in h.get("command", "") or "guard.py" in
                              h.get("command", "") or "check_note.py" in h.get("command", "")
                              for h in e.get("hooks", []))]
        entry = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            entry = {"matcher": matcher, **entry}
        hooks[event] = entries + [entry]

    put("PreToolUse", PRE_MATCHER, HOOK_PRE)
    put("PostToolUse", "Write|Edit", HOOK_POST)
    put("SessionStart", None, HOOK_SESSION)
    put("UserPromptSubmit", None, HOOK_PROMPT)
    allow = data.setdefault("permissions", {}).setdefault("allow", [])
    for rule in ("mcp__vault__vault_search", "mcp__vault__vault_quote", "mcp__vault__status",
                 "mcp__vault__digest", "Bash(udb status:*)", "Bash(udb verify:*)"):
        if rule not in allow:
            allow.append(rule)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")


def _merge_mcp(path: Path, google: bool) -> None:
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.setdefault("mcpServers", {})["vault"] = {"command": "udb", "args": ["mcp"]}
    if google:
        # The Google Workspace MCP, with the same OAuth app and login as udb's Gmail.
        data["mcpServers"]["google-workspace"] = {"command": "udb", "args": ["google-mcp"]}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _merge_claude_md(path: Path, block: str) -> None:
    managed = f"{START}\n{block.strip()}\n{END}\n"
    if not path.exists():
        path.write_text(managed, encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    if START in text and END in text:
        text = text[:text.index(START)] + managed + text[text.index(END) + len(END) + 1:]
    else:
        text = managed + "\n" + text
    path.write_text(text, encoding="utf-8")


def setup_claude(home: Path) -> list[str]:
    """Write skills, agents, hooks, MCP config and the CLAUDE.md block into `home`."""
    done = []
    claude = home / ".claude"
    skills_dst = claude / "skills"
    skills_dst.mkdir(parents=True, exist_ok=True)
    for old in skills_dst.iterdir():
        if old.is_symlink() or (old / MANAGED).exists() or old.name.startswith("uni-"):
            shutil.rmtree(old) if old.is_dir() and not old.is_symlink() else old.unlink()
    for skill in (_assets() / "skills").iterdir():
        target = skills_dst / skill.name
        shutil.copytree(skill, target, dirs_exist_ok=True)
        (target / MANAGED).touch()
    done.append(f"{len(list((_assets() / 'skills').iterdir()))} skills")

    agents_dst = claude / "agents"
    agents_dst.mkdir(parents=True, exist_ok=True)
    for old in agents_dst.iterdir():
        if old.is_symlink():
            old.unlink()
    for name in prompts.AGENTS:
        (agents_dst / f"{name}.md").write_text(prompts.agent_markdown(name), encoding="utf-8")
    done.append(f"{len(prompts.AGENTS)} agents")

    _merge_hooks(claude / "settings.json")
    mail = home / "config" / "mail.yaml"
    accounts = (yaml.safe_load(mail.read_text(encoding="utf-8")) or {}).get("accounts", []) \
        if mail.exists() else []
    _merge_mcp(home / ".mcp.json", any(a.get("provider") == "gmail" for a in accounts))
    try:
        domain = settings.load(home).institution.get("guard_domains", ["the classroom"])[0]
    except (OSError, KeyError, IndexError):
        domain = "the classroom"
    block = (_assets() / "CLAUDE.md").read_text(encoding="utf-8").replace(
        "{moodle_domain}", domain)
    _merge_claude_md(home / "CLAUDE.md", block)
    done += ["hooks", ".mcp.json", "CLAUDE.md"]
    return done


def init(folder: Path) -> Path:
    """Create a new data home with example config. Existing files are kept."""
    folder = folder.expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / settings.MARKER
    if not marker.exists():
        marker.write_text(yaml.safe_dump({k: v for k, v in settings.DEFAULTS.items()},
                                         allow_unicode=True, sort_keys=False), encoding="utf-8")
    for sub in ("config", "vault", "cycles", "index"):
        (folder / sub).mkdir(exist_ok=True)
    examples = {"subjects.yaml": SUBJECTS_EXAMPLE, "mail.yaml": MAIL_EXAMPLE,
                "agenda.yaml": {"passing_grade": 6.0, "subjects": {}},
                "recordings.yaml": {"browser": "chrome", "model": "large", "quality": "max"}}
    for name, data in examples.items():
        path = folder / "config" / name
        if not path.exists():
            path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                            encoding="utf-8")
    gitignore = folder / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(GITIGNORE, encoding="utf-8")
    setup_claude(folder)
    settings.reset()
    return folder
