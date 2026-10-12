"""Daily energy balance: calories in (Cronometer) vs. calories out (RMR + rides)."""
from dataclasses import dataclass, asdict
from datetime import date as date_cls, datetime, timedelta
from typing import Optional

from app.database import get_db

LB_TO_KG = 0.45359237
IN_TO_CM = 2.54
KCAL_PER_G_CARB = 4.0

# Ride kilojoules are treated as kilocalories 1:1. This is not a missing unit
# conversion -- at ~24% gross cycling efficiency the metabolic cost is
# kJ_work / 0.24 / 4.184 = kJ_work * 0.996. The two constants cancel. Do not
# "fix" this by dividing by 4.184.
KJ_TO_KCAL = 1.0


@dataclass
class DaySummary:
    date: str
    intake_logged: Optional[float]
    intake_onbike_est: Optional[float]
    intake_total: Optional[float]
    ride_kj: Optional[float]
    ride_seconds: int
    rmr: Optional[float]
    baseline_tdee: Optional[float]
    need: Optional[float]
    balance: Optional[float]
    cumulative_balance: Optional[float]
    is_logged: bool
    completed: bool
    weight_lb: Optional[float]
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    protein_g: Optional[float] = None

    def as_dict(self) -> dict:
        return asdict(self)


def mifflin_st_jeor(weight_lb: float, height_in: float, age_years: int, sex: str) -> float:
    kg = weight_lb * LB_TO_KG
    cm = height_in * IN_TO_CM
    base = 10 * kg + 6.25 * cm - 5 * age_years
    return base + (5 if (sex or "male").lower() == "male" else -161)


def _age_on(birth_date: str, on: date_cls) -> int:
    b = datetime.strptime(birth_date, "%Y-%m-%d").date()
    return on.year - b.year - ((on.month, on.day) < (b.month, b.day))


def get_nutrition_settings() -> dict:
    db = get_db()
    row = db.execute("SELECT * FROM nutrition_settings WHERE id = 1").fetchone()
    db.close()
    return dict(row) if row else {}


def save_nutrition_settings(height_in, birth_date, sex, activity_multiplier, carb_rate_g_per_hr):
    db = get_db()
    db.execute(
        """INSERT INTO nutrition_settings
             (id, height_in, birth_date, sex, activity_multiplier, carb_rate_g_per_hr)
           VALUES (1, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             height_in=excluded.height_in, birth_date=excluded.birth_date,
             sex=excluded.sex, activity_multiplier=excluded.activity_multiplier,
             carb_rate_g_per_hr=excluded.carb_rate_g_per_hr""",
        (height_in, birth_date, sex, activity_multiplier, carb_rate_g_per_hr),
    )
    db.commit()
    db.close()


def preview_rmr() -> tuple[Optional[float], Optional[float]]:
    """RMR and baseline TDEE using today's settings and latest weight, for the settings page."""
    s = get_nutrition_settings()
    db = get_db()
    row = db.execute("SELECT weight_lb FROM body_metrics ORDER BY date DESC LIMIT 1").fetchone()
    db.close()
    if not row or not s.get("height_in") or not s.get("birth_date"):
        return None, None
    age = _age_on(s["birth_date"], date_cls.today())
    rmr = mifflin_st_jeor(row["weight_lb"], s["height_in"], age, s["sex"])
    return rmr, rmr * s["activity_multiplier"]


def _spine(start: str, end: str) -> list[str]:
    d0 = datetime.strptime(start, "%Y-%m-%d").date()
    d1 = datetime.strptime(end, "%Y-%m-%d").date()
    out, d = [], d0
    while d <= d1:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def energy_balance(start: str, end: str) -> list[DaySummary]:
    db = get_db()
    settings = dict(db.execute("SELECT * FROM nutrition_settings WHERE id = 1").fetchone() or {})
    nut = {
        r["date"]: r
        for r in db.execute(
            "SELECT * FROM nutrition WHERE date BETWEEN ? AND ?", (start, end)
        ).fetchall()
    }
    weights = db.execute(
        "SELECT date, weight_lb FROM body_metrics ORDER BY date"
    ).fetchall()
    # Group rides by LOCAL calendar day. Cronometer logs food by local day while
    # activities.start_date is UTC -- 110 of 2190 rows disagree between the two.
    # The WHERE filters on the indexed UTC column and is padded by two days so no
    # boundary day is lost to the local/UTC offset. FIT-uploaded activities have
    # no raw_data and fall back to start_date (none exist today).
    rides = {
        r["d"]: r
        for r in db.execute(
            """SELECT substr(COALESCE(json_extract(raw_data,'$.start_date_local'),
                                      start_date), 1, 10) AS d,
                      SUM(kilojoules) AS kj,
                      SUM(COALESCE(moving_time, elapsed_time, 0)) AS secs
                 FROM activities
                WHERE start_date >= date(?, '-2 days')
                  AND start_date <= date(?, '+2 days')
                GROUP BY d""",
            (start, end),
        ).fetchall()
    }
    db.close()

    configured = bool(settings.get("height_in") and settings.get("birth_date") and weights)
    multiplier = settings.get("activity_multiplier") or 1.2
    carb_rate = settings.get("carb_rate_g_per_hr") or 0.0

    # Forward-walk the sorted weights alongside the spine: O(n+m), no per-day query.
    # Seed with the earliest entry so a spine starting before the first weigh-in
    # still produces a continuous cumulative line.
    wi = 0
    current_weight = weights[0]["weight_lb"] if weights else None

    out: list[DaySummary] = []
    running = 0.0
    for d in _spine(start, end):
        while wi < len(weights) and weights[wi]["date"] <= d:
            current_weight = weights[wi]["weight_lb"]
            wi += 1

        ride = rides.get(d)
        ride_kj = ride["kj"] if ride else None
        ride_secs = int(ride["secs"] or 0) if ride else 0

        n = nut.get(d)
        intake_logged = n["energy_kcal"] if n else None
        is_logged = intake_logged is not None

        rmr = baseline = need = None
        if configured and current_weight is not None:
            age = _age_on(settings["birth_date"], datetime.strptime(d, "%Y-%m-%d").date())
            rmr = mifflin_st_jeor(current_weight, settings["height_in"], age, settings["sex"])
            baseline = rmr * multiplier
            need = baseline + (ride_kj or 0.0) * KJ_TO_KCAL

        # On-bike fuel is an estimate layered on top of a logged day. With no
        # logged base there is nothing to add it to, so it stays None.
        onbike = (ride_secs / 3600.0) * carb_rate * KCAL_PER_G_CARB if is_logged else None
        intake_total = intake_logged + onbike if is_logged else None
        balance = intake_total - need if (intake_total is not None and need is not None) else None

        if balance is not None:
            running += balance
        # Carry the cumulative forward across unlogged days so the line stays
        # flat and continuous rather than interpolating over a gap.
        out.append(DaySummary(
            date=d,
            intake_logged=intake_logged,
            intake_onbike_est=onbike,
            intake_total=intake_total,
            ride_kj=ride_kj,
            ride_seconds=ride_secs,
            rmr=rmr,
            baseline_tdee=baseline,
            need=need,
            balance=balance,
            cumulative_balance=running if configured else None,
            is_logged=is_logged,
            completed=bool(n["completed"]) if n else False,
            weight_lb=current_weight,
            carbs_g=n["carbs_g"] if n else None,
            fat_g=n["fat_g"] if n else None,
            protein_g=n["protein_g"] if n else None,
        ))
    return out
