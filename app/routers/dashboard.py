from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.models import Activity

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def dashboard(request: Request, page: int = 1, per_page: int = 100, sport_type: str = ""):
    page = max(1, page)
    per_page = max(1, min(per_page, 500))
    offset = (page - 1) * per_page
    sport_type = sport_type.strip()

    db = get_db()
    sport_types = [
        r[0] for r in db.execute(
            "SELECT DISTINCT sport_type FROM activities WHERE sport_type IS NOT NULL ORDER BY sport_type"
        ).fetchall()
    ]

    if sport_type:
        total = db.execute("SELECT COUNT(*) FROM activities WHERE sport_type = ?", (sport_type,)).fetchone()[0]
        rows = db.execute(
            "SELECT * FROM activities WHERE sport_type = ? ORDER BY start_date DESC LIMIT ? OFFSET ?",
            (sport_type, per_page, offset),
        ).fetchall()
    else:
        total = db.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        rows = db.execute(
            "SELECT * FROM activities ORDER BY start_date DESC LIMIT ? OFFSET ?",
            (per_page, offset),
        ).fetchall()

    activity_ids = [r["id"] for r in rows]
    has_streams = set()
    if activity_ids:
        placeholders = ",".join("?" * len(activity_ids))
        stream_rows = db.execute(
            f"SELECT DISTINCT activity_id FROM activity_streams WHERE activity_id IN ({placeholders})",
            activity_ids,
        ).fetchall()
        has_streams = {r["activity_id"] for r in stream_rows}
    db.close()

    activities = [Activity.from_row(r) for r in rows]
    total_pages = max(1, (total + per_page - 1) // per_page)
    flash = request.query_params.get("flash")

    return templates.TemplateResponse(request, "dashboard.html", {
        "activities": activities,
        "flash": flash,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total": total,
        "has_streams": has_streams,
        "sport_types": sport_types,
        "current_sport_type": sport_type,
    })
