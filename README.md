# Streber

A locally-running web application for syncing, storing, and visualizing cycling activity data from Strava and Garmin FIT files.

## Features

- **Strava Sync** — OAuth integration to pull all activities and per-second stream data
- **FIT File Upload** — Import activities directly from Garmin .fit files
- **Activity Dashboard** — Paginated list of all activities with stream data indicators
- **Activity Detail** — Summary stats and interactive Plotly charts of power, HR, cadence
- **Trends** — Time-series charts (Apache ECharts) with metric toggles, time range selection, and trend lines
- **Dark/Light Mode** — Theme toggle persisted in browser

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)

### Setup

```bash
# Install dependencies
uv sync

# Start the web server
uv run uvicorn app.main:app --port 8000
```

The app will be accessible at `http://localhost:8000`. The SQLite database is auto-created on first startup.

### Connect to Strava

1. [Create a Strava API application](https://developers.strava.com/docs/getting-started/)
2. Go to Settings (`/settings`) and enter your Client ID and Client Secret
3. Click "Connect to Strava" to complete the OAuth flow
4. Use "Sync from Strava" on the dashboard to pull your activities

### CLI

```bash
# Backfill missing stream data (preferred for large batches)
uv run strava-cli backfill-streams [--limit N]
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full technical details including database schema, data flows, routes, and UI documentation.

## Resources

- [Strava Developer Docs](https://developers.strava.com/docs/getting-started/) — API reference and setup
- [FIT File Documentation](https://developer.garmin.com/fit/file-types/) — Garmin format specs
