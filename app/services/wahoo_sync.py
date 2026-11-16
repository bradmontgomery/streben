"""Turn Wahoo Cloud workouts and power zones into Streben rows."""
import json
import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services import wahoo_client
from app.services import zones as zone_service
from app.services.activity_store import (
    find_overlapping_activity,
    insert_activity,
    insert_streams,
    to_strava_iso,
)
from app.services.fit_parser import parse_fit_file

logger = logging.getLogger(__name__)

# Wahoo workout_type_id -> Strava sport_type, so the dashboard filter groups both sources.
# https://cloud-api.wahooligan.com/#workout-types
SPORT_TYPES = {
    0: "Ride", 11: "Ride", 15: "Ride", 16: "Ride", 14: "Ride",
    13: "MountainBikeRide",
    12: "VirtualRide", 49: "VirtualRide", 61: "VirtualRide", 68: "VirtualRide", 21: "VirtualRide",
    64: "EBikeRide",
    1: "Run", 3: "Run", 4: "TrailRun", 5: "Run", 67: "Run", 71: "VirtualRun",
    6: "Walk", 7: "Walk", 8: "Walk", 56: "Walk",
    9: "Hike",
    25: "Swim", 26: "Swim",
    39: "Rowing", 22: "Rowing",
    66: "Yoga",
    42: "WeightTraining",
}

PER_PAGE = 50


