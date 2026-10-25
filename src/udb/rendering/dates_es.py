"""Dates in Spanish for pages and emails: "sábado 24 de octubre de 2026", "10:45 p. m.".

Every filter takes epoch seconds, a date, a datetime or an ISO string, and works in
the vault's timezone. `now` is fixed per render so "faltan 58 min" is consistent.
"""
from datetime import date, datetime

from udb.config import settings

DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")


def _dt(value) -> datetime | date | None:
    zone = settings.get().tz
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value.astimezone(zone) if value.tzinfo else value.replace(tzinfo=zone)
    if isinstance(value, date):
        return value
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, zone)
    text = str(value)
    if len(text) == 10:
        return date.fromisoformat(text)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00").replace(" ", "T"))
    return parsed.astimezone(zone) if parsed.tzinfo else parsed.replace(tzinfo=zone)


def _day(value) -> date | None:
    d = _dt(value)
    return d.date() if isinstance(d, datetime) else d


def long_date(value) -> str:
    """sábado 24 de octubre de 2026"""
    d = _day(value)
    return f"{DAYS[d.weekday()]} {d.day} de {MONTHS[d.month - 1]} de {d.year}" if d else ""


def day_month(value) -> str:
    """sábado 24 de octubre"""
    d = _day(value)
    return f"{DAYS[d.weekday()]} {d.day} de {MONTHS[d.month - 1]}" if d else ""


def short_date(value) -> str:
    """sáb 24 oct"""
    d = _day(value)
    return f"{DAYS[d.weekday()][:3]} {d.day} {MONTHS[d.month - 1][:3]}" if d else ""


def clock(value) -> str:
    """10:45 p. m. (empty for a bare date)"""
    d = _dt(value)
    if not isinstance(d, datetime):
        return ""
    hour = d.hour % 12 or 12
    return f"{hour}:{d.minute:02d} {'a. m.' if d.hour < 12 else 'p. m.'}"


def _now() -> datetime:
    return datetime.now(settings.get().tz)


def ago(value, now: datetime | None = None) -> str:
    """hace 6 h · hace 3 días · ayer"""
    d = _dt(value)
    if not isinstance(d, datetime):
        return ""
    secs = ((now or _now()) - d).total_seconds()
    if secs < 3600:
        return f"hace {max(1, int(secs // 60))} min"
    if secs < 86400:
        return f"hace {int(secs // 3600)} h"
    days = int(secs // 86400)
    return "ayer" if days == 1 else f"hace {days} días"


def left(value, now: datetime | None = None) -> str:
    """faltan 58 min · faltan 5 h · faltan 3 días · cerrado"""
    d = _dt(value)
    if d is None:
        return ""
    now = now or _now()
    if not isinstance(d, datetime):
        days = (d - now.date()).days
        return "hoy" if days == 0 else "mañana" if days == 1 else f"faltan {days} días" \
            if days > 1 else "cerrado"
    secs = (d - now).total_seconds()
    if secs <= 0:
        return "cerrado"
    if secs < 3600:
        return f"faltan {max(1, int(secs // 60))} min"
    if secs < 48 * 3600:
        hours, mins = divmod(int(secs // 60), 60)
        return f"faltan {hours} h {mins:02d} min" if hours < 6 else f"faltan {hours} h"
    return f"faltan {int(secs // 86400)} días"


FILTERS = {"long_date": long_date, "day_month": day_month, "short_date": short_date,
           "clock": clock, "ago": ago, "left": left}
