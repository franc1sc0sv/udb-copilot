"""Run Claude from the CLI (`udb class write`, `udb study`...) with the vault tools.

Needs the `agent` extra (claude-agent-sdk). The vault MCP server runs as a
child process, exactly as Claude Code runs it.
"""
import asyncio
import sys

from udb.config import settings
from udb.domain.study import ledger
from udb.interfaces.claude import prompts
from udb.interfaces.mcp.vault import TOOL_NAMES

BASE_TOOLS = ["Write", "Edit", "Glob", "TodoWrite", "Agent", "WebSearch", "AskUserQuestion"]
DEFAULT_MODEL = "opus"
LANGUAGES = {"es": "Spanish", "en": "English"}


def _sdk():
    try:
        import claude_agent_sdk
    except ImportError as exc:
        raise RuntimeError("this command needs the agent extra: "
                           "uv tool install 'udb-copilot[agent]'") from exc
    return claude_agent_sdk


def options(model: str = DEFAULT_MODEL, budget: float = 2.0, resume: str | None = None,
            max_turns: int | None = None, permission_mode: str = "acceptEdits"):
    sdk = _sdk()
    home = settings.get().home
    agents = {name: sdk.AgentDefinition(description=spec["description"],
                                        prompt=prompts.agent_prompt(name),
                                        tools=spec["tools"], model=spec["model"])
              for name, spec in prompts.AGENTS.items()}
    return sdk.ClaudeAgentOptions(
        cwd=str(home), model=model,
        system_prompt={"type": "preset", "preset": "claude_code", "append": prompts.RULES + (
            "\n\nThe student reads your messages in "
            f"{LANGUAGES.get(settings.get().language, settings.get().language)}: "
            "write every message and the final report in that language.")},
        setting_sources=["project"],
        mcp_servers={"vault": {"type": "stdio", "command": sys.executable,
                               "args": ["-m", "udb.interfaces.mcp.vault"],
                               "env": {"UDB_HOME": str(home)}}},
        agents=agents,
        allowed_tools=BASE_TOOLS + [f"mcp__vault__{t}" for t in TOOL_NAMES],
        disallowed_tools=["WebFetch"], permission_mode=permission_mode,
        max_budget_usd=budget, max_turns=max_turns, resume=resume)


async def run(prompt: str, opts, on_text=None, subject: str | None = None) -> dict:
    sdk = _sdk()
    result = {"text": "", "cost": 0.0, "session_id": None, "error": None}
    async for message in sdk.query(prompt=prompt, options=opts):
        if isinstance(message, sdk.AssistantMessage):
            for block in message.content:
                if isinstance(block, sdk.TextBlock) and on_text:
                    on_text(block.text)
        elif isinstance(message, sdk.ResultMessage):
            result["session_id"] = message.session_id
            result["cost"] = message.total_cost_usd or 0.0
            if message.subtype == "success":
                result["text"] = message.result or ""
            else:
                result["error"] = message.subtype
    if subject and result["session_id"]:
        ledger.save_session(subject, result["session_id"])
    return result


def go(prompt: str, subject: str | None = None, **kwargs) -> dict:
    printed = {"any": False}

    def echo(text: str) -> None:
        printed["any"] = True
        print(text, end="", flush=True)

    result = asyncio.run(run(prompt, options(**kwargs), on_text=echo, subject=subject))
    if printed["any"]:
        print()
    return result


async def chat(opening: str, subject: str | None = None, **kwargs) -> None:
    sdk = _sdk()
    async with sdk.ClaudeSDKClient(options=options(**kwargs)) as client:
        await client.query(opening)
        while True:
            async for message in client.receive_response():
                if isinstance(message, sdk.AssistantMessage):
                    for block in message.content:
                        if isinstance(block, sdk.TextBlock):
                            print(block.text, end="", flush=True)
                elif isinstance(message, sdk.ResultMessage):
                    print(f"\n\n[cost {message.total_cost_usd or 0:.3f} USD]")
                    if subject and message.session_id:
                        ledger.save_session(subject, message.session_id)
            try:
                reply = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if reply.lower() in {"salir", "exit", "quit", ""}:
                return
            await client.query(reply)
