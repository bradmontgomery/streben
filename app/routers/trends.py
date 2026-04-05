from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/trends")
def trends_page(request: Request):
    return templates.TemplateResponse(request, "trends.html", {})


@router.get("/api/trends")
def trends_data(range: str = "6m"):
    range_map = {
        "1w": "-7 days",
        "1m": "-1 months",
        "3m": "-3 months",
        "6m": "-6 months",
        "1y": "-1 years",
        "all": None,
    }
    offset = range_map.get(range, "-6 months")

    db = get_db()
    if offset:
        rows = db.execute(
            """SELECT start_date, moving_time, elapsed_time, distance,
                      average_watts, max_watts, average_heartrate, max_heartrate,
                      kilojoules, suffer_score, elev_high, elev_low
               FROM activities
               WHERE start_date >= date('now', ?)
               ORDER BY start_date""",
            (offset,),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT start_date, moving_time, elapsed_time, distance,
                      average_watts, max_watts, average_heartrate, max_heartrate,
                      kilojoules, suffer_score, elev_high, elev_low
               FROM activities
               ORDER BY start_date"""
        ).fetchall()
    db.close()

    data = {
        "dates": [],
        "duration": [],
        "distance": [],
        "avg_power": [],
        "max_power": [],
        "avg_hr": [],
        "max_hr": [],
        "energy": [],
        "suffer_score": [],
        "elevation": [],
    }

    for r in rows:
        date = r["start_date"]
        if not date:
            continue
        data["dates"].append(date[:10])
        seconds = r["moving_time"] or r["elapsed_time"] or 0
        data["duration"].append(round(seconds / 60, 1))
        data["distance"].append(round(r["distance"] / 1609.344, 2) if r["distance"] else None)
        data["avg_power"].append(r["average_watts"])
        data["max_power"].append(r["max_watts"])
        data["avg_hr"].append(r["average_heartrate"])
        data["max_hr"].append(r["max_heartrate"])
        data["energy"].append(r["kilojoules"])
        data["suffer_score"].append(r["suffer_score"])
        if r["elev_high"] is not None and r["elev_low"] is not None:
            data["elevation"].append(round((r["elev_high"] - r["elev_low"]) * 3.28084))
        else:
            data["elevation"].append(None)

    return JSONResponse(data)
