from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fitparse import FitFile

from app.schemas.activity import ParsedActivity


def parse_fit(path: Path) -> ParsedActivity:
    fit = FitFile(str(path))

    start = None
    end = None
    sport = None
    distance_m = None
    duration_s = None
    elev_gain = None
    session_hr_avg = None
    session_hr_max = None
    title = None

    for msg in fit.get_messages("session"):
        vals = {f.name: f.value for f in msg.fields}
        if vals.get("sport"):
            sport = str(vals["sport"])
        if vals.get("total_timer_time") is not None:
            duration_s = float(vals["total_timer_time"])
        if vals.get("total_distance") is not None:
            distance_m = float(vals["total_distance"])
        if vals.get("total_ascent") is not None:
            elev_gain = float(vals["total_ascent"])
        if vals.get("avg_heart_rate") is not None:
            session_hr_avg = float(vals["avg_heart_rate"])
        if vals.get("max_heart_rate") is not None:
            session_hr_max = int(vals["max_heart_rate"])
        ts = vals.get("start_time")
        if isinstance(ts, datetime):
            start = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    if start is None:
        for msg in fit.get_messages("activity"):
            vals = {f.name: f.value for f in msg.fields}
            ts = vals.get("timestamp")
            if isinstance(ts, datetime):
                start = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
                break

    records_start = None
    records_end = None
    rec_hr_sum = 0.0
    rec_hr_cnt = 0
    rec_hr_max = None
    for msg in fit.get_messages("record"):
        vals = {f.name: f.value for f in msg.fields}
        ts = vals.get("timestamp")
        if isinstance(ts, datetime):
            tt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            records_end = tt
            if records_start is None:
                records_start = tt
        if vals.get("heart_rate") is not None:
            rec_hr_sum += float(vals["heart_rate"])
            rec_hr_cnt += 1
            h = int(vals["heart_rate"])
            rec_hr_max = h if rec_hr_max is None else max(rec_hr_max, h)

    if start is None and records_start is not None:
        start = records_start
    if records_end is not None:
        end = records_end

    if duration_s is None and start is not None and end is not None:
        duration_s = max(0.0, (end - start).total_seconds())

    if session_hr_avg is not None:
        hr_avg = int(round(session_hr_avg))
    elif rec_hr_cnt:
        hr_avg = int(round(rec_hr_sum / rec_hr_cnt))
    else:
        hr_avg = None

    if session_hr_max is not None:
        hr_max = session_hr_max
    else:
        hr_max = rec_hr_max

    detail: dict = {"file": path.name}
    for msg in fit.get_messages("file_id"):
        vals = {f.name: f.value for f in msg.fields}
        if vals.get("time_created"):
            detail["device_created"] = str(vals["time_created"])
        break

    return ParsedActivity(
        start_time_utc=start or datetime.now(tz=timezone.utc),
        end_time_utc=end,
        duration_seconds=duration_s,
        sport=sport,
        title=title,
        distance_m=distance_m,
        elevation_gain_m=elev_gain,
        hr_avg=hr_avg,
        hr_max=hr_max,
        source_format="fit",
        source_detail=detail,
    )
