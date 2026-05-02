from __future__ import annotations

from pathlib import Path

from app.parsers.fit_parser import parse_fit
from app.parsers.gpx_parser import parse_gpx
from app.parsers.tcx_parser import parse_tcx
from app.schemas.activity import ParsedActivity


def detect_format(path: Path) -> str | None:
    suf = path.suffix.lower()
    if suf == ".fit":
        return "fit"
    if suf == ".gpx":
        return "gpx"
    if suf == ".tcx":
        return "tcx"
    return None


def parse_file(path: Path) -> ParsedActivity:
    fmt = detect_format(path)
    if fmt == "fit":
        return parse_fit(path)
    if fmt == "gpx":
        return parse_gpx(path)
    if fmt == "tcx":
        return parse_tcx(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")
