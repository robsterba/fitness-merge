from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import CanonicalWorkout, CanonicalWorkoutSource, WorkoutImport
from app.schemas.activity import ParsedActivity
from app.services.matching import cluster_import_indices


def _label_from_format(fmt: str, origin_key: str) -> str:
    if fmt == "fit":
        return "garmin_fit"
    if fmt == "tcx":
        return "ifit_tcx" if "ifit" in origin_key.lower() else "tcx_file"
    if fmt == "gpx":
        return "gpx_file"
    if fmt == "strava":
        return "strava"
    return fmt


def _prefer_numeric(
    entries: list[tuple[str, float | int | None]],
) -> dict[str, Any] | None:
    best = None
    best_prio = -1
    priority = {
        "garmin_fit": 3,
        "gpx_file": 2,
        "tcx_file": 2,
        "ifit_tcx": 2,
        "strava": 1,
    }
    for label, val in entries:
        if val is None:
            continue
        p = priority.get(label, 0)
        if best is None or p > best_prio:
            best = {"value": val, "source": label}
            best_prio = p
    return best


def merge_cluster(imports: list[WorkoutImport]) -> dict[str, Any]:
    """Build merged JSON with provenance for one cluster of imports."""
    parsed_list = [ParsedActivity.model_validate(i.parsed) for i in imports]
    labels = [_label_from_format(i.format, i.origin_key) for i in imports]

    start_times = [p.start_time_utc for p in parsed_list]
    end_times = [p.end_time_utc for p in parsed_list if p.end_time_utc]
    start = min(start_times)
    end = max(end_times) if end_times else None

    sports = [p.sport for p in parsed_list if p.sport]
    sport = max(set(sports), key=sports.count) if sports else None

    titles = [p.title for p in parsed_list if p.title]
    title = titles[0] if titles else None

    merged: dict[str, Any] = {
        "start_time_utc": start.isoformat(),
        "end_time_utc": end.isoformat() if end else None,
        "sport": sport,
        "title": title,
        "fields": {},
    }

    def add_field(
        key: str,
        pairs: list[tuple[str, float | int | None]],
        *,
        prefer_high_for_gain: bool = False,
    ) -> None:
        cleaned = [(a, b) for a, b in pairs if b is not None]
        if not cleaned:
            return
        if prefer_high_for_gain and key == "elevation_gain_m":
            ifit = [(a, b) for a, b in cleaned if a == "ifit_tcx"]
            if ifit:
                label, val = ifit[0]
                merged["fields"][key] = {"value": val, "source": label}
                return
            label, val = max(cleaned, key=lambda x: float(x[1]))
            merged["fields"][key] = {"value": val, "source": label}
            return
        entry = _prefer_numeric([(a, float(b)) for a, b in cleaned])
        if entry:
            merged["fields"][key] = entry

    add_field(
        "distance_m",
        [(labels[i], parsed_list[i].distance_m) for i in range(len(parsed_list))],
    )
    add_field(
        "elevation_gain_m",
        [(labels[i], parsed_list[i].elevation_gain_m) for i in range(len(parsed_list))],
        prefer_high_for_gain=True,
    )
    add_field(
        "hr_avg",
        [(labels[i], parsed_list[i].hr_avg) for i in range(len(parsed_list))],
    )
    add_field(
        "hr_max",
        [(labels[i], parsed_list[i].hr_max) for i in range(len(parsed_list))],
    )

    return merged


def rebuild_all_canonical(session: Session) -> int:
    """Replace all canonical workouts by clustering every stored import."""
    session.execute(delete(CanonicalWorkout))
    session.commit()

    imports = list(session.execute(select(WorkoutImport).order_by(WorkoutImport.start_time)).scalars())
    if not imports:
        return 0

    rows = sorted(imports, key=lambda r: r.id)
    parsed_rows = [r.parsed for r in rows]
    clusters = cluster_import_indices(parsed_rows)

    created = 0
    now = datetime.now(tz=timezone.utc)
    for cluster in clusters:
        members = [rows[i] for i in cluster]
        merged = merge_cluster(members)
        cw = CanonicalWorkout(
            start_time=datetime.fromisoformat(merged["start_time_utc"]),
            end_time=(
                datetime.fromisoformat(merged["end_time_utc"])
                if merged.get("end_time_utc")
                else None
            ),
            sport=merged.get("sport"),
            merged=merged,
            created_at=now,
            updated_at=now,
        )
        session.add(cw)
        session.flush()
        for m in members:
            session.add(
                CanonicalWorkoutSource(
                    canonical_workout_id=cw.id,
                    workout_import_id=m.id,
                    label=_label_from_format(m.format, m.origin_key),
                )
            )
        created += 1

    session.commit()
    return created
