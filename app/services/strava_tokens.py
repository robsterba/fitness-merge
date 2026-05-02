from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OAuthToken
from app.integrations.strava import refresh_token, token_expires_at


def get_valid_strava_access_token(session: Session) -> str:
    row = session.execute(
        select(OAuthToken).where(OAuthToken.provider == "strava")
    ).scalar_one_or_none()
    if not row:
        raise RuntimeError("Strava is not connected")

    now = datetime.now(tz=timezone.utc)
    if row.expires_at and row.expires_at <= now + timedelta(minutes=2) and row.refresh_token:
        data = refresh_token(row.refresh_token)
        row.access_token = data["access_token"]
        if data.get("refresh_token"):
            row.refresh_token = data["refresh_token"]
        row.expires_at = token_expires_at(data.get("expires_in"))
        session.add(row)
        session.commit()

    return row.access_token
