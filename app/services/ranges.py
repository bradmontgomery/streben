"""Shared time-range vocabulary for the trends and nutrition views."""
from datetime import date, datetime, timedelta

from app.database import get_db

# Offsets are SQLite date modifiers; None means "everything".
RANGE_MAP = {
    "1w": "-7 days",
    "1m": "-1 months",
    "3m": "-3 months",
    "6m": "-6 months",
    "1y": "-1 years",
    "all": None,
}

_DAYS = {"1w": 7, "1m": 31, "3m": 92, "6m": 183, "1y": 366}


def resolve_dates(range_key: str, default: str = "3m") -> tuple[str, str]:
    """Resolve a range key to concrete (start, end) ISO dates for a dense day spine.

    'all' is clamped to the earliest nutrition row rather than the earliest
    activity -- the activity history reaches back to 2016 and a dense spine over
    it would materialize thousands of empty days.
    """
    end = date.today()
    if range_key == "all":
        db = get_db()
        row = db.execute("SELECT MIN(date) AS d FROM nutrition").fetchone()
        db.close()
        if row and row["d"]:
            return row["d"], end.isoformat()
        return (end - timedelta(days=_DAYS["3m"])).isoformat(), end.isoformat()

    days = _DAYS.get(range_key, _DAYS[default])
    return (end - timedelta(days=days)).isoformat(), end.isoformat()
