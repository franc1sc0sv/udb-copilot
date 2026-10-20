import asyncio
import json

from udb import migrate, setup
from udb.agent import guards, prompts
from udb.core import notes, settings
from udb.integrations.recordings import radar


def test_guard_blocks_sources_but_allows_git(home):
    deny = guards.check_pre("Read", {"file_path": str(home / "vault/DEMO/sources/x.pdf")}, home)
    assert deny and "source material" in deny
    assert guards.check_pre("Bash", {"command": "cat vault/DEMO/derived/text/a.jsonl"}, home)
    assert guards.check_pre("Bash", {"command": "python -c 'open(\"vault/DEMO/sources/a\")'"}, home)
    assert guards.check_pre("Bash", {"command": "git add vault/DEMO/derived"}, home) is None
    assert guards.check_pre("Glob", {"pattern": "vault/*/sources/**"}, home)


def test_guard_blocks_classroom_and_secrets(home):
    assert guards.check_pre("Bash", {"command": "curl https://moodle.example.edu/x"}, home)
    assert guards.check_pre("WebFetch", {"url": "https://moodle.example.edu/course"}, home)
    assert guards.check_pre("Read", {"file_path": "/home/u/.config/udb/moodle-token"}, home)
    assert guards.check_pre("Bash", {"command": "echo $MOODLE_TOKEN"}, home)
    assert guards.check_pre("Bash", {"command": "grep -r MOODLE_TOKEN src/"}, home) is None
    assert guards.check_pre("Bash", {"command": "udb status DEMO"}, home) is None


def test_post_hook_blocks_bad_note(indexed):
    path = indexed / "vault/DEMO/classes/01-2026-01-10/class.md"
    path.write_text(path.read_text().replace("multiplicada por", "dividida entre"))
    out = guards.check_post({"file_path": str(path)})
    assert out and out["decision"] == "block"


def test_agents_markdown_has_frontmatter():
    md = prompts.agent_markdown("scribe")
    assert md.startswith("---\nname: scribe") and "Vault rules" in md
    assert "mcp__vault__method_get" in md


def test_init_and_setup_claude(tmp_path, monkeypatch):
    monkeypatch.delenv("UDB_HOME", raising=False)
    home = setup.init(tmp_path / "data")
    assert (home / "udb.yaml").exists() and (home / "config/mail.yaml").exists()
    assert (home / ".claude/skills/udb-digest/SKILL.md").exists()
    assert (home / ".claude/agents/methodist.md").exists()
    hooks = json.loads((home / ".claude/settings.json").read_text())["hooks"]
    assert "udb hook pre" in hooks["PreToolUse"][0]["hooks"][0]["command"]
    assert json.loads((home / ".mcp.json").read_text())["mcpServers"]["vault"]["command"] == "udb"
    (home / "CLAUDE.md").write_text((home / "CLAUDE.md").read_text() + "\nMy own notes.\n")
    setup.setup_claude(home)
    text = (home / "CLAUDE.md").read_text()
    assert text.count("udb:start") == 1 and "My own notes." in text
    assert len(json.loads((home / ".claude/settings.json").read_text())["hooks"]["PreToolUse"]) == 1
    settings.reset()


def test_migrate_rewrites_legacy_keys(home):
    changed = migrate.run()
    assert any("class.md" in c for c in changed)
    front = notes.split_front_matter(
        (home / "vault/DEMO/classes/01-2026-01-10/class.md").read_text())[0]
    assert front["subject"] == "DEMO" and "asignatura" not in front
    assert '"class": 1' in (home / "vault/DEMO/registry.jsonl").read_text()
    task = notes.split_front_matter(
        (home / "cycles/2026-1/DEMO/tasks/01-tarea-1/TASK.md").read_text())[0]
    assert task["methods"] == ["ohm-current"] and task["status"] == "todo"
    assert migrate.run() == []


def test_radar_scores_exam_talk():
    points, why = radar.score("El parcial es el 12 de octubre y vale 30%")
    assert points >= 8 and why["dates"] and why["percents"]


def test_mcp_server_lists_every_tool(home):
    from udb.server.app import TOOL_NAMES, server
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == set(TOOL_NAMES)
