from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.models import Activity

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def dashboard(request: Request, page: int = 1, per_page: int = 100):
    page = max(1, page)
    per_page = max(1, min(per_page, 500))
    offset = (page - 1) * per_page

    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    rows = db.execute(
        "SELECT * FROM activities ORDER BY start_date DESC LIMIT ? OFFSET ?",
        (per_page, offset),
    ).fetchall()
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
    })
