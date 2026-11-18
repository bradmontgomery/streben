# Streben

A local app for your Strava, Wahoo, and Garmin FIT cycling data. No socials. No signups.
Everything stays on your computer.

Project site: <https://bradmontgomery.net/streben/>

## Features

- **Strava Sync** — OAuth integration to pull all activities and per-second stream data
- **Wahoo Sync** — Pull workouts (and their FIT files) from the Wahoo Cloud API, plus power zones
- **FIT File Upload** — Import activities directly from Garmin .fit files
- **No double-counted rides** — A ride that arrives from both Strava and Wahoo is stored once
- **Activity Dashboard** — Paginated, filterable list of all activities with stream data indicators
- **Activity Detail** — Summary stats, interactive Plotly charts of power, HR and cadence, a route
  map, and time in power/heart-rate zones; rename or delete any activity
- **Trends** — Time-series charts (Apache ECharts) with metric toggles, time range selection, and trend lines
- **Nutrition & Energy Balance** — Import Cronometer CSV exports and see daily calories in vs.
  kJ burned, with a cumulative surplus/deficit line and weight over time
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

### Connect to Wahoo

1. Create an app in the [Wahoo developer portal](https://developers.wahooligan.com/) and register a
   redirect URI
2. Optionally export `WAHOO_CLIENT_ID` and `WAHOO_SECRET` — they pre-fill the form on `/settings`
3. On Settings, enter the client ID/secret and a redirect URI that **exactly** matches the portal.
   The default, `https://localhost:8000/wahoo/redirect`, needs uvicorn running with TLS
   (`--ssl-keyfile` / `--ssl-certfile`)
4. Click "Connect to Wahoo", then "Sync from Wahoo" on the dashboard

Wahoo caps each user at 10 active tokens, so use **Disconnect** before reconnecting. Sandbox rate
limits are small; a large first sync may take several runs, and each resumes where the last stopped.

### CLI

```bash
# Backfill missing stream data (preferred for large batches)
uv run strava-cli backfill-streams [--limit N]

# Sync from Wahoo (--full for the first backfill; --zones also imports power zones)
uv run strava-cli sync-wahoo [--full] [--zones]

# Import a Cronometer daily nutrition summary (re-importing a date overwrites it)
uv run strava-cli import-cronometer ~/Downloads/dailysummary.csv

# Import dated weights from a Cronometer biometrics export
uv run strava-cli import-biometrics ~/Downloads/biometrics.csv
```

See [ARCHITECTURE.md](ARCHITECTURE.md#cli) for every command.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full technical details including database schema, data flows, routes, and UI documentation.

## Resources

- [Strava Developer Docs](https://developers.strava.com/docs/getting-started/) — API reference and setup
- [Wahoo Cloud API](https://cloud-api.wahooligan.com/) — API reference
- [FIT File Documentation](https://developer.garmin.com/fit/file-types/) — Garmin format specs

## License

MIT — see [LICENSE.txt](LICENSE.txt).
