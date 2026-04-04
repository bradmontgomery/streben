import json
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.services import strava_client

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/settings")
def settings_page(request: Request):
    auth = strava_client.get_auth()
    flash = request.query_params.get("flash")
    return templates.TemplateResponse(request, "settings.html", {
        "auth": auth,
        "flash": flash,
    })


@router.post("/settings")
async def save_settings(request: Request):
    form = await request.form()
    client_id = form.get("client_id", "").strip()
    client_secret = form.get("client_secret", "").strip()

    if not client_id or not client_secret:
        return RedirectResponse("/settings?flash=Client+ID+and+Secret+are+required", status_code=303)

    strava_client.save_auth(client_id, client_secret)
    return RedirectResponse("/settings?flash=Settings+saved", status_code=303)


@router.get("/strava/connect")
def strava_connect(request: Request):
    redirect_uri = str(request.url_for("strava_callback"))
    auth_url = strava_client.get_authorize_url(redirect_uri)
    if not auth_url:
        return RedirectResponse("/settings?flash=Set+Client+ID+and+Secret+first", status_code=303)
    return RedirectResponse(auth_url)


@router.get("/strava/callback")
def strava_callback(request: Request):
    code = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        return RedirectResponse(f"/settings?flash=Authorization+denied:+{quote(error)}", status_code=303)
    if not code:
        return RedirectResponse("/settings?flash=No+authorization+code+received", status_code=303)

    try:
        strava_client.exchange_code(code)
        return RedirectResponse("/settings?flash=Connected+to+Strava!", status_code=303)
    except Exception as e:
        return RedirectResponse(f"/settings?flash=Error:+{quote(str(e))}", status_code=303)


@router.post("/strava/sync")
def strava_sync():
    try:
        activities = strava_client.get_all_activities()
    except Exception as e:
        return RedirectResponse(f"/?flash=Sync+error:+{quote(str(e))}", status_code=303)

    db = get_db()
    new_count = 0

    for act in activities:
        strava_id = act["id"]
        existing = db.execute(
            "SELECT id FROM activities WHERE strava_id = ?", (strava_id,)
        ).fetchone()
        if existing:
            continue

        db.execute(
            """INSERT INTO activities
               (strava_id, source, name, sport_type, start_date, moving_time, elapsed_time,
                distance, average_watts, max_watts, weighted_average_watts,
                average_heartrate, max_heartrate, average_cadence, average_speed, max_speed,
                elev_high, elev_low, kilojoules, suffer_score, raw_data)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                strava_id,
                "strava",
                act.get("name"),
                act.get("sport_type") or act.get("type"),
                act.get("start_date"),
                act.get("moving_time"),
                act.get("elapsed_time"),
                act.get("distance"),
                act.get("average_watts"),
                act.get("max_watts"),
                act.get("weighted_average_watts"),
                act.get("average_heartrate"),
                act.get("max_heartrate"),
                act.get("average_cadence"),
                act.get("average_speed"),
                act.get("max_speed"),
                act.get("elev_high"),
                act.get("elev_low"),
                act.get("kilojoules"),
                act.get("suffer_score"),
                json.dumps(act),
            ),
        )
        new_activity_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Fetch streams for this activity
        try:
            streams = strava_client.get_activity_streams(strava_id)
            _insert_strava_streams(db, new_activity_id, streams)
        except Exception:
            pass  # Stream fetch can fail for some activity types

        new_count += 1

    db.commit()
    db.close()

    return RedirectResponse(f"/?flash=Synced+{new_count}+new+activities", status_code=303)


def _insert_strava_streams(db, activity_id: int, streams: list[dict]):
    if not streams:
        return

    # Build a dict of stream_type -> data array
    by_type = {}
    for s in streams:
        by_type[s["type"]] = s["data"]

    time_data = by_type.get("time", [])
    if not time_data:
        return

    for i, t in enumerate(time_data):
        latlng = by_type.get("latlng", [])
        lat = latlng[i][0] if i < len(latlng) else None
        lng = latlng[i][1] if i < len(latlng) else None

        db.execute(
            """INSERT INTO activity_streams
               (activity_id, timestamp_offset, watts, heartrate, cadence, distance, speed, altitude, lat, lng)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                activity_id,
                t,
                _safe_index(by_type.get("watts", []), i),
                _safe_index(by_type.get("heartrate", []), i),
                _safe_index(by_type.get("cadence", []), i),
                _safe_index(by_type.get("distance", []), i),
                None,  # speed not in default stream types
                _safe_index(by_type.get("altitude", []), i),
                lat,
                lng,
            ),
        )


def _safe_index(lst: list, i: int):
    return lst[i] if i < len(lst) else None
