"""Persistence for nutrition days and body-metric entries."""
from datetime import datetime, timezone

from app.database import get_db

_COLUMNS = [
    "energy_kcal", "carbs_g", "fat_g", "protein_g",
    "fiber_g", "sugars_g", "sodium_mg", "completed", "raw_data",
]


def upsert_nutrition_rows(db, rows: list[dict]) -> int:
    """Insert or overwrite one nutrition row per date.

    Every column is listed in the DO UPDATE SET and NULLs are allowed through.
    Deliberately no COALESCE(excluded.x, nutrition.x) idiom: a day the user
    cleared in Cronometer must come back empty, not keep stale values.
    """
    if not rows:
        return 0
    imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    assignments = ", ".join(f"{c}=excluded.{c}" for c in _COLUMNS)
    placeholders = ", ".join(f":{c}" for c in _COLUMNS)
    db.executemany(
        f"""INSERT INTO nutrition (date, {', '.join(_COLUMNS)}, imported_at)
            VALUES (:date, {placeholders}, :imported_at)
            ON CONFLICT(date) DO UPDATE SET
              {assignments}, imported_at=excluded.imported_at""",
        [{**r, "imported_at": imported_at} for r in rows],
    )
    return len(rows)


def upsert_weights(db, entries: list[dict], source: str = "manual") -> int:
    if not entries:
        return 0
    db.executemany(
        """INSERT INTO body_metrics (date, weight_lb, source)
           VALUES (:date, :weight_lb, :source)
           ON CONFLICT(date) DO UPDATE SET
             weight_lb=excluded.weight_lb, source=excluded.source""",
        [{**e, "source": source} for e in entries],
    )
    return len(entries)


def delete_weight(date: str) -> None:
    db = get_db()
    db.execute("DELETE FROM body_metrics WHERE date = ?", (date,))
    db.commit()
    db.close()


def list_weights(limit: int = 20) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT date, weight_lb, source FROM body_metrics ORDER BY date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]
