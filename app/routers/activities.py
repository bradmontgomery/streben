import json

from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.models import Activity
from app.services.charts import build_streams_chart, build_zone_chart
from app.services.geo import decode_polyline

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/activities/{activity_id}")
def activity_detail(request: Request, activity_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail="Activity not found")

    activity = Activity.from_row(row)

    stream_rows = db.execute(
        "SELECT * FROM activity_streams WHERE activity_id = ? ORDER BY timestamp_offset",
        (activity_id,),
    ).fetchall()
    db.close()

    streams = [dict(r) for r in stream_rows]
    chart_html = build_streams_chart(streams)
    power_zone_html = build_zone_chart(streams, "watts", 100, "#3273dc", "Power (W)")
    hr_zone_html = build_zone_chart(streams, "heartrate", 50, "#ff3860", "Heart Rate (bpm)")
    flash = request.query_params.get("flash")

    # Build route coordinates for map display
    # Prefer stream lat/lng data; fall back to decoded summary_polyline
    geo_points = [
        (s["lat"], s["lng"], s["timestamp_offset"]) for s in streams
        if s.get("lat") is not None and s.get("lng") is not None
    ]
    route_coords = [[lat, lng] for lat, lng, _ in geo_points]
    route_times = [t for _, _, t in geo_points]
    if not route_coords and activity.summary_polyline:
        route_coords = decode_polyline(activity.summary_polyline)
        route_times = []

    return templates.TemplateResponse(request, "activity_detail.html", {
        "activity": activity,
        "chart_html": chart_html,
        "power_zone_html": power_zone_html,
        "hr_zone_html": hr_zone_html,
        "stream_count": len(streams),
        "route_coords": json.dumps(route_coords) if route_coords else None,
        "route_times": json.dumps(route_times) if route_times else "[]",
        "flash": flash,
    })
