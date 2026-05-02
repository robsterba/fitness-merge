from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.activity import ParsedActivity

TCX = "{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}"


def _parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    text = text.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_tcx(path: Path) -> ParsedActivity:
    tree = ET.parse(path)
    root = tree.getroot()

    start = None
    end = None
    distance_m = 0.0
    elev_gain = 0.0
    hr_sum = 0.0
    hr_cnt = 0
    hr_max = None
    sport = None
    title = None

    for activity in root.findall(f".//{TCX}Activity"):
        if sport is None:
            st = activity.get("Sport")
            if st:
                sport = st
        for lap in activity.findall(f"{TCX}Lap"):
            t0 = _parse_time(lap.findtext(f"{TCX}StartTime"))
            if t0 and (start is None or t0 < start):
                start = t0
            dist_el = lap.find(f"{TCX}DistanceMeters")
            if dist_el is not None and dist_el.text:
                try:
                    distance_m += float(dist_el.text)
                except ValueError:
                    pass
            total_s = lap.findtext(f"{TCX}TotalTimeSeconds")
            dur = None
            if total_s:
                try:
                    dur = float(total_s)
                except ValueError:
                    dur = None
            if t0 and dur is not None:
                lap_end = t0.timestamp() + dur
                end_dt = datetime.fromtimestamp(lap_end, tz=timezone.utc)
                end = end_dt if end is None or end_dt > end else end

            last_el = None
            for tp in lap.findall(f".//{TCX}Trackpoint"):
                tt = _parse_time(tp.findtext(f"{TCX}Time"))
                if tt:
                    start = tt if start is None or tt < start else start
                    end = tt if end is None or tt > end else end
                alt = tp.find(f"{TCX}AltitudeMeters")
                if alt is not None and alt.text:
                    try:
                        el = float(alt.text)
                        if last_el is not None and el > last_el:
                            elev_gain += el - last_el
                        last_el = el
                    except ValueError:
                        pass
                hr_el = tp.find(f"{TCX}HeartRateBpm/{TCX}Value")
                if hr_el is not None and hr_el.text:
                    try:
                        h = int(float(hr_el.text))
                        hr_sum += h
                        hr_cnt += 1
                        hr_max = h if hr_max is None else max(hr_max, h)
                    except ValueError:
                        pass

    notes = root.find(f".//{TCX}Notes")
    if notes is not None and notes.text:
        title = notes.text.strip()

    duration_s = None
    if start and end:
        duration_s = max(0.0, (end - start).total_seconds())

    hr_avg = int(round(hr_sum / hr_cnt)) if hr_cnt else None

    return ParsedActivity(
        start_time_utc=start or datetime.now(tz=timezone.utc),
        end_time_utc=end,
        duration_seconds=duration_s,
        sport=sport,
        title=title,
        distance_m=distance_m if distance_m > 0 else None,
        elevation_gain_m=elev_gain if elev_gain > 0 else None,
        hr_avg=hr_avg,
        hr_max=hr_max,
        source_format="tcx",
        source_detail={"file": path.name},
    )
