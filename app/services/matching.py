from __future__ import annotations

from datetime import timedelta

from app.config import get_settings
from app.schemas.activity import ParsedActivity


def _as_parsed(d: dict) -> ParsedActivity:
    return ParsedActivity.model_validate(d)


def activities_overlap(a: ParsedActivity, b: ParsedActivity) -> bool:
    s = get_settings()
    tol = timedelta(seconds=s.match_start_tolerance_seconds)

    if abs(a.start_time_utc - b.start_time_utc) <= tol:
        da = a.duration_seconds
        db = b.duration_seconds
        if da is None or db is None or da <= 0 or db <= 0:
            return True
        ratio = abs(da - db) / max(da, db)
        return ratio <= s.match_duration_tolerance_ratio

    a_end = a.end_time_utc
    b_end = b.end_time_utc
    if a.duration_seconds and not a_end:
        a_end = a.start_time_utc + timedelta(seconds=a.duration_seconds)
    if b.duration_seconds and not b_end:
        b_end = b.start_time_utc + timedelta(seconds=b.duration_seconds)
    if a_end is None or b_end is None:
        return False

    latest_start = max(a.start_time_utc, b.start_time_utc)
    earliest_end = min(a_end, b_end)
    return latest_start < earliest_end + tol


def cluster_import_indices(parsed_rows: list[dict]) -> list[list[int]]:
    """Union-find clusters of imports that describe the same workout."""
    n = len(parsed_rows)
    parents = list(range(n))

    def find(i: int) -> int:
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parents[rj] = ri

    parsed = [_as_parsed(p) for p in parsed_rows]
    for i in range(n):
        for j in range(i + 1, n):
            if activities_overlap(parsed[i], parsed[j]):
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        r = find(i)
        clusters.setdefault(r, []).append(i)
    return list(clusters.values())
