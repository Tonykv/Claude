from datetime import datetime, timedelta, timezone

import httpx
import pytest

from garmin_mcp.garmin_client import MAX_WINDOW_SECONDS, GarminClient


def _client(handler) -> GarminClient:
    http = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))
    return GarminClient(access_token="token", http=http)


def test_get_weight_splits_range_into_24h_windows_and_converts_units():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=[{"calendarDate": "2026-01-01", "measurementTimeInSeconds": 1767225600,
                   "weightInGrams": 81250, "bodyFatInPercent": 18.5}],
        )

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=2)
    result = _client(handler).get_weight(start, end)

    assert len(calls) == 2
    assert int(calls[0].url.params["uploadEndTimeInSeconds"]) - int(calls[0].url.params["uploadStartTimeInSeconds"]) == MAX_WINDOW_SECONDS
    assert calls[0].headers["Authorization"] == "Bearer token"
    assert result[0]["weight_kg"] == 81.25
    assert result[0]["body_fat_percent"] == 18.5


def test_get_weight_rejects_empty_range():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        _client(lambda r: httpx.Response(200, json=[])).get_weight(start, start)
