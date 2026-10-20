# Running udb in Claude Code on the web (and from your phone)

A cloud session clones your **private vault repo** into a fresh Linux container.
The vault's `.claude/` folder (written by `udb setup claude`) brings the skills,
agents, hooks and the `vault` MCP server. The `SessionStart` hook installs `udb`
when it is missing and builds the search index.

What works in the cloud: Moodle, mail, Calendar, Drive, search and citations,
`udb status`, `udb digest`, agenda, tasks, writing notes and exercises.
What stays on your computer: downloading recordings (needs your browser's
Microsoft session), GPU transcription, Packet Tracer.

## 1. Environment

In [claude.ai/code](https://claude.ai/code) → your vault repo → environment settings:

**Network access: Custom**, allowing:

```
www.udbvirtual.edu.sv
*.googleapis.com
oauth2.googleapis.com
accounts.google.com
login.microsoftonline.com
graph.microsoft.com
github.com
pypi.org
files.pythonhosted.org
registry.npmjs.org
```

Add your IMAP host if you use one.

**Environment variables** (only for you; never commit them):

| Variable | Value |
|---|---|
| `MOODLE_TOKEN` | the token from `~/.config/udb/moodle-token` on your computer |
| `GMAIL_PERSONAL_JSON` | the content of `~/.config/udb/mail-personal.json` (name it as `credentials_env` says) |
| `OUTLOOK_UDB_CACHE` | the content of `~/.config/udb/mail-udb.json`, base64-encoded |

Never put your UDB password in the cloud: only the token. If a Google refresh
token expires, run `udb mail login` again locally and update the variable.

**Setup script** (optional; the SessionStart hook does the same if you skip it):

```bash
#!/bin/bash
set -e
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv tool install "udb-copilot[outlook] @ git+https://github.com/franc1sc0sv/udb-copilot"
udb setup mathjax || true
```

## 2. Routines

Ask Claude, in a session on the vault repo, to create these with `/schedule`.

**Morning briefing, every day at 05:52:**

> Run `udb digest --json` in the vault. Write me an email in Spanish, warm and
> short, subject "Mañanita: tu día <date>": classes today, what is due in the
> next 72 hours in bold, the countdown to each evaluation with its weight, new
> classroom activity and teacher mail. Mention any source that failed. Send it
> to my Gmail with the Gmail connector.

**Change alerts, every 2 hours from 07:00 to 22:00:**

> Run `udb digest --alerts --hours 2 --json`. If `empty` is true, do nothing.
> Otherwise email me "Novedades en el aula" with each new item in one line.

Without a model, the same emails can be sent by `udb digest --send personal`
(the account needs `send: true` and the `gmail.send` scope).

## 3. Phone

Open the Claude app → Code → your vault repo, and ask. The `/udb-digest`,
`/udb-status` and `/udb-agenda` skills answer the usual questions. When your
laptop is on, Remote Control gives the phone the full local session instead,
including recordings and Packet Tracer.
