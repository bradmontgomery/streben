# Strava API Thing

A Jupyter notebook-based project for exploring the Strava cycling activity API and analyzing fitness data from FIT files (Garmin/cycling device format).

## Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)

### Setup

```bash
# Install dependencies
uv sync --with notebook

# Activate the virtual environment (optional, uv can run directly)
source .venv/bin/activate
```

### Run Jupyter

```bash
# With activation
jupyter notebook

# Or directly with uv (no activation needed)
uv run jupyter notebook
```

The notebooks will be accessible at `http://localhost:8888`

## Project Structure

- **Strava API.ipynb** — Authenticate to Strava API, fetch athlete/activity data, and analyze with Pandas
- **FIT Files.ipynb** — Decode and explore Garmin FIT files (workouts and activity recordings)
- **data/** — Sample FIT files for testing

## Environment Variables

Both notebooks require these for Strava API authentication:
- `CLIENT_ID` — Strava app client ID
- `CLIENT_SECRET` — Strava app client secret
- `ACCESS_TOKEN` — OAuth bearer token (generated via authorization flow)

See [CLAUDE.md](CLAUDE.md) for architecture details and Strava API setup instructions.

## Future Ideas

Explore .fit file decoders and signal matching:
* Dynamic Time Warping for workout matching
* Machine learning models with Pycaret (time, heartrate, cadence, power)

## Resources

* [Strava Developer Docs](https://developers.strava.com/docs/getting-started/) — API reference and setup
* [FIT File Documentation](https://developer.garmin.com/fit/file-types/) — Garmin format specs
* [fitdecode](https://pypi.org/project/fitdecode/) — FIT file decoder library
