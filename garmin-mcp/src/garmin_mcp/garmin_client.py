"""Minimal client for the Garmin Health API body composition (weight) endpoint."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

BASE_URL = "https://apis.garmin.com/wellness-api/rest"
# Garmin limits each pull request to a 24-hour window.
MAX_WINDOW_SECONDS = 86400


class GarminClient:
    def __init__(self, access_token: str | None = None, http: httpx.Client | None = None) -> None:
        self._token = access_token or os.environ.get("GARMIN_ACCESS_TOKEN", "")
        if not self._token:
            raise RuntimeError("GARMIN_ACCESS_TOKEN is not set")
        self._http = http or httpx.Client(base_url=BASE_URL, timeout=30.0)

    def get_weight(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Return weight records uploaded between start and end (timezone-aware)."""
        start_s, end_s = int(start.timestamp()), int(end.timestamp())
        if end_s <= start_s:
            raise ValueError("end must be after start")

        records: list[dict[str, Any]] = []
        window_start = start_s
        while window_start < end_s:
            window_end = min(window_start + MAX_WINDOW_SECONDS, end_s)
            response = self._http.get(
                "/bodyComps",
                params={
                    "uploadStartTimeInSeconds": window_start,
                    "uploadEndTimeInSeconds": window_end,
                },
                headers={"Authorization": f"Bearer {self._token}"},
            )
            response.raise_for_status()
            records.extend(response.json())
            window_start = window_end

        return [_to_weight_entry(r) for r in records if r.get("weightInGrams") is not None]


def _to_weight_entry(record: dict[str, Any]) -> dict[str, Any]:
    measured = record.get("measurementTimeInSeconds")
    return {
        "date": record.get("calendarDate"),
        "measured_at": datetime.fromtimestamp(measured, tz=timezone.utc).isoformat() if measured else None,
        "weight_kg": round(record["weightInGrams"] / 1000, 2),
        "bmi": record.get("bmi"),
        "body_fat_percent": record.get("bodyFatInPercent"),
        "body_water_percent": record.get("bodyWaterInPercent"),
        "muscle_mass_kg": _grams_to_kg(record.get("muscleMassInGrams")),
        "bone_mass_kg": _grams_to_kg(record.get("boneMassInGrams")),
    }


def _grams_to_kg(value: float | None) -> float | None:
    return round(value / 1000, 2) if value is not None else None
