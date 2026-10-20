"""Any IMAP mailbox (Gmail with an app password, Yahoo, another university's server...).

The password is an app password, stored by `udb mail login <id>` in the
secrets folder or read from the variable named in `credentials_env`.

    - id: other
      provider: imap
      host: imap.example.edu
      port: 993
      address: me@example.edu
"""
from __future__ import annotations

import email
import imaplib
import smtplib
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path

from .base import MailError, Message, Query, matches, safe_name, secret_from_env, secret_path


def password_for(account: dict) -> str:
    raw = secret_from_env(account)
    if raw:
        return raw
    path = secret_path(account)
    if not path.exists():
        raise MailError(f"no password for {account['id']}. Run: udb mail login {account['id']}")
    return path.read_text(encoding="utf-8").strip()


def _text(value: str | None) -> str:
    return str(make_header(decode_header(value or "")))


class ImapProvider:
    def __init__(self, account: dict):
        self.account = account

    def _connect(self) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self.account["host"], int(self.account.get("port", 993)))
        conn.login(self.account.get("user", self.account["address"]), password_for(self.account))
        conn.select(self.account.get("folder", "INBOX"), readonly=True)
        return conn

    def search(self, query: Query) -> list[Message]:
        since = (datetime.now() - timedelta(days=query.since_days)).strftime("%d-%b-%Y")
        conn = self._connect()
        try:
            _, data = conn.search(None, "SINCE", since)
            ids = data[0].split()[::-1][: max(query.limit * 3, 50)]
            out = []
            for num in ids:
                _, parts = conn.fetch(num, "(BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.400>)")
                header = email.message_from_bytes(parts[0][1])
                body = parts[1][1].decode("utf-8", errors="replace") if len(parts) > 1 else ""
                when = parsedate_to_datetime(header["Date"]) if header["Date"] else datetime.now()
                msg = Message(id=num.decode(), account=self.account["id"], provider="imap",
                              date=int(when.timestamp()), sender=_text(header["From"]),
                              subject=_text(header["Subject"]),
                              snippet=" ".join(body.split())[:280])
                if matches(msg, query):
                    out.append(msg)
                if len(out) >= query.limit:
                    break
            return out
        finally:
            conn.logout()

    def attachments(self, message_id: str, dest: Path, pdf_only: bool = False) -> list[Path]:
        conn = self._connect()
        try:
            _, parts = conn.fetch(message_id.encode(), "(RFC822)")
        finally:
            conn.logout()
        msg = email.message_from_bytes(parts[0][1])
        dest.mkdir(parents=True, exist_ok=True)
        saved = []
        for part in msg.walk():
            name = part.get_filename()
            if not name or (pdf_only and not name.lower().endswith(".pdf")):
                continue
            target = dest / safe_name(_text(name))
            target.write_bytes(part.get_payload(decode=True) or b"")
            saved.append(target)
        return saved

    def send(self, to: str, subject: str, html: str, text: str = "") -> str:
        host = self.account.get("smtp_host")
        if not host or not self.account.get("send"):
            raise MailError(f"account {self.account['id']} is not set to send (send: true, smtp_host)")
        msg = EmailMessage()
        msg["To"], msg["From"], msg["Subject"] = to, self.account["address"], subject
        msg.set_content(text or "Este correo necesita un lector con HTML.")
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP_SSL(host, int(self.account.get("smtp_port", 465)), timeout=30) as smtp:
            smtp.login(self.account.get("user", self.account["address"]), password_for(self.account))
            smtp.send_message(msg)
        return msg["Message-ID"] or "sent"

    def check(self) -> None:
        self._connect().logout()
