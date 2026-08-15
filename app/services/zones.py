from app.database import get_db

POWER_ZONE_KEYS = ["power_z1", "power_z2", "power_z3", "power_z4", "power_z5"]
HR_ZONE_KEYS = ["hr_z1", "hr_z2", "hr_z3", "hr_z4", "hr_z5"]


def get_zone_settings() -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM zone_settings WHERE id = 1").fetchone()
    db.close()
    return dict(row) if row else None


def save_zone_settings(power_bounds: list[int], hr_bounds: list[int]):
    db = get_db()
    db.execute(
        """INSERT INTO zone_settings (id, power_z1, power_z2, power_z3, power_z4, power_z5,
                                       hr_z1, hr_z2, hr_z3, hr_z4, hr_z5)
           VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             power_z1=excluded.power_z1, power_z2=excluded.power_z2, power_z3=excluded.power_z3,
             power_z4=excluded.power_z4, power_z5=excluded.power_z5,
             hr_z1=excluded.hr_z1, hr_z2=excluded.hr_z2, hr_z3=excluded.hr_z3,
             hr_z4=excluded.hr_z4, hr_z5=excluded.hr_z5""",
        (*power_bounds, *hr_bounds),
    )
    db.commit()
    db.close()


def zone_bounds(settings: dict, prefix: str) -> list[int]:
    """Return the 5 lower bounds for 'power' or 'hr' prefix, in Z1..Z5 order."""
    return [settings[f"{prefix}_z{i}"] for i in range(1, 6)]
