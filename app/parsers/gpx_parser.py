from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import gpxpy

from app.schemas.activity import ParsedActivity


def parse_gpx(path: Path) -> ParsedActivity:
    with path.open("rb") as f:
        gpx = gpxpy.parse(f)

    start = None
    end = None
    points = 0
    distance_m = 0.0
    elev_gain = 0.0

    for track in gpx.tracks:
        for seg in track.segments:
            points += len(seg.points)
            try:
                distance_m += float(seg.length_2d())
            except Exception:
                pass
            last_el = None
            for p in seg.points:
                if p.time:
                    tt = p.time
                    if tt.tzinfo is None:
                        tt = tt.replace(tzinfo=timezone.utc)
                    start = tt if start is None or tt < start else start
                    end = tt if end is None or tt > end else end
                if p.elevation is not None:
                    el = float(p.elevation)
                    if last_el is not None and el > last_el:
                        elev_gain += el - last_el
                    last_el = el

    duration_s = None
    if start and end:
        duration_s = max(0.0, (end - start).total_seconds())

    title = gpx.name or gpx.description

    return ParsedActivity(
        start_time_utc=start or end or datetime.now(tz=timezone.utc),
        end_time_utc=end,
        duration_seconds=duration_s,
        sport=None,
        title=title,
        distance_m=distance_m if distance_m > 0 else None,
        elevation_gain_m=elev_gain if elev_gain > 0 else None,
        source_format="gpx",
        source_detail={"file": path.name, "track_points": points},
    )
