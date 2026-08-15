import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "strava.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS strava_auth (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    client_id TEXT NOT NULL,
    client_secret TEXT NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    expires_at INTEGER
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strava_id INTEGER UNIQUE,
    source TEXT NOT NULL,
    name TEXT,
    sport_type TEXT,
    start_date TEXT,
    moving_time INTEGER,
    elapsed_time INTEGER,
    distance REAL,
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
    total_elevation_gain REAL,
    calories REAL,
    description TEXT,
    device_name TEXT,
    average_temp REAL,
    summary_polyline TEXT,
    fit_filename TEXT,
    raw_data TEXT
);

CREATE TABLE IF NOT EXISTS activity_streams (
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

CREATE INDEX IF NOT EXISTS idx_streams_activity ON activity_streams(activity_id);

CREATE TABLE IF NOT EXISTS zone_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    power_z1 INTEGER NOT NULL DEFAULT 0,
    power_z2 INTEGER NOT NULL DEFAULT 100,
    power_z3 INTEGER NOT NULL DEFAULT 150,
    power_z4 INTEGER NOT NULL DEFAULT 200,
    power_z5 INTEGER NOT NULL DEFAULT 250,
    hr_z1 INTEGER NOT NULL DEFAULT 0,
    hr_z2 INTEGER NOT NULL DEFAULT 115,
    hr_z3 INTEGER NOT NULL DEFAULT 140,
    hr_z4 INTEGER NOT NULL DEFAULT 160,
    hr_z5 INTEGER NOT NULL DEFAULT 175
);
"""


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


MIGRATIONS = [
    ("total_elevation_gain", "ALTER TABLE activities ADD COLUMN total_elevation_gain REAL"),
    ("calories", "ALTER TABLE activities ADD COLUMN calories REAL"),
    ("description", "ALTER TABLE activities ADD COLUMN description TEXT"),
    ("device_name", "ALTER TABLE activities ADD COLUMN device_name TEXT"),
    ("average_temp", "ALTER TABLE activities ADD COLUMN average_temp REAL"),
    ("summary_polyline", "ALTER TABLE activities ADD COLUMN summary_polyline TEXT"),
]


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    # Migrate existing databases: add columns if missing
    existing = {row[1] for row in conn.execute("PRAGMA table_info(activities)").fetchall()}
    for col_name, sql in MIGRATIONS:
        if col_name not in existing:
            conn.execute(sql)
    conn.execute("INSERT OR IGNORE INTO zone_settings (id) VALUES (1)")
    conn.commit()
    conn.close()
