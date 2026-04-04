from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.models import Activity

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def dashboard(request: Request):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM activities ORDER BY start_date DESC"
    ).fetchall()
    db.close()

    activities = [Activity.from_row(r) for r in rows]
    flash = request.query_params.get("flash")

    return templates.TemplateResponse(request, "dashboard.html", {
        "activities": activities,
        "flash": flash,
    })
