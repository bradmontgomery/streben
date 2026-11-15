"""Wahoo Cloud API client. See https://cloud-api.wahooligan.com

Credentials and tokens live in the single-row `wahoo_auth` table, mirroring strava_client.
"""
import os
import time
from urllib.parse import urlencode

import requests

from app.database import get_db

WAHOO_BASE_URL = "https://api.wahooligan.com"
WAHOO_AUTH_URL = f"{WAHOO_BASE_URL}/oauth/authorize"
WAHOO_TOKEN_URL = f"{WAHOO_BASE_URL}/oauth/token"
WAHOO_SCOPES = "email power_zones_read workouts_read plans_read routes_read offline_data user_read"
DEFAULT_REDIRECT_URI = "https://localhost:8000/wahoo/redirect"

# Refresh this many seconds before the token actually expires (tokens last 2 hours).
REFRESH_MARGIN_S = 300
TIMEOUT_S = 30


class WahooError(RuntimeError):
    pass


class WahooRateLimited(WahooError):
    def __init__(self, reset_s: int | None):
        self.reset_s = reset_s
        when = f" Try again in ~{(reset_s + 59) // 60} min." if reset_s else ""
        super().__init__(f"Wahoo API rate limit reached.{when}")


# --- credentials & tokens -------------------------------------------------------------

def get_auth() -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM wahoo_auth WHERE id = 1").fetchone()
    db.close()
    return dict(row) if row else None


def default_credentials() -> dict:
    """Pre-fill values for the settings form when nothing is saved yet."""
    return {
        "client_id": os.environ.get("WAHOO_CLIENT_ID", ""),
        "client_secret": os.environ.get("WAHOO_SECRET", ""),
        "redirect_uri": DEFAULT_REDIRECT_URI,
    }


def is_connected() -> bool:
    auth = get_auth()
    return bool(auth and auth.get("access_token"))


def save_auth(client_id: str, client_secret: str, redirect_uri: str):
    db = get_db()
    db.execute(
        """INSERT INTO wahoo_auth (id, client_id, client_secret, redirect_uri)
           VALUES (1, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET client_id=excluded.client_id,
             client_secret=excluded.client_secret, redirect_uri=excluded.redirect_uri""",
        (client_id, client_secret, redirect_uri),
    )
    db.commit()
    db.close()


def save_tokens(access_token: str | None, refresh_token: str | None, expires_at: int | None):
    db = get_db()
    db.execute(
        "UPDATE wahoo_auth SET access_token=?, refresh_token=?, expires_at=? WHERE id=1",
        (access_token, refresh_token, expires_at),
    )
    db.commit()
    db.close()


def _save_token_response(data: dict):
    expires_at = int(time.time()) + int(data.get("expires_in") or 7200)
    save_tokens(data["access_token"], data.get("refresh_token"), expires_at)


# --- OAuth ----------------------------------------------------------------------------

def get_authorize_url(state: str) -> str | None:
    auth = get_auth()
    if not auth or not auth.get("client_id"):
        return None
    params = {
        "client_id": auth["client_id"],
        "redirect_uri": auth.get("redirect_uri") or DEFAULT_REDIRECT_URI,
        "response_type": "code",
        "scope": WAHOO_SCOPES,
        "state": state,
    }
    return f"{WAHOO_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    auth = get_auth()
    if not auth:
        raise WahooError("Wahoo credentials are not set")
    resp = requests.post(WAHOO_TOKEN_URL, data={
        "client_id": auth["client_id"],
        "client_secret": auth["client_secret"],
        "code": code,
        "redirect_uri": auth.get("redirect_uri") or DEFAULT_REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=TIMEOUT_S)
    resp.raise_for_status()
    data = resp.json()
    _save_token_response(data)
    return data


def _ensure_valid_token() -> str:
    auth = get_auth()
    if not auth or not auth.get("access_token"):
        raise WahooError("Not connected to Wahoo")

    if auth.get("expires_at") and auth["expires_at"] - REFRESH_MARGIN_S < time.time():
        resp = requests.post(WAHOO_TOKEN_URL, data={
            "client_id": auth["client_id"],
            "client_secret": auth["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": auth["refresh_token"],
        }, timeout=TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
        # Persist before the next API call: Wahoo revokes the old pair once the new token is used.
        _save_token_response(data)
        return data["access_token"]

    return auth["access_token"]


# --- requests -------------------------------------------------------------------------

def _ints(header: str | None) -> list[int]:
    """Rate-limit headers carry one value per window (5-minute, hour, day), comma-separated."""
    nums = []
    for part in (header or "").replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            nums.append(int(part))
    return nums


def rate_limit_state(headers) -> tuple[bool, int | None]:
    """Return (exhausted, seconds_until_usable) from X-RateLimit-* headers.

    Remaining and Reset are paired by position, so a spent daily window reports the daily reset
    rather than the 5-minute one. If they can't be paired, the longest reset is the safe answer.
    """
    remaining = _ints(headers.get("X-RateLimit-Remaining"))
    resets = _ints(headers.get("X-RateLimit-Reset"))
    exhausted_idx = [i for i, r in enumerate(remaining) if r <= 0]
    if not exhausted_idx:
        return False, None
    if len(resets) == len(remaining):
        return True, max(resets[i] for i in exhausted_idx)
    return True, max(resets) if resets else None


def _request(method: str, path: str, **kwargs) -> requests.Response:
    token = _ensure_valid_token()
    resp = requests.request(
        method,
        f"{WAHOO_BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=TIMEOUT_S,
        **kwargs,
    )
    if resp.status_code == 429:
        _, reset_s = rate_limit_state(resp.headers)
        if reset_s is None:
            resets = _ints(resp.headers.get("X-RateLimit-Reset"))
            reset_s = max(resets) if resets else None
        raise WahooRateLimited(reset_s)
    resp.raise_for_status()
    return resp


def exhausted_limit(resp: requests.Response) -> WahooRateLimited | None:
    """If this (successful) response used up a rate-limit window, return the error to raise
    after processing it, so the next call isn't wasted on a 429."""
    exhausted, reset_s = rate_limit_state(resp.headers)
    return WahooRateLimited(reset_s) if exhausted else None


def get_user() -> dict:
    return _request("GET", "/v1/user").json()


def list_workouts(page: int = 1, per_page: int = 50) -> tuple[dict, WahooRateLimited | None]:
    """Return (page_json, pending_limit). pending_limit is set when this call used up the quota."""
    resp = _request("GET", "/v1/workouts", params={"page": page, "per_page": per_page})
    return resp.json(), exhausted_limit(resp)


def list_power_zones() -> list[dict]:
    data = _request("GET", "/v1/power_zones").json()
    if isinstance(data, dict):
        return data.get("power_zones") or []
    return data or []


def download_fit(url: str) -> bytes:
    """FIT files are plain downloads (no auth header) and don't count against rate limits."""
    resp = requests.get(url, timeout=TIMEOUT_S * 2)
    resp.raise_for_status()
    return resp.content


def deauthorize():
    """Revoke this app's access on Wahoo, then forget the tokens locally.

    Wahoo caps a user at 10 unrevoked tokens, so disconnect before reconnecting.
    """
    try:
        _request("DELETE", "/v1/permissions")
    finally:
        save_tokens(None, None, None)
