from pathlib import Path
from garmin_fit_sdk import Decoder, Stream
from app.models import StreamRecord


def parse_fit_file(file_path: str | Path) -> dict:
    """Parse a FIT file and return activity summary + stream records.

    Returns:
        {
            "activity": dict of activity-level fields,
            "streams": list of StreamRecord,
        }
    """
    stream = Stream.from_file(str(file_path))
    decoder = Decoder(stream)
    messages, errors = decoder.read()

    if errors:
        raise ValueError(f"FIT decode errors: {errors}")

    activity = _extract_activity(messages)
    streams = _extract_streams(messages)

    return {"activity": activity, "streams": streams}


def _extract_activity(messages: dict) -> dict:
    """Extract activity summary from session messages."""
    sessions = messages.get("session_mesgs", [])
    if not sessions:
        # Fall back to activity message
        activity_mesgs = messages.get("activity_mesgs", [])
        if activity_mesgs:
            msg = activity_mesgs[0]
            return {
                "name": None,
                "sport_type": str(msg.get("sport", "")),
                "start_date": str(msg.get("timestamp", "")),
                "elapsed_time": _to_seconds(msg.get("total_elapsed_time")),
            }
        return {}

    session = sessions[0]
    return {
        "name": None,  # FIT files don't have user-friendly names; caller uses filename
        "sport_type": str(session.get("sport", "")),
        "start_date": str(session.get("start_time", session.get("timestamp", ""))),
        "moving_time": _to_seconds(session.get("total_timer_time")),
        "elapsed_time": _to_seconds(session.get("total_elapsed_time")),
        "distance": _to_float(session.get("total_distance")),
        "average_watts": _to_float(session.get("avg_power")),
        "max_watts": _to_float(session.get("max_power")),
        "weighted_average_watts": _to_float(session.get("normalized_power")),
        "average_heartrate": _to_float(session.get("avg_heart_rate")),
        "max_heartrate": _to_float(session.get("max_heart_rate")),
        "average_cadence": _to_float(session.get("avg_cadence")),
        "average_speed": _to_float(session.get("avg_speed")),
        "max_speed": _to_float(session.get("max_speed")),
        "elev_high": _to_float(session.get("max_altitude")),
        "elev_low": _to_float(session.get("min_altitude")),
        "kilojoules": _calc_kj(session),
    }


def _extract_streams(messages: dict) -> list[StreamRecord]:
    """Extract per-second record data."""
    records = messages.get("record_mesgs", [])
    if not records:
        return []

    # Use the first record's timestamp as the base
    base_ts = records[0].get("timestamp")
    streams = []

    for rec in records:
        ts = rec.get("timestamp")
        if ts is None or base_ts is None:
            offset = 0
        else:
            offset = int((ts - base_ts).total_seconds()) if hasattr(ts - base_ts, "total_seconds") else 0

        lat, lng = None, None
        if rec.get("position_lat") is not None:
            lat = _semicircles_to_degrees(rec["position_lat"])
        if rec.get("position_long") is not None:
            lng = _semicircles_to_degrees(rec["position_long"])

        streams.append(StreamRecord(
            timestamp_offset=offset,
            watts=_to_float(rec.get("power")),
            heartrate=_to_float(rec.get("heart_rate")),
            cadence=_to_float(rec.get("cadence")),
            distance=_to_float(rec.get("distance")),
            speed=_to_float(rec.get("speed")),
            altitude=_to_float(rec.get("altitude")),
            lat=lat,
            lng=lng,
        ))

    return streams


def _to_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_seconds(val) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _semicircles_to_degrees(semicircles) -> float:
    return float(semicircles) * (180.0 / 2**31)


def _calc_kj(session: dict) -> float | None:
    avg_power = _to_float(session.get("avg_power"))
    duration = _to_float(session.get("total_timer_time"))
    if avg_power and duration:
        return round(avg_power * duration / 1000, 1)
    return None
