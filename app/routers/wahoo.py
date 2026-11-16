import secrets
from urllib.parse import quote_plus

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.database import get_db
from app.services import wahoo_client, wahoo_sync

router = APIRouter()

STATE_COOKIE = "wahoo_oauth_state"


def _flash(path: str, msg: str) -> RedirectResponse:
    return RedirectResponse(f"{path}?flash={quote_plus(msg)}", status_code=303)


@router.post("/settings/wahoo")
async def save_wahoo_settings(request: Request):
    form = await request.form()
    client_id = form.get("client_id", "").strip()
    client_secret = form.get("client_secret", "").strip()
    redirect_uri = form.get("redirect_uri", "").strip() or wahoo_client.DEFAULT_REDIRECT_URI

    if not client_id or not client_secret:
        return _flash("/settings", "Wahoo Client ID and Secret are required")

    wahoo_client.save_auth(client_id, client_secret, redirect_uri)
    return _flash("/settings", "Wahoo settings saved")


@router.get("/wahoo/connect")
def wahoo_connect():
    state = secrets.token_urlsafe(24)
    auth_url = wahoo_client.get_authorize_url(state)
    if not auth_url:
        return _flash("/settings", "Save your Wahoo Client ID and Secret first")
    resp = RedirectResponse(auth_url)
    resp.set_cookie(STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax")
    return resp


@router.get("/wahoo/redirect")
def wahoo_redirect(request: Request):
    code = request.query_params.get("code")
    error = request.query_params.get("error")
    state = request.query_params.get("state")
    expected = request.cookies.get(STATE_COOKIE)

    if error:
        resp = _flash("/settings", f"Wahoo authorization denied: {error}")
    elif not code:
        resp = _flash("/settings", "No authorization code received from Wahoo")
    elif not expected or not state or not secrets.compare_digest(state, expected):
        resp = _flash("/settings", "Wahoo authorization failed: state mismatch, please try again")
    else:
        try:
            wahoo_client.exchange_code(code)
            resp = _flash("/settings", "Connected to Wahoo!")
        except Exception as e:
            resp = _flash("/settings", f"Wahoo error: {e}")
    resp.delete_cookie(STATE_COOKIE)
    return resp


@router.post("/wahoo/disconnect")
def wahoo_disconnect():
    try:
        wahoo_client.deauthorize()
        return _flash("/settings", "Disconnected from Wahoo")
    except Exception as e:
        return _flash("/settings", f"Disconnected locally, but Wahoo revoke failed: {e}")


@router.post("/wahoo/sync")
def wahoo_sync_route():
    db = get_db()
    try:
        result = wahoo_sync.sync_workouts(db, full=False)
        return _flash("/", result.message())
    except Exception as e:
        return _flash("/", f"Wahoo sync error: {e}")
    finally:
        db.close()


@router.post("/wahoo/sync-zones")
def wahoo_sync_zones():
    db = get_db()
    try:
        return _flash("/settings", wahoo_sync.sync_power_zones(db))
    except Exception as e:
        return _flash("/settings", f"Wahoo zone import error: {e}")
    finally:
        db.close()
