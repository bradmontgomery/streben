import json
import sqlite3

import pytest

from app.database import SCHEMA
from app.services.activity_store import find_overlapping_activity, insert_activity, to_strava_iso
from app.services.wahoo_client import rate_limit_state
from app.services.wahoo_sync import local_power_bounds, map_workout, pick_bike_zones


def _workout(**summary_overrides):
    summary = {
        "id": 8297,
        "name": "Evening Ride",
        "time_zone": "America/Chicago",
        "file": {"url": "https://example.com/ride.fit"},
        "distance_accum": "40233.6",
        "ascent_accum": "312.0",
        "calories_accum": "850",
        "duration_active_accum": "5400.0",
        "duration_total_accum": "5700.0",
        "heart_rate_avg": "141.2",
        "cadence_avg": "88.0",
        "power_avg": "180.5",
        "power_bike_np_last": "195.0",
        "power_bike_tss_last": "72.4",
        "speed_avg": "7.45",
        "work_accum": "974700.0",
    }
    summary.update(summary_overrides)
    return {
        "id": 123,
        # 7:30pm CST on Nov 14 == 01:30 UTC Nov 15
        "starts": "2026-11-15T01:30:00.000Z",
        "minutes": 95,
        "name": "Planned name",
        "workout_type_id": 0,
        "workout_summary": summary,
    }


def test_map_workout_casts_string_decimals():
    act = map_workout(_workout())
    assert act["distance"] == pytest.approx(40233.6)
    assert act["average_watts"] == pytest.approx(180.5)
    assert act["weighted_average_watts"] == pytest.approx(195.0)
    assert act["moving_time"] == 5400
    assert act["elapsed_time"] == 5700
    assert act["calories"] == pytest.approx(850)
    assert act["name"] == "Evening Ride"
    assert act["suffer_score"] is None


def test_map_workout_kj_from_joules():
    assert map_workout(_workout())["kilojoules"] == pytest.approx(974.7)


def test_map_workout_kj_falls_back_to_avg_power():
    act = map_workout(_workout(work_accum=None))
    assert act["kilojoules"] == pytest.approx(180.5 * 5400 / 1000, abs=0.1)


def test_evening_ride_gets_local_date():
    act = map_workout(_workout())
    assert act["start_date"] == "2026-11-15T01:30:00Z"
    raw = json.loads(act["raw_data"])
    assert raw["start_date_local"] == "2026-11-14T19:30:00Z"
    assert raw["workout_summary"]["power_bike_tss_last"] == "72.4"


def test_unknown_time_zone_omits_local_date():
    raw = json.loads(map_workout(_workout(time_zone="Not/AZone"))["raw_data"])
    assert "start_date_local" not in raw


@pytest.mark.parametrize("type_id,expected", [
    (0, "Ride"), (15, "Ride"), (13, "MountainBikeRide"), (61, "VirtualRide"),
    (12, "VirtualRide"), (1, "Run"), (9, "Hike"), (255, "Workout"),
])
def test_sport_type_mapping(type_id, expected):
    w = _workout()
    w["workout_type_id"] = type_id
    assert map_workout(w)["sport_type"] == expected


def test_to_strava_iso_formats():
    assert to_strava_iso("2024-05-01 14:03:00+00:00") == "2024-05-01T14:03:00Z"
    assert to_strava_iso("2024-05-01T09:03:00-05:00") == "2024-05-01T14:03:00Z"
    assert to_strava_iso(None) is None


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    yield conn
    conn.close()


def test_overlap_matches_across_formats(db):
    # FIT uploads store "YYYY-MM-DD HH:MM:SS+00:00"; Strava/Wahoo store "...Z"
    insert_activity(db, {"start_date": "2026-11-15 01:28:00+00:00"}, source="fit_upload")
    hit = find_overlapping_activity(db, "2026-11-15T01:30:00Z", "wahoo")
    assert hit is not None and hit["source"] == "fit_upload"


def test_overlap_respects_window(db):
    insert_activity(db, {"start_date": "2026-11-15T01:20:00Z"}, source="strava", strava_id=1)
    assert find_overlapping_activity(db, "2026-11-15T01:30:00Z", "wahoo") is None
    assert find_overlapping_activity(db, "2026-11-15T01:24:00Z", "wahoo") is not None


def test_overlap_ignores_same_source(db):
    # Two real Strava activities can start minutes apart; strava_id already dedups Strava.
    insert_activity(db, {"start_date": "2026-11-15T01:28:00Z"}, source="strava", strava_id=1)
    assert find_overlapping_activity(db, "2026-11-15T01:30:00Z", "strava") is None
    assert find_overlapping_activity(db, "2026-11-15T01:30:00Z", "wahoo") is not None


def test_wahoo_id_is_unique(db):
    db.execute("CREATE UNIQUE INDEX idx_activities_wahoo_id ON activities(wahoo_id)")
    insert_activity(db, {"start_date": "2026-01-01T00:00:00Z"}, source="wahoo", wahoo_id=5)
    with pytest.raises(sqlite3.IntegrityError):
        insert_activity(db, {"start_date": "2026-02-01T00:00:00Z"}, source="wahoo", wahoo_id=5)


def test_power_zones_pick_and_map():
    entries = [
        {"id": 1, "workout_type_id": 1, "workout_type_family_id": 1,
         "zone_1": 1, "zone_2": 2, "zone_3": 3, "zone_4": 4},
        {"id": 2, "workout_type_id": 0, "workout_type_family_id": 0,
         "zone_1": "150", "zone_2": "205", "zone_3": "245", "zone_4": "285",
         "zone_5": "325", "zone_6": "405", "zone_7": "600", "ftp": "270"},
    ]
    entry = pick_bike_zones(entries)
    assert entry["id"] == 2
    assert local_power_bounds(entry) == [0, 150, 205, 245, 285]


def test_power_zones_reject_non_increasing():
    assert local_power_bounds({"zone_1": 200, "zone_2": 150, "zone_3": 250, "zone_4": 300}) is None


@pytest.mark.parametrize("remaining,reset,expected", [
    ("12, 80, 200", "120, 1800, 40000", (False, None)),
    ("0, 80, 200", "120, 1800, 40000", (True, 120)),       # 5-minute window spent
    ("5, 40, 0", "120, 1800, 40000", (True, 40000)),       # daily window spent -> daily reset
    ("0, 0, 0", "120, 1800, 40000", (True, 40000)),
    ("0", "120, 1800, 40000", (True, 40000)),              # can't pair -> longest reset
    ("", "", (False, None)),
])
def test_rate_limit_state(remaining, reset, expected):
    headers = {"X-RateLimit-Remaining": remaining, "X-RateLimit-Reset": reset}
    assert rate_limit_state(headers) == expected
