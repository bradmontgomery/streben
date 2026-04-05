import tempfile
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.services.fit_parser import parse_fit_file

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/upload")
def upload_page(request: Request):
    flash = request.query_params.get("flash")
    return templates.TemplateResponse(request, "fit_upload.html", {
        "flash": flash,
    })


@router.post("/upload")
async def upload_fit(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".fit"):
        return RedirectResponse("/upload?flash=Please+upload+a+.fit+file", status_code=303)

    # Save to temp file for parsing
    with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = parse_fit_file(tmp_path)
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        return RedirectResponse(f"/upload?flash=Error+parsing+FIT+file:+{e}", status_code=303)

    Path(tmp_path).unlink(missing_ok=True)

    act = result["activity"]
    streams = result["streams"]

    db = get_db()
    db.execute(
        """INSERT INTO activities
           (source, name, sport_type, start_date, moving_time, elapsed_time,
            distance, average_watts, max_watts, weighted_average_watts,
            average_heartrate, max_heartrate, average_cadence, average_speed, max_speed,
            elev_high, elev_low, kilojoules, fit_filename)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "fit_upload",
            act.get("name") or file.filename,
            act.get("sport_type"),
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
            file.filename,
        ),
    )
    activity_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    for s in streams:
        db.execute(
            """INSERT INTO activity_streams
               (activity_id, timestamp_offset, watts, heartrate, cadence, distance, speed, altitude, lat, lng)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (activity_id, s.timestamp_offset, s.watts, s.heartrate, s.cadence,
             s.distance, s.speed, s.altitude, s.lat, s.lng),
        )

    db.commit()
    db.close()

    return RedirectResponse(f"/activities/{activity_id}", status_code=303)