def _num(value) -> float | None:
    """Wahoo returns decimals as strings ("123.45"); treat blanks as missing."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value) -> int | None:
    n = _num(value)
    return int(round(n)) if n is not None else None


def local_start(starts_utc: str, time_zone: str | None) -> str | None:
    """Local wall-clock start in Strava's start_date_local style (local time, literal Z)."""
    if not starts_utc:
        return None
    dt = datetime.fromisoformat(starts_utc.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        tz = ZoneInfo(time_zone) if time_zone else None
    except (ZoneInfoNotFoundError, ValueError):
        tz = None
    if tz is None:
        return None
    return dt.astimezone(tz).strftime("%Y-%m-%dT%H:%M:%SZ")


def map_workout(workout: dict) -> dict:
    """Map a Wahoo workout (with a non-null workout_summary) to an activity dict.

    Pure function: no I/O. Returns the same keys as fit_parser._extract_activity plus
    `raw_data` (JSON string with a computed `start_date_local`).
    """
    summary = workout.get("workout_summary") or {}
    moving = _int(summary.get("duration_active_accum"))
    avg_watts = _num(summary.get("power_avg"))

    work_j = _num(summary.get("work_accum"))
    if work_j:
        kj = round(work_j / 1000, 1)
    elif avg_watts and moving:
        kj = round(avg_watts * moving / 1000, 1)
    else:
        kj = None

    starts = workout.get("starts")
    raw = dict(workout)
    start_local = local_start(starts, summary.get("time_zone"))
    if start_local:
        # energy.py buckets ride kJ by this key; without it evening rides land on the next UTC day
        raw["start_date_local"] = start_local

    return {
        "name": summary.get("name") or workout.get("name"),
        "sport_type": SPORT_TYPES.get(_int(workout.get("workout_type_id")), "Workout"),
        "start_date": to_strava_iso(starts),
        "moving_time": moving,
        "elapsed_time": _int(summary.get("duration_total_accum")),
        "distance": _num(summary.get("distance_accum")),
        "average_watts": avg_watts,
        "weighted_average_watts": _num(summary.get("power_bike_np_last")),
        "average_heartrate": _num(summary.get("heart_rate_avg")),
        "average_cadence": _num(summary.get("cadence_avg")),
        "average_speed": _num(summary.get("speed_avg")),
        "total_elevation_gain": _num(summary.get("ascent_accum")),
        "kilojoules": kj,
        "calories": _num(summary.get("calories_accum")),
        # suffer_score is Strava's Relative Effort; Wahoo's TSS is a different scale, so it
        # stays in raw_data rather than polluting that trend.
        "suffer_score": None,
        "raw_data": json.dumps(raw),
    }


# Fields the FIT file can fill in when the summary doesn't have them.
FIT_FILL_FIELDS = ["max_watts", "max_heartrate", "max_speed", "elev_high", "elev_low",
                   "average_watts", "weighted_average_watts", "average_heartrate",
                   "average_cadence", "average_speed", "distance", "moving_time", "elapsed_time"]


def _fetch_fit(url: str) -> dict:
    data = wahoo_client.download_fit(url)
    with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        return parse_fit_file(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@dataclass
class SyncResult:
    inserted: int = 0
    streams_filled: int = 0
    skipped_known: int = 0
    skipped_dup: int = 0
    no_summary: int = 0
    fit_failed: int = 0
    pages: int = 0
    stopped_reason: str | None = None
    duplicates: list[str] = field(default_factory=list)

    def message(self) -> str:
        parts = [f"Synced {self.inserted} new Wahoo workouts"]
        if self.skipped_dup:
            parts.append(f"skipped {self.skipped_dup} already imported from another source")
        if self.fit_failed:
            parts.append(f"{self.fit_failed} without stream data (FIT download failed; "
                         "retried by later syncs or `strava-cli sync-wahoo --full`)")
        if self.streams_filled:
            parts.append(f"filled streams for {self.streams_filled} earlier workouts")
        msg = "; ".join(parts)
        if self.stopped_reason:
            msg += f". Stopped early: {self.stopped_reason}"
        return msg


def _file_url(workout: dict) -> str | None:
    return ((workout.get("workout_summary") or {}).get("file") or {}).get("url")


def _retry_streams(db, activity_id: int, workout: dict, result: SyncResult) -> None:
    """A stored workout whose FIT download failed earlier gets another try. FIT downloads
    don't count against Wahoo's rate limits, so this is cheap."""
    if db.execute("SELECT 1 FROM activity_streams WHERE activity_id = ? LIMIT 1",
                  (activity_id,)).fetchone():
        return
    url = _file_url(workout)
    if not url:
        return
    try:
        streams = _fetch_fit(url)["streams"]
    except Exception as e:
        logger.warning("FIT retry failed for Wahoo workout %s: %s", workout["id"], e)
        return
    if streams:
        insert_streams(db, activity_id, streams)
        db.commit()
        result.streams_filled += 1


def import_workout(db, workout: dict, result: SyncResult) -> None:
    """Insert one workout if it is new and not a duplicate. Commits on insert."""
    wahoo_id = workout["id"]
    known = db.execute("SELECT id FROM activities WHERE wahoo_id = ?", (wahoo_id,)).fetchone()
    if known:
        result.skipped_known += 1
        _retry_streams(db, known["id"], workout, result)
        return

    act = map_workout(workout)
    overlap = find_overlapping_activity(db, act["start_date"], "wahoo")
    if overlap:
        logger.info("Skipping Wahoo workout %s: overlaps activity %s (%s)",
                    wahoo_id, overlap["id"], overlap["source"])
        result.skipped_dup += 1
        result.duplicates.append(f"{act['start_date']} {act['name']}")
        return

    streams = []
    file_url = _file_url(workout)
    if file_url:
        try:
            parsed = _fetch_fit(file_url)
            streams = parsed["streams"]
            for key in FIT_FILL_FIELDS:
                if act.get(key) is None and parsed["activity"].get(key) is not None:
                    act[key] = parsed["activity"][key]
        except Exception as e:  # keep the activity; _retry_streams tries again next sync
            logger.warning("FIT download/parse failed for Wahoo workout %s: %s", wahoo_id, e)
            result.fit_failed += 1
    else:
        result.fit_failed += 1

    raw_data = act.pop("raw_data")
    insert_activity(db, act, streams, source="wahoo", wahoo_id=wahoo_id, raw_data=raw_data)
    db.commit()
    result.inserted += 1


def _history_synced(db) -> bool:
    row = db.execute("SELECT history_synced_at FROM wahoo_auth WHERE id = 1").fetchone()
    return bool(row and row["history_synced_at"])


def sync_workouts(db, full: bool = False, max_pages: int | None = None,
                  progress=None) -> SyncResult:
    """Pull completed workouts from Wahoo.

    Incremental (default): stop at the first page that adds nothing new (every completed
    workout already stored or a duplicate of another source's activity). `full`: page through
    the whole history (for the first backfill or to fill gaps
    left by an interrupted run). Each insert commits, so re-running resumes cleanly.

    Until one pass has reached the end of the history, every sync behaves as `full`; otherwise
    a first page made up of rides already imported from Strava would end the first sync early.
    """
    full = full or not _history_synced(db)
    reached_end = False
    result = SyncResult()
    seen = 0
    page = 1
    while max_pages is None or page <= max_pages:
        try:
            data, pending_limit = wahoo_client.list_workouts(page=page, per_page=PER_PAGE)
        except wahoo_client.WahooRateLimited as e:
            result.stopped_reason = str(e)
            break
        result.pages += 1
        workouts = data.get("workouts") or []
        if not workouts:
            reached_end = True
            break
        seen += len(workouts)

        inserted_before = result.inserted
        completed = 0
        for w in workouts:
            if not w.get("workout_summary"):
                result.no_summary += 1  # planned / unfinished workout
                continue
            completed += 1
            import_workout(db, w, result)
            if progress:
                progress(result)

        # Count what actually came back: Wahoo may cap per_page below what we asked for.
        total = data.get("total")
        if total is not None and seen >= int(total):
            reached_end = True
            break
        if pending_limit:
            result.stopped_reason = str(pending_limit)
            break
        nothing_new = completed > 0 and result.inserted == inserted_before
        if not full and nothing_new:
            break
        page += 1

    if reached_end:
        db.execute("UPDATE wahoo_auth SET history_synced_at = datetime('now') WHERE id = 1")
        db.commit()
    return result


def pick_bike_zones(entries: list[dict]) -> dict | None:
    """Choose the cycling power-zone entry: outdoor biking, then any biking family, then first."""
    if not entries:
        return None
    for e in entries:
        if _int(e.get("workout_type_id")) == 0:
            return e
    for e in entries:
        if _int(e.get("workout_type_family_id")) == 0:
            return e
    return entries[0]


def local_power_bounds(entry: dict) -> list[int] | None:
    """Wahoo zone_N values are treated as the *upper* bound of zone N (they ascend, and
    zone_7 is open-ended upward in Wahoo's 7-zone model). Streben stores 5 lower bounds,
    so local Z1 starts at 0 and Z2..Z5 start where Wahoo zones 1..4 end.
    """
    uppers = [_int(entry.get(f"zone_{i}")) for i in range(1, 5)]
    if any(u is None for u in uppers):
        return None
    bounds = [0, *uppers]
    if bounds != sorted(bounds) or len(set(bounds)) != 5:
        return None
    return bounds


def sync_power_zones(db) -> str:
    """Store every Wahoo power-zone entry and apply the cycling one to local zone settings."""
    entries = wahoo_client.list_power_zones()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for e in entries:
        db.execute(
            """INSERT INTO wahoo_power_zones
               (wahoo_id, workout_type_id, workout_type_family_id,
                zone_1, zone_2, zone_3, zone_4, zone_5, zone_6, zone_7,
                ftp, critical_power, raw_data, synced_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(wahoo_id) DO UPDATE SET
                 workout_type_id=excluded.workout_type_id,
                 workout_type_family_id=excluded.workout_type_family_id,
                 zone_1=excluded.zone_1, zone_2=excluded.zone_2, zone_3=excluded.zone_3,
                 zone_4=excluded.zone_4, zone_5=excluded.zone_5, zone_6=excluded.zone_6,
                 zone_7=excluded.zone_7, ftp=excluded.ftp,
                 critical_power=excluded.critical_power,
                 raw_data=excluded.raw_data, synced_at=excluded.synced_at""",
            (
                e["id"], _int(e.get("workout_type_id")), _int(e.get("workout_type_family_id")),
                *(_num(e.get(f"zone_{i}")) for i in range(1, 8)),
                _num(e.get("ftp")), _num(e.get("critical_power")),
                json.dumps(e), now,
            ),
        )
    db.commit()

    entry = pick_bike_zones(entries)
    if not entry:
        return "No power zones found on Wahoo"
    bounds = local_power_bounds(entry)
    if not bounds:
        return "Saved Wahoo power zones, but they couldn't be mapped to 5 increasing local zones"
    current = zone_service.get_zone_settings()
    hr_bounds = zone_service.zone_bounds(current, "hr")
    zone_service.save_zone_settings(bounds, hr_bounds)
    ftp = _int(entry.get("ftp"))
    return f"Imported Wahoo power zones ({', '.join(map(str, bounds))} W)" + (
        f", FTP {ftp} W" if ftp else ""
    )


def stored_bike_zones(db) -> dict | None:
    rows = [dict(r) for r in db.execute("SELECT * FROM wahoo_power_zones").fetchall()]
    return pick_bike_zones(rows)
