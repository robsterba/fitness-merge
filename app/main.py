from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette import status

from app.config import get_settings
from app.db.models import CanonicalWorkout, OAuthToken, WorkoutImport
from app.db.session import get_db, init_db
from app.integrations import strava as strava_api
from app.services.ingest import ingest_path, scan_directory, ingest_strava_activity
from app.services.merge import rebuild_all_canonical
from app.services.strava_tokens import get_valid_strava_access_token

_oauth_states: set[str] = set()

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _oauth_success_page() -> str:
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Strava connected</title>
<style>
body{font-family:system-ui,sans-serif;background:#0f1419;color:#e6edf3;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;padding:1rem;}
.card{max-width:28rem;background:#1a2332;border:1px solid #2d3a4f;border-radius:10px;padding:1.5rem;text-align:center;}
a{color:#3b82f6;}
</style></head>
<body><div class="card"><h1 style="margin:0 0 .5rem;font-size:1.2rem">Strava connected</h1>
<p style="color:#8b9cb3;margin:0 0 1rem">You can close this tab or return to the dashboard.</p>
<p><a href="/">Open dashboard</a> · <a href="/docs">API docs</a></p></div></body></html>"""


def _oauth_error_page(message: str) -> str:
    safe = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Strava error</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0f1419;color:#fca5a5;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;padding:1rem;}}
.card{{max-width:28rem;background:#1a2332;border:1px solid #7f1d1d;border-radius:10px;padding:1.5rem;text-align:center;}}
a{{color:#3b82f6;}}
</style></head>
<body><div class="card"><h1 style="margin:0 0 .5rem;font-size:1.2rem">Strava authorization failed</h1>
<p style="color:#e6edf3;margin:0 0 1rem">{safe}</p>
<p><a href="/">Back to dashboard</a></p></div></body></html>"""


@asynccontextmanager
async def lifespan(_: Any):
    init_db()
    yield


def create_app():
    from fastapi import FastAPI

    app = FastAPI(title="Fitness merge", version="0.1.0", lifespan=lifespan)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def ui_root() -> FileResponse:
        index = STATIC_DIR / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404, detail="UI not found")
        return FileResponse(index)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config")
    def api_config() -> dict[str, Any]:
        s = get_settings()
        return {
            "import_dir": s.import_dir,
            "strava_redirect_uri": s.strava_redirect_uri,
            "public_base_url": s.public_base_url,
            "strava_configured": bool(s.strava_client_id and s.strava_client_secret),
        }

    @app.get("/api/summary")
    def api_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
        n_imp = db.scalar(select(func.count()).select_from(WorkoutImport)) or 0
        n_can = db.scalar(select(func.count()).select_from(CanonicalWorkout)) or 0
        tok = db.execute(
            select(OAuthToken).where(OAuthToken.provider == "strava")
        ).scalar_one_or_none()
        return {
            "imports": int(n_imp),
            "canonical_workouts": int(n_can),
            "strava_connected": tok is not None,
        }

    @app.post("/imports/scan")
    def import_scan(
        db: Session = Depends(get_db),
    ) -> dict[str, int | str]:
        s = get_settings()
        root = Path(s.import_dir)
        rows = scan_directory(db, root)
        return {"imported": len(rows), "directory": str(root)}

    @app.post("/imports/upload")
    async def import_upload(
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        s = get_settings()
        root = Path(s.import_dir)
        root.mkdir(parents=True, exist_ok=True)
        name = Path(file.filename or "upload").name
        if not name or name in (".", ".."):
            name = "upload"
        dest = root / name
        data = await file.read()
        dest.write_bytes(data)
        row = ingest_path(db, dest, import_root=root, force=True)
        if not row:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        db.commit()
        return {"id": row.id, "origin_key": row.origin_key, "format": row.format}

    @app.get("/imports")
    def list_imports(
        db: Session = Depends(get_db),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        total = db.scalar(select(func.count()).select_from(WorkoutImport)) or 0
        rows = db.execute(
            select(WorkoutImport)
            .order_by(WorkoutImport.start_time.desc())
            .limit(limit)
            .offset(offset)
        ).scalars().all()
        return {
            "items": [
                {
                    "id": r.id,
                    "origin_key": r.origin_key,
                    "format": r.format,
                    "start_time": r.start_time.isoformat(),
                }
                for r in rows
            ],
            "total": int(total),
            "limit": limit,
            "offset": offset,
        }

    @app.post("/merge/rebuild")
    def merge_rebuild(db: Session = Depends(get_db)) -> dict[str, int]:
        n = rebuild_all_canonical(db)
        return {"canonical_workouts": n}

    @app.get("/activities")
    def list_activities(
        db: Session = Depends(get_db),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        total = db.scalar(select(func.count()).select_from(CanonicalWorkout)) or 0
        rows = db.execute(
            select(CanonicalWorkout)
            .order_by(CanonicalWorkout.start_time.desc())
            .limit(limit)
            .offset(offset)
        ).scalars().all()
        return {
            "items": [
                {
                    "id": r.id,
                    "start_time": r.start_time.isoformat(),
                    "end_time": r.end_time.isoformat() if r.end_time else None,
                    "sport": r.sport,
                    "merged": r.merged,
                }
                for r in rows
            ],
            "total": int(total),
            "limit": limit,
            "offset": offset,
        }

    @app.get("/auth/strava")
    def strava_auth() -> RedirectResponse:
        s = get_settings()
        if not s.strava_client_id or not s.strava_client_secret:
            raise HTTPException(
                status_code=503,
                detail="Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET",
            )
        state = secrets.token_urlsafe(32)
        _oauth_states.add(state)
        url = strava_api.strava_authorize_url(state)
        return RedirectResponse(url, status_code=status.HTTP_302_FOUND)

    @app.get("/auth/strava/callback", response_class=HTMLResponse)
    def strava_callback(
        code: str = Query(...),
        state: str = Query(...),
        error: str | None = None,
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        if error:
            return HTMLResponse(
                _oauth_error_page(error),
                status_code=400,
            )
        if state not in _oauth_states:
            return HTMLResponse(
                _oauth_error_page("Invalid OAuth state — start again from the app."),
                status_code=400,
            )
        _oauth_states.discard(state)

        try:
            data = strava_api.exchange_code_for_token(code)
        except Exception as e:
            return HTMLResponse(
                _oauth_error_page(str(e)),
                status_code=400,
            )

        row = db.execute(
            select(OAuthToken).where(OAuthToken.provider == "strava")
        ).scalar_one_or_none()
        exp = strava_api.token_expires_at(data.get("expires_in"))
        if row:
            row.access_token = data["access_token"]
            row.refresh_token = data.get("refresh_token", "")
            row.expires_at = exp
        else:
            row = OAuthToken(
                provider="strava",
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", ""),
                expires_at=exp,
            )
            db.add(row)
        db.commit()
        return HTMLResponse(_oauth_success_page())

    @app.post("/sync/strava")
    def strava_sync(
        db: Session = Depends(get_db),
        days: int = Query(14, ge=1, le=365),
    ) -> dict[str, int]:
        try:
            token = get_valid_strava_access_token(db)
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        since = int(datetime.now(tz=timezone.utc).timestamp()) - days * 86400
        acts: list[dict] = []
        for page in range(1, 50):
            batch = strava_api.fetch_activities(token, after=since, per_page=100, page=page)
            if not batch:
                break
            acts.extend(batch)
            if len(batch) < 100:
                break
        n = 0
        for a in acts:
            sid = a.get("id")
            if sid is None:
                continue
            parsed = strava_api.strava_activity_to_parsed(a)
            ingest_strava_activity(db, parsed, int(sid))
            n += 1
        db.commit()
        return {"strava_activities_upserted": n}

    return app


app = create_app()
