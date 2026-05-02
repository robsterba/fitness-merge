from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.parsers.registry import detect_format, parse_file
from app.schemas.activity import ParsedActivity
from app.db.models import WorkoutImport


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _origin_key_for_file(path: Path, root: Path) -> str:
    try:
        rel = path.resolve().relative_to(root.resolve())
        return f"file:{rel.as_posix()}"
    except ValueError:
        return f"file:{path.name}"


def ingest_path(
    session: Session, path: Path, *, import_root: Path, force: bool = False
) -> WorkoutImport | None:
    if not path.is_file():
        return None
    fmt = detect_format(path)
    if not fmt:
        return None

    origin = _origin_key_for_file(path, import_root)
    content_hash = _sha256_file(path)

    existing = session.execute(
        select(WorkoutImport).where(WorkoutImport.origin_key == origin)
    ).scalar_one_or_none()
    if existing and existing.content_sha256 == content_hash and not force:
        return existing

    parsed: ParsedActivity = parse_file(path)
    payload = parsed.model_dump_json_safe()
    now = datetime.now(tz=timezone.utc)

    if existing:
        existing.content_sha256 = content_hash
        existing.format = fmt
        existing.start_time = parsed.start_time_utc
        existing.parsed = payload
        session.flush()
        return existing

    row = WorkoutImport(
        origin_key=origin,
        format=fmt,
        content_sha256=content_hash,
        start_time=parsed.start_time_utc,
        parsed=payload,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def scan_directory(session: Session, directory: Path) -> list[WorkoutImport]:
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    out: list[WorkoutImport] = []
    for pattern in ("*.fit", "*.gpx", "*.tcx"):
        for path in sorted(directory.rglob(pattern)):
            row = ingest_path(session, path, import_root=directory)
            if row:
                out.append(row)
    session.commit()
    return out


def ingest_strava_activity(session: Session, parsed: ParsedActivity, strava_id: int) -> WorkoutImport:
    origin = f"strava:{strava_id}"
    existing = session.execute(
        select(WorkoutImport).where(WorkoutImport.origin_key == origin)
    ).scalar_one_or_none()

    payload = parsed.model_dump_json_safe()
    now = datetime.now(tz=timezone.utc)

    if existing:
        existing.format = "strava"
        existing.start_time = parsed.start_time_utc
        existing.parsed = payload
        existing.content_sha256 = None
        session.flush()
        return existing

    row = WorkoutImport(
        origin_key=origin,
        format="strava",
        content_sha256=None,
        start_time=parsed.start_time_utc,
        parsed=payload,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row
