# Strava Activity Tracker — Web App Design

## Overview

Rethink the existing Jupyter notebook project into a locally-running web application for syncing Strava data, uploading FIT files, and visualizing cycling activity data. All data stored in SQLite.

## Stack

- **Backend:** FastAPI + Jinja2 templates (no JS/TS frontend)
- **Styling:** Bulma CSS via CDN (default theme, no custom CSS)
- **Database:** SQLite via `sqlite3` (no ORM)
- **Charts:** Plotly (server-side HTML generation, embedded in templates)
- **FIT parsing:** garmin_fit_sdk (Decoder/Stream)
- **Strava API:** requests library, OAuth2 flow built into the app

## Project Structure

```
app/
  main.py              # FastAPI app, startup, routes mount
  database.py          # SQLite connection, schema init
  models.py            # Dataclasses for type safety (not ORM)
  routers/
    dashboard.py       # Home page with activity overview
    strava.py          # OAuth flow + sync trigger
    fit_upload.py      # FIT file upload + parsing
    activities.py      # Activity detail + visualizations
  services/
    strava_client.py   # Strava API client (extracted from notebook)
    fit_parser.py      # FIT file parsing logic
    charts.py          # Plotly chart generators
  templates/
    base.html          # Bulma layout, navbar
    dashboard.html
    activity_detail.html
    fit_upload.html
    settings.html
  static/
    (bulma via CDN, no local static CSS)
```

## Database Schema

```sql
CREATE TABLE strava_auth (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    client_id TEXT NOT NULL,
    client_secret TEXT NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    expires_at INTEGER
);

CREATE TABLE activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strava_id INTEGER UNIQUE,
    source TEXT NOT NULL,              -- 'strava' or 'fit_upload'
    name TEXT,
    sport_type TEXT,
    start_date TEXT,                   -- ISO 8601 UTC
    moving_time INTEGER,              -- seconds
    elapsed_time INTEGER,             -- seconds
    distance REAL,                    -- meters
    average_watts REAL,
    max_watts REAL,
    weighted_average_watts REAL,
    average_heartrate REAL,
    max_heartrate REAL,
    average_cadence REAL,
    average_speed REAL,
    max_speed REAL,
    elev_high REAL,
    elev_low REAL,
    kilojoules REAL,
    suffer_score REAL,
    fit_filename TEXT,
    raw_data TEXT                     -- JSON blob for extras
);

CREATE TABLE activity_streams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL REFERENCES activities(id),
    timestamp_offset INTEGER NOT NULL,
    watts REAL,
    heartrate REAL,
    cadence REAL,
    distance REAL,
    speed REAL,
    altitude REAL,
    lat REAL,
    lng REAL
);

CREATE INDEX idx_streams_activity ON activity_streams(activity_id);
```

## Pages & Routes

### Navbar
Dashboard | Upload FIT | Settings

### 1. Dashboard (`GET /`)
- Bulma table of all activities sorted by date descending
- Columns: date, name, source, duration, distance, avg watts, avg HR
- Each row links to `/activities/{id}`
- "Sync from Strava" button in header

### 2. Activity Detail (`GET /activities/{id}`)
- Bulma level/hero with summary stats (duration, distance, avg/max watts, avg/max HR, kJ)
- Plotly time-series chart with watts, heartrate, cadence (toggle-able series)
- Chart section only shown if stream data exists

### 3. Upload FIT (`GET /upload`, `POST /upload`)
- Bulma file input for `.fit` files
- On POST: parse FIT file, insert activity + streams, redirect to activity detail

### 4. Settings (`GET /settings`, `POST /settings`)
- Form for Strava Client ID + Client Secret
- "Connect to Strava" button (initiates OAuth)
- Connection status display

### 5. Strava OAuth (`GET /strava/callback`)
- Handles OAuth redirect from Strava
- Exchanges code for tokens, stores in strava_auth
- Redirects to settings with success flash

### 6. Strava Sync (`POST /strava/sync`)
- Fetches all activities from Strava API
- Upserts into activities table (skip existing by strava_id)
- For each new activity, fetches streams and inserts into activity_streams
- Redirects to dashboard with count of new activities

## OAuth Flow

1. User enters Client ID + Secret in Settings, saves
2. User clicks "Connect to Strava"
3. App redirects to `https://www.strava.com/oauth/authorize` with `redirect_uri=http://localhost:8000/strava/callback`
4. User authorizes in browser
5. Strava redirects to callback with code
6. App exchanges code for access_token + refresh_token, stores in DB
7. Redirect to Settings with success message

## Strava Sync Flow

1. User clicks "Sync from Strava" on dashboard
2. App checks token validity, refreshes if expired
3. Fetches all activities via pagination
4. For each activity not already in DB (by strava_id): insert activity, fetch streams, insert stream records
5. Redirect to dashboard with flash showing count of new activities

## FIT Upload Flow

1. User selects .fit file on upload page
2. App parses using garmin_fit_sdk Decoder
3. Extracts activity summary (from session messages) and per-second records
4. Inserts activity + stream records
5. Redirects to new activity detail page

## Visualization

- All charts generated server-side with Plotly
- `charts.py` produces HTML strings via `plotly.io.to_html(full_html=False)`
- Embedded in templates via `{{ chart_html | safe }}`
- Primary chart: time-series with watts, heartrate, cadence as separate traces
- Interactive zoom/pan/hover provided by Plotly's built-in JS

## Key Decisions

- **No ORM**: Raw SQL with sqlite3 keeps it simple for a personal tool
- **Single activities table**: Both sources share the same schema, distinguished by `source` column
- **Bulma via CDN**: No build step, no local CSS files
- **No background tasks**: Strava sync is synchronous (acceptable for personal use with ~hundreds of activities)
- **Token refresh**: Automatic before API calls if expires_at is past
