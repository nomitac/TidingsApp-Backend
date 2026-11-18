"""Timestamps are exchanged as ISO-8601 UTC with milliseconds: 2026-11-15T22:44:01.123Z."""
from datetime import datetime, timezone
import re

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def now() -> datetime:
    return datetime.now(timezone.utc)


def parse(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        s = value.strip()
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        # Python 3.12 fromisoformat accepts 1-6 fractional digits; trim longer (Postgres gives ≤6).
        m = re.match(r"^(.*?\.\d{6})\d+(.*)$", s)
        if m:
            s = m.group(1) + m.group(2)
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fmt(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def normalize(value: str | datetime) -> str:
    return fmt(parse(value))


def now_str() -> str:
    return fmt(now())


def looks_like_ts(value: object) -> bool:
    return isinstance(value, str) and bool(_TS_RE.match(value))
