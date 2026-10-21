"""Google Calendar, read-only. Uses the mail account marked `calendar: true`."""
from datetime import UTC, datetime
from urllib.parse import quote

from ..mail import base
from ..mail.gmail import token_for
from . import oauth

API = "https://www.googleapis.com/calendar/v3"


def calendar_account() -> dict:
    for acc in base.accounts():
        if acc.get("provider") == "gmail" and acc.get("calendar"):
            return acc
    raise base.MailError("no mail account has calendar: true in config/mail.yaml")


def events(start: float, end: float) -> list[dict]:
    token = token_for(calendar_account())

    def iso(t: float) -> str:
        return datetime.fromtimestamp(t, UTC).isoformat().replace("+00:00", "Z")

    out = []
    for cal in oauth.get(f"{API}/users/me/calendarList", token).get("items", []):
        # Ids such as "es.sv#holiday@group.v.calendar.google.com" must be escaped:
        # an unescaped "#" cuts the URL and Google answers 404.
        try:
            data = oauth.get(f"{API}/calendars/{quote(cal['id'], safe='')}/events", token, {
                "timeMin": iso(start), "timeMax": iso(end), "singleEvents": "true",
                "orderBy": "startTime", "maxResults": 250})
        except oauth.GoogleError:
            continue
        for ev in data.get("items", []):
            begin = ev.get("start", {})
            out.append({"title": ev.get("summary", "(no title)"),
                        "start": begin.get("dateTime") or begin.get("date"),
                        "calendar": cal.get("summary", "")})
    return out
