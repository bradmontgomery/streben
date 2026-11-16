"""Shared persistence helpers for activities coming from any source."""
from datetime import datetime, timezone

from app.models import StreamRecord

ACTIVITY_COLUMNS = [
    "name", "sport_type", "start_date", "moving_time", "elapsed_time",
    "distance", "average_watts", "max_watts", "weighted_average_watts",
    "average_heartrate", "max_heartrate", "average_cadence", "average_speed", "max_speed",
    "elev_high", "elev_low", "kilojoules", "suffer_score",
    "total_elevation_gain", "calories", "description", "device_name", "average_temp",
    "summary_polyline",
]


def to_strava_iso(value) -> str | None:
    """Normalize a datetime or ISO string to Strava's UTC format, e.g. 2024-05-01T14:03:00Z."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_overlapping_activity(db, start_date: str | None, source: str, window_s: int = 300):
    """Return an activity from a *different* source that starts within ±window_s seconds.

    Same-source repeats are already caught by strava_id / wahoo_id, and two genuine activities
    from one source can start minutes apart (a false start, back-to-back legs), so they are
    not treated as duplicates. julianday() understands both Strava's `...Z` format and the
    `... +00:00` format FIT uploads store, so this matches across sources.
    """
    if not start_date:
        return None
    return db.execute(
        """SELECT id, source, name, start_date FROM activities
           WHERE start_date IS NOT NULL AND source != ?
             AND ABS(julianday(start_date) - julianday(?)) * 86400 <= ?
           ORDER BY ABS(julianday(start_date) - julianday(?))
           LIMIT 1""",
        (source, start_date, window_s, start_date),
    ).fetchone()


def insert_activity(
    db,
    act: dict,
    streams: list[StreamRecord] | None = None,
    *,
    source: str,
    strava_id: int | None = None,
    wahoo_id: int | None = None,
    fit_filename: str | None = None,
    raw_data: str | None = None,
) -> int:
    """Insert an activity row (and its stream records). Returns the new activity id.

    Does not commit; the caller owns the transaction.
    """
    cols = ["source", "strava_id", "wahoo_id", "fit_filename", "raw_data", *ACTIVITY_COLUMNS]
    values = [source, strava_id, wahoo_id, fit_filename, raw_data,
              *(act.get(c) for c in ACTIVITY_COLUMNS)]
    cur = db.execute(
        f"INSERT INTO activities ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        values,
    )
    activity_id = cur.lastrowid
    insert_streams(db, activity_id, streams or [])
    return activity_id


def insert_streams(db, activity_id: int, streams: list[StreamRecord]):
    db.executemany(
        """INSERT INTO activity_streams
           (activity_id, timestamp_offset, watts, heartrate, cadence, distance, speed, altitude, lat, lng)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [
            (activity_id, s.timestamp_offset, s.watts, s.heartrate, s.cadence,
             s.distance, s.speed, s.altitude, s.lat, s.lng)
            for s in streams
        ],
    )
