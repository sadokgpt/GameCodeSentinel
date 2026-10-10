"""Pure table helpers, safe to import without Tkinter or a live database."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from collections.abc import Iterable

from sentinel_freshness import MAX_AGE_DAYS, age_days, parse_publication_time


DEFAULT_COLUMNS = (
    "game", "code", "status", "verify", "expires", "published",
    "seen", "last", "sources", "reward",
)
DEFAULT_WIDTHS = {
    "game": 125, "code": 168, "status": 165,
    "verify": 165, "expires": 151, "published": 124,
    "seen": 155, "last": 155, "sources": 62, "reward": 270,
}


def restore_column_order(raw: object) -> tuple[str, ...]:
    """Reject malformed or partial saved layouts, not just missing columns."""
    if isinstance(raw, (list, tuple)) and len(raw) == len(DEFAULT_COLUMNS):
        if all(isinstance(c, str) for c in raw) and set(raw) == set(DEFAULT_COLUMNS):
            return tuple(raw)
    return DEFAULT_COLUMNS


def restore_column_widths(raw: object) -> dict[str, int]:
    widths = DEFAULT_WIDTHS.copy()
    if isinstance(raw, dict):
        for name, value in raw.items():
            if name in widths and type(value) is int and 65 <= value <= 850:
                widths[name] = value
    return widths


def move_column(columns: Iterable[str], source: str, before: str) -> tuple[str, ...]:
    """Move a heading to a chosen visual position without changing row fields."""
    order = list(restore_column_order(list(columns)))
    if source not in order or before not in order or source == before:
        return tuple(order)
    order.remove(source)
    order.insert(order.index(before), source)
    return tuple(order)


def sources_from_row(row) -> list[dict]:
    try:
        value = json.loads(row["sources_json"] or "[]")
        return [s for s in value if isinstance(s, dict)] if isinstance(value, list) else []
    except (TypeError, ValueError, KeyError, IndexError):
        return []


def latest_post_date(row) -> str:
    """Newest genuine publication date in the saved evidence, never last_seen."""
    dates = [parse_publication_time(src.get("published_at"))
             for src in sources_from_row(row)]
    return max((value for value in dates if value), default="")


def is_recent_code(row, now: datetime | None = None) -> bool:
    """Recent refers to publication, not scan/download or article edit time."""
    posted = latest_post_date(row)
    if not posted:
        return False
    maximum = MAX_AGE_DAYS.get(row["game"], 60)
    days = age_days(posted, now=now)
    return days is not None and days <= maximum


def sort_rows_by_post_date(rows, descending: bool = True):
    """Keep unknown publication dates last for both newest/oldest orderings."""
    known, unknown = [], []
    for row in rows:
        post = latest_post_date(row)
        (known if post else unknown).append((post, row))
    known.sort(key=lambda p: p[0], reverse=descending)
    return [r for _, r in known] + [r for _, r in unknown]
