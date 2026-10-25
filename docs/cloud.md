# Running udb in Claude Code on the web (and from your phone)

A cloud session clones your **private vault repo** into a fresh Linux container.
The vault's `.claude/` folder (written by `udb setup claude`) brings the skills,
agents, hooks and the `vault` MCP server. The `SessionStart` hook installs `udb`
when it is missing and builds the search index.

What works in the cloud: Moodle, mail, Calendar, Drive, search and citations,
`udb status`, `udb digest`, agenda, tasks, writing notes and exercises.
What stays on your computer: videos (download, GPU transcription, board
reading), Teams recordings with Claude in Chrome, Packet Tracer.

**Cloud mode.** udb turns the local-only parts off by itself when
`CLAUDE_CODE_REMOTE=true` (every Claude Code cloud session). `UDB_CLOUD=1`
forces cloud mode anywhere, `UDB_CLOUD=0` forces local mode. In cloud mode
`udb recording download|attach|transcribe|frames|read-boards|process|stream-js|import-stream`
stop with a clear message, the session hook skips the Moodle sync and tells
Claude what is not available. Reading transcripts, board stills already
committed and the radar keep working.

## 1. Environment

In [claude.ai/code](https://claude.ai/code) → your vault repo → environment settings:

**Network access: Custom**, allowing:

```
www.udbvirtual.edu.sv
*.googleapis.com
oauth2.googleapis.com
accounts.google.com
github.com
pypi.org
files.pythonhosted.org
registry.npmjs.org
```

Add your IMAP host if you use one.

**Environment variables** (only for you; never commit them): one variable,
`UDB_SECRETS`. On your computer run `udb cloud secrets` and paste its output as
the value. It packs the Moodle token, mail and Google tokens and the Google
Workspace MCP credentials; each cloud session unpacks them into the same files.
Run it again only when you add an account or renew a token.

Never put your UDB password in the cloud: only the token. In a cloud session,
`udb cloud check` shows whether the secrets were restored, the hosts are
reachable and OCR works.

**Setup script** (optional; the SessionStart hook does the same if you skip it):

```bash
#!/bin/bash
set -e
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv tool install "udb-copilot @ git+https://github.com/franc1sc0sv/udb-copilot"
udb setup mathjax || true
```

## 2. Routines

Ask Claude, in a session on the vault repo, to create these with `/schedule`.
Both send the built-in email with `udb digest --send <account>` (the account
needs `send: true` and the `gmail.send` scope), so no connector is needed and
every line comes from a source. Cron runs in UTC; El Salvador is UTC−6.

**Morning briefing, every day at 05:52 (`52 11 * * *` UTC):**

> In the vault root run `udb digest --send personal`. It mails "Mañanita: tu
> día <date>": classes today, what is due in 72 hours, the countdown with
> weights, the Moodle calendar, what changed this week (★ new), unread
> notifications, what was said in class and teacher mail. Report the output.
> If it says "No pude leer", name the failed sources.

**Change alerts, every 2 hours from 07:00 to 21:00
(`0 1,3,13,15,17,19,21,23 * * *` UTC):**

> In the vault root run `udb digest --alerts --hours 2 --send personal`. It
> mails "Novedades en el aula" only when something is new; otherwise it sends
> nothing. Report the output.

A fresh clone has no `index/digest_seen.json`, so in the cloud "new" (★)
means "inside the window" (24 hours for the briefing). Alerts only look at
the window.

## 3. Phone

Open the Claude app → Code → your vault repo, and ask. The `/udb-digest`,
`/udb-status` and `/udb-agenda` skills answer the usual questions. When your
laptop is on, Remote Control gives the phone the full local session instead,
including recordings and Packet Tracer.
