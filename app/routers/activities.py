from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.models import Activity
from app.services.charts import build_streams_chart

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
    flash = request.query_params.get("flash")

    return templates.TemplateResponse(request, "activity_detail.html", {
        "activity": activity,
        "chart_html": chart_html,
        "stream_count": len(streams),
        "flash": flash,
    })
