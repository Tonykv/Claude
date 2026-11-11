# garmin-mcp

An MCP server that exposes weight data from the [Garmin Health API](https://developer.garmin.com/gc-developer-program/health-api/) to MCP clients.

## Tools

- `get_weight(start_date?, end_date?)`: weight measurements between two ISO dates (UTC, inclusive). Defaults to the last 30 days. Returns weight in kg plus BMI, body fat, body water, muscle mass, and bone mass when Garmin provides them.

## Setup

Garmin Health API access requires an approved developer program account and a user OAuth 2.0 access token. This server does not perform the OAuth flow; supply a token through the environment.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:GARMIN_ACCESS_TOKEN = "<user access token>"
.\.venv\Scripts\python.exe -m pytest
```

## Client configuration

Example MCP client entry (stdio transport):

```json
{
  "mcpServers": {
    "garmin": {
      "command": "C:\\claude\\garmin-mcp\\.venv\\Scripts\\garmin-mcp.exe",
      "env": { "GARMIN_ACCESS_TOKEN": "<user access token>" }
    }
  }
}
```
