# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Streben** is a locally-running web application for syncing, storing, and visualizing cycling activity data. It ingests data from three sources — the Strava API, the Wahoo Cloud API, and Garmin FIT file uploads — stores everything in a local SQLite database, and presents it through a server-rendered web UI.

Stack: FastAPI + Jinja2, Bulma 1.0.2 (CDN), Plotly / ECharts / Leaflet (CDN), SQLite via `sqlite3` (no ORM), garmin-fit-sdk, uv, Python 3.11+.

**[ARCHITECTURE.md](ARCHITECTURE.md) is the single technical reference** — project tree, database schema, data flows, routes, pages, and the full CLI. Update it (not this file) when those change.

## Running & Development

```bash
uv sync                                    # install dependencies
uv run uvicorn app.main:app --port 8000    # http://localhost:8000; creates data/strava.db
uv run pytest                              # tests
```

### CLI (`strava-cli`)
```bash
uv run strava-cli backfill-streams [--limit N]                 # missing Strava streams (preferred over the web UI for large batches)
uv run strava-cli backfill-fields                              # re-extract activity columns from stored raw_data
uv run strava-cli sync-wahoo [--full] [--zones] [--max-pages N] # --full for the first backfill
uv run strava-cli import-cronometer path/to/dailysummary.csv   # re-importing a date overwrites it
uv run strava-cli import-biometrics path/to/biometrics.csv     # dated weights
uv run strava-cli backfill-nutrition-fields                    # re-promote nutrition columns from raw_data
```

## Where Things Live
- `app/routers/` — one module per area (dashboard, activities, strava, wahoo, fit_upload, nutrition, trends).
  Most delegate to services; the exception is the Strava sync/backfill loop, which still lives in `routers/strava.py`
- `app/services/` — API clients, sync loops, FIT parsing, charts, energy math; no FastAPI imports
- `app/templates/` — Jinja2; `base.html` holds the navbar and all shared inline CSS/JS
- `app/database.py` — schema + idempotent `ALTER TABLE` migrations; add new columns there
- `data/strava.db` — SQLite database (runtime, gitignored)
- `docs/index.html` — public project site (GitHub Pages from `main:/docs`); static, no build, not part of the app

## Testing & Dependencies
- `tests/` currently covers **Wahoo sync only**. There are no sample FIT files in the repo, so changes to
  FIT parsing (or a `garmin-fit-sdk` upgrade) need a manual upload check on `/upload`
- Use a current `uv`. An older uv rewrites `uv.lock` to an older lockfile format and churns unrelated
  lines — if `uv lock` produces a huge diff, check `uv --version` before committing

## Important Context

### Strava API
- Activities are fetched as summaries; detailed streams require additional API calls per activity
- Stream types: time, distance, heartrate, cadence, watts, altitude, lat/lng
- Strava API returns streams in two formats (list of `{type, data}` objects or dict keyed by type) — the app handles both
- Rate limit: 100 requests per 15 minutes — the CLI backfill command adds 1-second delays between calls
- All timestamps are UTC; the browser converts to local timezone for display

### Wahoo Cloud API
- Configured on `/settings` (client ID/secret pre-filled from `WAHOO_CLIENT_ID`/`WAHOO_SECRET`,
  plus a stored redirect URI that must exactly match the Wahoo developer portal; the default is
  `https://localhost:8000/wahoo/redirect`, which requires running uvicorn with TLS)
- Workout summaries give the activity columns; the summary's FIT file (`file.url`) is downloaded
  and parsed with `fit_parser` for streams. Decimals arrive as **strings** — always cast
- `raw_data` gets a computed `start_date_local` (from `starts` + `time_zone`) so energy balance
  buckets Wahoo rides on the local day, same as Strava
- `sport_type` is mapped to Strava's vocabulary (`Ride`, `VirtualRide`, …) so filters merge sources
- Sandbox rate limits are tiny (25 / 5 min, 250 / day); syncs stop cleanly and resume. Use
  Disconnect before reconnecting — Wahoo caps a user at 10 unrevoked tokens
- **Cross-source dedup**: Strava and Wahoo syncs skip an activity that starts within ±5 min of an
  existing one from a *different* source, otherwise ride kJ would double-count in energy balance

### FIT File Parsing
- FIT files are decoded using garmin-fit-sdk (session + record messages) in `services/fit_parser.py`;
  the same parser handles uploads and Wahoo's downloaded FIT files

### UI Conventions
- Bulma CSS via CDN with dark/light mode toggle (persisted in localStorage)
- All pages are server-rendered; minimal inline JS for interactivity
- Long-running POST forms get `data-busy="Message…"` — `base.html` adds a spinner, disables all busy
  buttons (prevents concurrent syncs), and shows elapsed time in `#busy-status` if the page has one
- Any animation must be skipped under `prefers-reduced-motion: reduce`
- Flash messages via query parameters, displayed as dismissible Bulma notifications

### Nutrition & Energy Balance
- Cronometer `dailysummary.csv` is imported per calendar day into the `nutrition` table; all 61
  export columns are kept as `raw_data` JSON, with curated macros promoted to real columns
- **Blank is not zero.** An unlogged day has every nutrient cell empty in the export. Blanks are
  stored as `NULL`; `is_logged` is `energy_kcal IS NOT NULL`. The `Completed` flag is display-only —
  it is almost never ticked and must not be used to decide whether a day has data
- Ride energy is joined on **local** date via `json_extract(raw_data, '$.start_date_local')`, not
  `start_date` — the latter is UTC and misattributes 110 of 2190 activities (evening rides)
- `ride_kj` is treated as kcal 1:1: at ~24% gross cycling efficiency, kJ / 0.24 / 4.184 ≈ kJ. This
  is physiology, not a missing unit conversion
- Food eaten *during* rides is not logged, so it is estimated as
  `ride_hours × carb_rate_g_per_hr × 4` and always rendered as visibly an estimate
- RMR uses Mifflin–St Jeor with the weight in effect on **that date** (`body_metrics` is
  date-stamped), so past balances stay correct as weight changes
- `activity_multiplier` must stay at 1.2 (sedentary) — ride energy is added separately, so a higher
  multiplier double-counts rides
- `/api/trends` is per-activity; `/api/nutrition-trends` is a dense per-calendar-day spine. They are
  deliberately separate endpoints with different grains
