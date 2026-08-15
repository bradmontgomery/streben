# Architecture

## Overview

Streber is a locally-running web application for syncing, storing, and visualizing cycling activity data. It ingests data from two sources — the Strava API and Garmin FIT files — stores everything in a local SQLite database, and presents it through a server-rendered web UI.

The application is built with **FastAPI** and **Jinja2** templates, styled with **Bulma CSS** (via CDN), and uses **Plotly** and **Apache ECharts** for data visualization. There is no JavaScript frontend framework; all pages are server-rendered with minimal inline JS for interactivity.

## Tech Stack

| Layer         | Technology                     |
|---------------|--------------------------------|
| Web framework | FastAPI                        |
| Templating    | Jinja2                         |
| CSS           | Bulma 1.0.2 (CDN)             |
| Charts        | Plotly (activity detail), Apache ECharts (trends) |
| Database      | SQLite (via `sqlite3`, no ORM) |
| FIT parsing   | garmin-fit-sdk                 |
| HTTP client   | requests                       |
| Package mgr   | uv                             |
| Build backend | hatchling                      |
| Python        | 3.11+                          |

## Project Structure

```
streber/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app setup, router registration, startup
│   ├── database.py          # SQLite connection, schema, init_db()
│   ├── models.py            # Dataclasses: Activity, StreamRecord, StravaAuth
│   ├── cli.py               # CLI commands (backfill-streams)
│   ├── routers/
│   │   ├── dashboard.py     # GET /              — paginated activity list
│   │   ├── activities.py    # GET /activities/:id — activity detail + chart
│   │   ├── strava.py        # Strava OAuth, sync, stream fetch/backfill
│   │   ├── fit_upload.py    # GET/POST /upload   — FIT file upload
│   │   └── trends.py        # GET /trends, GET /api/trends — trends page + JSON API
│   ├── services/
│   │   ├── strava_client.py # Strava API client (auth, tokens, activities, streams)
│   │   ├── fit_parser.py    # FIT file decoding via garmin-fit-sdk
│   │   └── charts.py        # Plotly chart generation for activity streams
│   └── templates/
│       ├── base.html         # Layout: navbar, flash messages, dark/light toggle
│       ├── dashboard.html    # Activity table with pagination
│       ├── activity_detail.html # Stats summary + Plotly stream chart
│       ├── fit_upload.html   # FIT file upload form
│       ├── settings.html     # Strava API credentials + connection status
│       └── trends.html       # ECharts time-series with metric/range toggles
├── data/
│   └── strava.db            # SQLite database (created at runtime)
├── pyproject.toml
└── uv.lock
```

## Database Schema

SQLite with WAL mode and foreign keys enabled. Three tables:

### `strava_auth`
Single-row table (`CHECK id = 1`) storing Strava OAuth credentials and tokens.

| Column        | Type    | Notes                     |
|---------------|---------|---------------------------|
| id            | INTEGER | PK, always 1              |
| client_id     | TEXT    | Strava app client ID      |
| client_secret | TEXT    | Strava app client secret  |
| access_token  | TEXT    | OAuth access token        |
| refresh_token | TEXT    | OAuth refresh token       |
| expires_at    | INTEGER | Token expiry (Unix epoch) |

### `activities`
Unified table for both Strava-synced and FIT-uploaded activities.

| Column                  | Type    | Notes                              |
|-------------------------|---------|------------------------------------|
| id                      | INTEGER | PK autoincrement                   |
| strava_id               | INTEGER | UNIQUE, nullable (null for FIT)    |
| source                  | TEXT    | `"strava"` or `"fit_upload"`       |
| name                    | TEXT    | Activity name or filename          |
| sport_type              | TEXT    | e.g. "Ride", "VirtualRide"        |
| start_date              | TEXT    | ISO 8601 datetime                  |
| moving_time             | INTEGER | Seconds                            |
| elapsed_time            | INTEGER | Seconds                            |
| distance                | REAL    | Meters                             |
| average_watts           | REAL    |                                    |
| max_watts               | REAL    |                                    |
| weighted_average_watts  | REAL    | Normalized power                   |
| average_heartrate       | REAL    | BPM                                |
| max_heartrate           | REAL    | BPM                                |
| average_cadence         | REAL    | RPM                                |
| average_speed           | REAL    | m/s                                |
| max_speed               | REAL    | m/s                                |
| elev_high               | REAL    | Meters                             |
| elev_low                | REAL    | Meters                             |
| kilojoules              | REAL    |                                    |
| suffer_score            | REAL    | Strava-only                        |
| fit_filename            | TEXT    | FIT upload only                    |
| raw_data                | TEXT    | Full Strava JSON (Strava only)     |

### `activity_streams`
Per-second time-series data for activities. Indexed on `activity_id`.

