from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.services import energy as energy_service
from app.services import nutrition as nutrition_service
from app.services.cronometer import CronometerParseError, parse_biometrics, parse_daily_summary
from app.services.ranges import resolve_dates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/nutrition")
def nutrition_page(request: Request, range: str = "3m", page: int = 1, per_page: int = 100):
    page = max(1, page)
    per_page = max(1, min(per_page, 500))

    start, end = resolve_dates(range)
    days = energy_service.energy_balance(start, end)
    days.reverse()  # newest first, matching the activity dashboard

    # Summary covers the whole range, not just the page in view.
    logged = [d for d in days if d.balance is not None]
    summary = {
        "logged_days": len(logged),
        "total_balance": sum(d.balance for d in logged) if logged else None,
        "mean_balance": (sum(d.balance for d in logged) / len(logged)) if logged else None,
    }

    total = len(days)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    page_days = days[offset:offset + per_page]

    settings = energy_service.get_nutrition_settings()
    configured = bool(settings.get("height_in") and settings.get("birth_date"))

    return templates.TemplateResponse(request, "nutrition.html", {
        "days": page_days,
        "summary": summary,
        "current_range": range,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "configured": configured,
        "carb_rate": settings.get("carb_rate_g_per_hr") or 0,
        "flash": request.query_params.get("flash"),
    })


@router.get("/nutrition/upload")
def nutrition_upload_page(request: Request):
    return templates.TemplateResponse(request, "nutrition_upload.html", {
        "flash": request.query_params.get("flash"),
    })


@router.post("/nutrition/upload")
async def nutrition_upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return RedirectResponse("/nutrition/upload?flash=Please+upload+a+.csv+file", status_code=303)

    content = await file.read()
    try:
        rows, skipped = parse_daily_summary(content)
    except CronometerParseError as e:
        return RedirectResponse(f"/nutrition/upload?flash={quote(str(e))}", status_code=303)

    db = get_db()
    nutrition_service.upsert_nutrition_rows(db, rows)
    db.commit()
    db.close()

    logged = sum(1 for r in rows if r["energy_kcal"] is not None)
    msg = f"Imported {len(rows)} days ({logged} logged, {len(rows) - logged} blank)"
    if skipped:
        msg += f", {skipped} skipped"
    return RedirectResponse(f"/nutrition?flash={quote(msg)}", status_code=303)


@router.get("/api/nutrition-trends")
def nutrition_trends(range: str = "6m"):
    start, end = resolve_dates(range, default="6m")
    days = energy_service.energy_balance(start, end)

    def col(attr, nd=1):
        return [None if getattr(d, attr) is None else round(getattr(d, attr), nd) for d in days]

    logged = [d for d in days if d.balance is not None]
    total = sum(d.balance for d in logged) if logged else None
    data = {
        "dates": [d.date for d in days],
        "intake_logged": col("intake_logged"),
        "intake_onbike_est": col("intake_onbike_est"),
        "ride_kcal": [None if d.ride_kj is None else round(d.ride_kj * energy_service.KJ_TO_KCAL, 1)
                      for d in days],
        "baseline_tdee": col("baseline_tdee"),
        "need": col("need"),
        "balance": col("balance"),
        "cumulative_balance": col("cumulative_balance"),
        "is_logged": [d.is_logged for d in days],
        "weight_lb": col("weight_lb"),
        "configured": days[0].baseline_tdee is not None if days else False,
        "summary": {
            "logged_days": len(logged),
            "total_balance": round(total, 1) if total is not None else None,
            "mean_balance": round(total / len(logged), 1) if logged else None,
        },
    }
    return JSONResponse(data)


@router.post("/settings/nutrition")
async def save_nutrition_settings_route(request: Request):
    form = await request.form()
    try:
        height_in = float(form.get("height_in", ""))
        activity_multiplier = float(form.get("activity_multiplier", ""))
        carb_rate = float(form.get("carb_rate_g_per_hr", ""))
    except ValueError:
        return RedirectResponse("/settings?flash=Body+metrics+must+be+numbers", status_code=303)

    birth_date = (form.get("birth_date") or "").strip()
    try:
        date.fromisoformat(birth_date)
    except ValueError:
        return RedirectResponse("/settings?flash=Birth+date+must+be+YYYY-MM-DD", status_code=303)

    sex = (form.get("sex") or "male").strip().lower()
    if sex not in ("male", "female"):
        return RedirectResponse("/settings?flash=Sex+must+be+male+or+female", status_code=303)
    if not 1.0 <= activity_multiplier <= 2.5:
        return RedirectResponse("/settings?flash=Activity+multiplier+must+be+1.0-2.5", status_code=303)
    if not 0 <= carb_rate <= 150:
        return RedirectResponse("/settings?flash=Carb+rate+must+be+0-150+g/hr", status_code=303)

    energy_service.save_nutrition_settings(height_in, birth_date, sex, activity_multiplier, carb_rate)
    return RedirectResponse("/settings?flash=Body+metrics+saved", status_code=303)


@router.post("/settings/weight")
async def save_weight(request: Request):
    form = await request.form()
    entry_date = (form.get("date") or "").strip()
    try:
        date.fromisoformat(entry_date)
        weight_lb = float(form.get("weight_lb", ""))
    except ValueError:
        return RedirectResponse("/settings?flash=Enter+a+valid+date+and+weight", status_code=303)
    if not 50 <= weight_lb <= 700:
        return RedirectResponse("/settings?flash=Weight+looks+out+of+range", status_code=303)

    db = get_db()
    nutrition_service.upsert_weights(db, [{"date": entry_date, "weight_lb": weight_lb}])
    db.commit()
    db.close()
    return RedirectResponse("/settings?flash=Weight+entry+saved", status_code=303)


@router.post("/settings/weight/delete")
async def remove_weight(request: Request):
    form = await request.form()
    entry_date = (form.get("date") or "").strip()
    if entry_date:
        nutrition_service.delete_weight(entry_date)
    return RedirectResponse("/settings?flash=Weight+entry+deleted", status_code=303)


@router.post("/settings/biometrics")
async def upload_biometrics(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return RedirectResponse("/settings?flash=Please+upload+a+.csv+file", status_code=303)
    try:
        entries = parse_biometrics(await file.read())
    except CronometerParseError as e:
        return RedirectResponse(f"/settings?flash={quote(str(e))}", status_code=303)

    db = get_db()
    nutrition_service.upsert_weights(db, entries, source="cronometer")
    db.commit()
    db.close()
    return RedirectResponse(f"/settings?flash={quote(f'Imported {len(entries)} weight entries')}",
                            status_code=303)
