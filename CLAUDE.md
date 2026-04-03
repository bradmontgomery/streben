# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Strava API Thing** is a Jupyter notebook-based project for exploring the Strava cycling activity API and analyzing fitness data from FIT files (Garmin/cycling device format). The project focuses on data extraction, processing, and visualization of cycling workouts.

## Architecture & Data Flow

The project is organized around two independent Jupyter notebooks:

### 1. **Strava API.ipynb** - Strava API Exploration
- **Purpose**: Authenticates to Strava API and fetches athlete/activity data
- **Key Flow**:
  - OAuth authentication using `CLIENT_ID`, `CLIENT_SECRET`, and `ACCESS_TOKEN` (loaded from environment variables)
  - Fetch athlete profile from `/api/v3/athlete`
  - Fetch activities list from `/api/v3/athlete/activities` (paginated, 100 per page)
  - Fetch activity streams (time, distance, heartrate, cadence, watts) from `/api/v3/activities/{id}/streams`
- **Outputs**: Pandas DataFrames with aggregated activity metrics and time-series stream data
- **Sections**: Authentication → Basic API Requests → Pandas Data Frames → Data Streams

### 2. **FIT Files.ipynb** - FIT File Decoding
- **Purpose**: Decodes Garmin FIT files (both workout templates and activity recordings)
- **Key Components**:
  - **Workout Files**: Parse structured workout steps (duration, intensity, power targets) using Garmin FIT SDK
  - **Activity Files**: Parse recorded activity records (GPS, power, heart rate, cadence per second)
- **Data Structure**: Messages organized by type (file_id, device_info, event, record, lap, session, activity)
- **Power Values**: Note encoding - values 0-1000 are relative (% FTP), absolute power offset by 1000W

## Setup & Dependencies

### Requirements
- Python 3.11+ (see `env/pyvenv.cfg`)
- Virtual environment: `env/`
- Dependencies in `requirements.txt`:
  - **Jupyter**: jupyter, notebook, ipython, ipykernel
  - **Data**: pandas, arrow (datetime), Pillow (images)
  - **Visualization**: matplotlib, seaborn, plotly
  - **FIT Files**: fitdecode (0.10.0), garmin-fit-sdk (21.133.0)
  - **API**: requests, certifi

### Environment Variables
Both notebooks require these for Strava API authentication (set in your shell before running):
- `CLIENT_ID` - Strava app client ID
- `CLIENT_SECRET` - Strava app client secret
- `ACCESS_TOKEN` - OAuth bearer token (generated via authorization flow)

See Strava Developer Docs: https://developers.strava.com/docs/getting-started/

## Running & Development

### Start Jupyter
```bash
source env/bin/activate
jupyter notebook
```
The notebooks will be accessible at `http://localhost:8888`

### Key Resources
- **Strava API Reference**: https://developers.strava.com/docs/reference/
- **FIT File Documentation**: https://developer.garmin.com/fit/file-types/
- **FIT Workout Format**: https://developer.garmin.com/fit/file-types/workout/
- **FIT Activity Format**: https://developer.garmin.com/fit/file-types/activity/

## Data Locations
- **FIT Files**: `data/HOP21/` - Contains workout and activity FIT files for testing
- **Static Assets**: `static/` - Icon and other assets

## Important Context

### Strava API Key Concepts
- Activities are fetched as summaries; detailed streams require additional API calls per activity
- Stream types available: time, distance, heartrate, cadence, watts, altitude, lat/lng, etc.
- All timestamps are UTC; activities include local timezone info for display

### FIT File Structure
- **Workout Files**: Define structured training plans with steps, durations, power zones, and repetition logic
  - Power values encoded as custom ranges (e.g., 1240-1263 watts = 240-263 offset from 1000)
  - Repeat logic uses `duration_step` to reference which step to repeat
- **Activity Files**: Contain second-by-second recorded data (records) plus aggregated lap/session summaries
  - GPS coordinates use signed integer encoding (not standard lat/lng)
  - Each record represents one second of data

### Known Patterns
- Power data in Zwift activities shows extreme values (e.g., 1001W spikes) due to trainer inconsistencies
- Strava and FIT data for the same workout show near-identical metrics (validation data)
- Repeat logic in workout files uses message indices, not named references
