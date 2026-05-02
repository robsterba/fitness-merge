from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ParsedActivity(BaseModel):
    """Normalized activity extracted from FIT, GPX, TCX, or Strava JSON."""

    start_time_utc: datetime
    end_time_utc: datetime | None = None
    duration_seconds: float | None = None
    sport: str | None = None
    title: str | None = None

    distance_m: float | None = None
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    hr_avg: int | None = None
    hr_max: int | None = None

    source_format: str = Field(description="fit, gpx, tcx, strava")
    source_detail: dict[str, Any] = Field(default_factory=dict)

    def model_dump_json_safe(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