| Column           | Type    | Notes                    |
|------------------|---------|--------------------------|
| id               | INTEGER | PK autoincrement         |
| activity_id      | INTEGER | FK to activities         |
| timestamp_offset | INTEGER | Seconds from start       |
| watts            | REAL    | Power                    |
| heartrate        | REAL    | BPM                      |
| cadence          | REAL    | RPM                      |
| distance         | REAL    | Meters                   |
| speed            | REAL    |                          |
| altitude         | REAL    | Meters                   |
| lat              | REAL    | Degrees                  |
| lng              | REAL    | Degrees                  |

## Data Flow

### Strava Sync

```
Browser POST /strava/sync
  → strava_client.get_all_activities()  (paginated, 100/page)
  → For each new activity (by strava_id):
      INSERT into activities
      → strava_client.get_activity_streams(strava_id)
      → INSERT rows into activity_streams
  → Redirect to dashboard with count
```

### Strava OAuth

```
Browser → GET /strava/connect
  → Redirect to Strava authorize URL
  → Strava redirects to GET /strava/callback?code=...
  → strava_client.exchange_code() → saves tokens to strava_auth
  → Redirect to /settings with flash
```

Token refresh happens automatically in `_ensure_valid_token()` when the access token is expired.

### FIT Upload

```
Browser POST /upload (multipart file)
  → Save to temp file
  → fit_parser.parse_fit_file()
      → garmin_fit_sdk Decoder reads session + record messages
      → Returns {activity: dict, streams: list[StreamRecord]}
  → INSERT activity + stream rows
  → Redirect to /activities/:id
```

### Stream Backfill

For activities synced before stream fetching was implemented:

- **Web UI**: "Backfill Streams" button on dashboard, or per-activity "Fetch Streams" button on detail page
- **CLI**: `uv run strava-cli backfill-streams [--limit N]` — preferred for large backfills, shows progress and respects rate limits

## Routes

| Method | Path                              | Description                        |
|--------|-----------------------------------|------------------------------------|
| GET    | `/`                               | Dashboard — paginated activity list |
| GET    | `/activities/{id}`                | Activity detail with charts        |
| GET    | `/upload`                         | FIT upload form                    |
| POST   | `/upload`                         | Handle FIT file upload             |
| GET    | `/settings`                       | Strava credentials & status        |
| POST   | `/settings`                       | Save Strava credentials            |
| GET    | `/strava/connect`                 | Start Strava OAuth flow            |
| GET    | `/strava/callback`                | OAuth callback                     |
| POST   | `/strava/sync`                    | Sync all activities from Strava    |
| POST   | `/strava/backfill-streams`        | Backfill streams for all activities |
| POST   | `/strava/fetch-streams/{id}`      | Fetch streams for one activity     |
| GET    | `/trends`                         | Trends page                        |
| GET    | `/api/trends?range=6m`            | Trends JSON data                   |

## Pages

### Dashboard (`/`)
Paginated table of all activities (default 100/page). Shows date, name, source tag, sport type, duration, distance, avg watts, avg HR. Warning icon on activities missing stream data. Buttons for Strava sync and stream backfill.

### Activity Detail (`/activities/:id`)
Summary stats bar (duration, distance, power, HR, energy), interactive Plotly chart of stream data (watts, HR, cadence), additional stats section. "View on Strava" badge links to the original activity for Strava-sourced data. "Fetch Streams from Strava" button when stream data is missing.

### Trends (`/trends`)
Time-series chart using Apache ECharts. Toggle between metrics (duration, distance, avg/max power, avg/max HR, energy, suffer score) and time ranges (1W, 1M, 3M, 6M, 1Y, All). Optional linear regression trend line overlay. Data fetched via `/api/trends` JSON endpoint.

### Upload (`/upload`)
File input for .fit files. Parses and stores the activity + streams on upload, then redirects to the activity detail page.

### Settings (`/settings`)
Strava API credential management (client ID/secret), connection status with human-readable token expiry, and OAuth connect/reconnect button.

## UI

- **Bulma CSS 1.0.2** via CDN — default theme, no custom CSS
- **Dark/light mode** toggle in navbar, persisted in localStorage, uses Bulma's `data-theme` attribute
- **Flash messages** via query parameter, displayed as dismissible Bulma notifications
- **Responsive** navbar with burger menu for mobile

## CLI

Registered as `strava-cli` via `[project.scripts]` in pyproject.toml.

```
uv run strava-cli backfill-streams [--limit N]
```

Fetches missing stream data from Strava with per-activity progress output, 1-second delay between API calls to respect rate limits (100 requests / 15 minutes).

## Running

```bash
# Install dependencies
uv sync

# Start the web server
uv run uvicorn app.main:app --port 8000

# Backfill stream data (CLI)
uv run strava-cli backfill-streams --limit 50
```

The database is auto-created at `data/strava.db` on first startup.
