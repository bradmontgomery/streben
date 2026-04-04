import time
import requests
from app.database import get_db


STRAVA_BASE_URL = "https://www.strava.com/api/v3"
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"


def get_auth():
    db = get_db()
    row = db.execute("SELECT * FROM strava_auth WHERE id = 1").fetchone()
    db.close()
    if row:
        return dict(row)
    return None


def save_auth(client_id: str, client_secret: str):
    db = get_db()
    db.execute(
        """INSERT INTO strava_auth (id, client_id, client_secret)
           VALUES (1, ?, ?)
           ON CONFLICT(id) DO UPDATE SET client_id=excluded.client_id, client_secret=excluded.client_secret""",
        (client_id, client_secret),
    )
    db.commit()
    db.close()


def save_tokens(access_token: str, refresh_token: str, expires_at: int):
    db = get_db()
    db.execute(
        "UPDATE strava_auth SET access_token=?, refresh_token=?, expires_at=? WHERE id=1",
        (access_token, refresh_token, expires_at),
    )
    db.commit()
    db.close()


def get_authorize_url(redirect_uri: str) -> str | None:
    auth = get_auth()
    if not auth:
        return None
    scopes = "read,read_all,activity:read,activity:read_all"
    return (
        f"{STRAVA_AUTH_URL}?client_id={auth['client_id']}"
        f"&response_type=code&redirect_uri={redirect_uri}"
        f"&approval_prompt=force&scope={scopes}"
    )


def exchange_code(code: str) -> dict:
    auth = get_auth()
    resp = requests.post(STRAVA_TOKEN_URL, data={
        "client_id": auth["client_id"],
        "client_secret": auth["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    data = resp.json()
    save_tokens(data["access_token"], data["refresh_token"], data["expires_at"])
    return data


def _ensure_valid_token() -> str:
    auth = get_auth()
    if not auth or not auth["access_token"]:
        raise RuntimeError("Not connected to Strava")

    if auth["expires_at"] and auth["expires_at"] < time.time():
        resp = requests.post(STRAVA_TOKEN_URL, data={
            "client_id": auth["client_id"],
            "client_secret": auth["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": auth["refresh_token"],
        })
        resp.raise_for_status()
        data = resp.json()
        save_tokens(data["access_token"], data["refresh_token"], data["expires_at"])
        return data["access_token"]

    return auth["access_token"]


def _headers() -> dict:
    token = _ensure_valid_token()
    return {"Authorization": f"Bearer {token}"}


def get_athlete() -> dict:
    resp = requests.get(f"{STRAVA_BASE_URL}/athlete", headers=_headers())
    resp.raise_for_status()
    return resp.json()


def get_all_activities(per_page: int = 100) -> list[dict]:
    all_activities = []
    page = 1
    while True:
        resp = requests.get(
            f"{STRAVA_BASE_URL}/athlete/activities",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_activities.extend(batch)
        page += 1
    return all_activities


def get_activity_streams(activity_id: int) -> list[dict]:
    stream_types = ["time", "distance", "heartrate", "cadence", "watts", "altitude", "latlng"]
    resp = requests.get(
        f"{STRAVA_BASE_URL}/activities/{activity_id}/streams",
        headers=_headers(),
        params={"keys": ",".join(stream_types), "key_by_type": ""},
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json()
