"""One interface for every mail account, whatever the provider.

Accounts live in `config/mail.yaml`:

    accounts:
      - id: personal
        provider: gmail          # gmail | imap
        address: me@gmail.com
        calendar: true           # also read Google Calendar from this account
    filters:
      - name: teachers
        from_domains: [udb.edu.sv]

Credentials never go in that file. `udb mail login <id>` stores them under
the secrets folder (`~/.config/udb` by default). In cloud sessions an account
can read them from an environment variable named in `credentials_env`.
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from udb.config import settings
from udb.config.paths import load_yaml
from udb.domain.text.normalize import normalize


@dataclass
class Message:
    id: str
    account: str
    provider: str
    date: int                      # epoch seconds
    sender: str
    subject: str
    snippet: str
    attachments: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)   # filters it matched

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Query:
    since_days: int = 7
    terms: list[str] = field(default_factory=list)      # any of these words
    from_domains: list[str] = field(default_factory=list)
    limit: int = 25


class Provider(Protocol):
    account: dict

    def search(self, query: Query) -> list[Message]: ...

    def attachments(self, message_id: str, dest: Path, pdf_only: bool = False) -> list[Path]: ...


class MailError(RuntimeError):
    pass


def accounts(include_disabled: bool = False) -> list[dict]:
    """Configured accounts; `enabled: false` ones are skipped by digest and search."""
    found = load_yaml("mail.yaml").get("accounts", [])
    return found if include_disabled else [a for a in found if a.get("enabled", True)]


def filters() -> list[dict]:
    return load_yaml("mail.yaml").get("filters", [])


def get_account(account_id: str) -> dict:
    for acc in accounts(include_disabled=True):
        if acc["id"] == account_id:
            return acc
    raise MailError(f"unknown mail account: {account_id} (see config/mail.yaml)")


def secret_path(account: dict) -> Path:
    return settings.get().secrets / f"mail-{account['id']}.json"


def secret_from_env(account: dict) -> str | None:
    name = account.get("credentials_env")
    return os.environ.get(name) if name else None


def matches(message: Message, query: Query) -> bool:
    sender = message.sender.lower()
    if query.from_domains and not any(d.lower() in sender for d in query.from_domains):
        return False
    if query.terms:
        text = normalize(f"{message.subject} {message.snippet}")
        return any(normalize(t) in text for t in query.terms)
    return True


def label(message: Message) -> Message:
    for f in filters():
        domains = [d.lower() for d in f.get("from_domains", [])]
        senders = [s.lower() for s in f.get("from", [])]
        sender = message.sender.lower()
        if any(d in sender for d in domains) or any(s in sender for s in senders):
            message.labels.append(f["name"])
    return message


def safe_name(name: str) -> str:
    clean = re.sub(r"[\x00/\\]", "_", Path(name).name)
    return clean or "attachment"


def provider_for(account: dict) -> Provider:
    kind = account.get("provider")
    if kind == "gmail" and account.get("auth") == "app-password":
        from udb.integrations.mail.imap import ImapProvider
        return ImapProvider({"host": "imap.gmail.com", "smtp_host": "smtp.gmail.com", **account})
    if kind == "gmail":
        from udb.integrations.mail.gmail import GmailProvider
        return GmailProvider(account)
    if kind == "imap":
        from udb.integrations.mail.imap import ImapProvider
        return ImapProvider(account)
    raise MailError(f"account {account.get('id')}: unknown provider '{kind}'")


def search_all(query: Query, account_ids: list[str] | None = None) -> tuple[list[Message], list[dict]]:
    """Messages from every account (newest first) and a status line per account."""
    found: list[Message] = []
    status = []
    for acc in accounts():
        if account_ids and acc["id"] not in account_ids:
            continue
        try:
            msgs = [label(m) for m in provider_for(acc).search(query)]
            found += msgs
            status.append({"account": acc["id"], "ok": True, "detail": f"{len(msgs)} messages"})
        except Exception as exc:  # noqa: BLE001 - one broken account must not hide the rest
            status.append({"account": acc["id"], "ok": False,
                           "detail": f"{type(exc).__name__}: {exc}"})
    return sorted(found, key=lambda m: -m.date), status
