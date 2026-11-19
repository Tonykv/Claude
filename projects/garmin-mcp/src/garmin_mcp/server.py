"""MCP server exposing Garmin weight data."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from mcp.server.fastmcp import FastMCP

from garmin_mcp.garmin_client import GarminClient

mcp = FastMCP("garmin")

_client: GarminClient | None = None


def _get_client() -> GarminClient:
    global _client
    if _client is None:
        _client = GarminClient()
    return _client


@mcp.tool()
def get_weight(start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    """Get weight measurements from Garmin between start_date and end_date (inclusive).

    Dates are ISO format (YYYY-MM-DD) in UTC. Defaults to the last 30 days.
    """
    end_day = date.fromisoformat(end_date) if end_date else date.today()
    start_day = date.fromisoformat(start_date) if start_date else end_day - timedelta(days=30)
    start_dt = datetime.combine(start_day, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return _get_client().get_weight(start_dt, end_dt)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
