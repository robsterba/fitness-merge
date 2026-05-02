from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.schemas.activity import ParsedActivity

STRAVA_AUTH = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN = "https://www.strava.com/oauth/token"
STRAVA_API = "https://www.strava.com/api/v3"


def strava_authorize_url(state: str) -> str:
    s = get_settings()
    if not s.strava_client_id:
        raise RuntimeError("STRAVA_CLIENT_ID is not set")
    q = urlencode(
        {
            "client_id": s.strava_client_id,
            "redirect_uri": s.strava_redirect_uri,
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": "activity:read,activity:read_all",
            "state": state,
        }
    )
    return f"{STRAVA_AUTH}?{q}"


def exchange_code_for_token(code: str) -> dict[str, Any]:
    s = get_settings()
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            STRAVA_TOKEN,
            data={
                "client_id": s.strava_client_id,
                "client_secret": s.strava_client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
    r.raise_for_status()
    return r.json()


def refresh_token(refresh: str) -> dict[str, Any]:
    s = get_settings()
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            STRAVA_TOKEN,
            data={
                "client_id": s.strava_client_id,
                "client_secret": s.strava_client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
    r.raise_for_status()
    return r.json()


def strava_activity_to_parsed(data: dict[str, Any]) -> ParsedActivity:
    start_raw = data.get("start_date")
    if not start_raw:
        raise ValueError("Strava activity missing start_date")
    text = str(start_raw).replace("Z", "+00:00")
    start = datetime.fromisoformat(text)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)

    elapsed = data.get("elapsed_time")
    duration_s = float(elapsed) if elapsed is not None else None
    end = None
    if duration_s is not None:
        end = start + timedelta(seconds=duration_s)

    dist = data.get("distance")
    gain = data.get("total_elevation_gain")
    hr_a = data.get("average_heartrate")
    hr_m = data.get("max_heartrate")

    return ParsedActivity(
        start_time_utc=start,
        end_time_utc=end,
        duration_seconds=duration_s,
        sport=str(data.get("type") or data.get("sport_type") or "") or None,
        title=data.get("name"),
        distance_m=float(dist) if dist is not None else None,
        elevation_gain_m=float(gain) if gain is not None else None,
        hr_avg=int(hr_a) if hr_a is not None else None,
        hr_max=int(hr_m) if hr_m is not None else None,
        source_format="strava",
        source_detail={
            "strava_id": data.get("id"),
            "external_id": data.get("external_id"),
        },
    )


def fetch_activities(
    access_token: str,
    *,
    after: int | None = None,
    per_page: int = 50,
    page: int = 1,
) -> list[dict[str, Any]]:
    params: dict[str, str | int] = {"per_page": per_page, "page": page}
    if after is not None:
        params["after"] = after
    with httpx.Client(timeout=60.0) as client:
        r = client.get(
            f"{STRAVA_API}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
    r.raise_for_status()
    return r.json()


def token_expires_at(expires_in: int | None) -> datetime | None:
    if not expires_in:
        return None
    return datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc)
