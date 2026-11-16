import tempfile
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.services.activity_store import insert_activity
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

    act["name"] = act.get("name") or file.filename

    db = get_db()
    activity_id = insert_activity(
        db, act, streams, source="fit_upload", fit_filename=file.filename,
    )

    db.commit()
    db.close()

    return RedirectResponse(f"/activities/{activity_id}", status_code=303)
