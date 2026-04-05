from dataclasses import dataclass
from typing import Optional


@dataclass
class Activity:
    id: int
    strava_id: Optional[int]
    source: str
    name: Optional[str]
    sport_type: Optional[str]
    start_date: Optional[str]
    moving_time: Optional[int]
    elapsed_time: Optional[int]
    distance: Optional[float]
    average_watts: Optional[float]
    max_watts: Optional[float]
    weighted_average_watts: Optional[float]
    average_heartrate: Optional[float]
    max_heartrate: Optional[float]
    average_cadence: Optional[float]
    average_speed: Optional[float]
    max_speed: Optional[float]
    elev_high: Optional[float]
    elev_low: Optional[float]
    kilojoules: Optional[float]
    suffer_score: Optional[float]
    total_elevation_gain: Optional[float]
    calories: Optional[float]
    description: Optional[str]
    device_name: Optional[str]
    average_temp: Optional[float]
    summary_polyline: Optional[str]
    fit_filename: Optional[str]
    raw_data: Optional[str]

    @classmethod
    def from_row(cls, row) -> "Activity":
        return cls(**dict(row))

    @property
    def duration_display(self) -> str:
        seconds = self.moving_time or self.elapsed_time or 0
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        if h:
            return f"{h}h {m:02d}m"
        return f"{m}m {s:02d}s"

    @property
    def elapsed_display(self) -> str:
        seconds = self.elapsed_time or 0
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        if h:
            return f"{h}h {m:02d}m"
        return f"{m}m {s:02d}s"

    @property
    def stopped_time(self) -> Optional[int]:
        if self.elapsed_time and self.moving_time:
            diff = self.elapsed_time - self.moving_time
            return diff if diff > 0 else None
        return None

    @property
    def stopped_display(self) -> Optional[str]:
        diff = self.stopped_time
        if diff is None:
            return None
        h, remainder = divmod(diff, 3600)
        m, s = divmod(remainder, 60)
        if h:
            return f"{h}h {m:02d}m"
        return f"{m}m {s:02d}s"

    @property
    def distance_km(self) -> Optional[float]:
        if self.distance is not None:
            return round(self.distance / 1000, 2)
        return None

    @property
    def distance_mi(self) -> Optional[float]:
        if self.distance is not None:
            return round(self.distance / 1609.344, 2)
        return None


@dataclass
class StreamRecord:
    timestamp_offset: int
    watts: Optional[float] = None
    heartrate: Optional[float] = None
    cadence: Optional[float] = None
    distance: Optional[float] = None
    speed: Optional[float] = None
    altitude: Optional[float] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


@dataclass
class StravaAuth:
    client_id: str
    client_secret: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[int] = None
