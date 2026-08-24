"""Parsing for Cronometer CSV exports.

Uses the stdlib ``csv`` module deliberately. pandas is a project dependency but
must not be used here: it coerces blank cells to NaN, and the whole point of this
module is that a blank cell means "not logged", which is distinct from zero.
"""
import csv
import io
import json
from datetime import datetime

# CSV header -> nutrition table column. Headers carry their units and some are
# non-ASCII elsewhere in the file, so match the exact strings Cronometer emits.
CURATED = {
    "Energy (kcal)": "energy_kcal",
    "Carbs (g)": "carbs_g",
    "Fat (g)": "fat_g",
    "Protein (g)": "protein_g",
    "Fiber (g)": "fiber_g",
    "Sugars (g)": "sugars_g",
    "Sodium (mg)": "sodium_mg",
}


class CronometerParseError(ValueError):
    """Raised when a file isn't a Cronometer export we recognize."""


def _num(value):
    """Blank -> None, never 0.0.

    The empty-string check must come before the float attempt: an unlogged day
    in a Cronometer export has every nutrient field empty, and turning those
    into zeros invents a day of eating nothing.
    """
    s = (value or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _decode(content: bytes) -> str:
    # utf-8-sig tolerates a BOM if Cronometer ever adds one. Headers contain
    # micro signs (B12, Vitamin A), so never fall back to ascii/latin-1.
    return content.decode("utf-8-sig")


def parse_daily_summary(content: bytes) -> tuple[list[dict], int]:
    """Parse a Cronometer dailysummary.csv.

    Returns (rows, skipped) where each row is a dict of curated columns plus
    ``raw_data`` (JSON of all original columns). Blank cells are None.
    Later rows win if a date appears more than once.
    """
    reader = csv.DictReader(io.StringIO(_decode(content)))
    fields = reader.fieldnames or []
    if "Date" not in fields:
        raise CronometerParseError("Not a Cronometer daily summary CSV (no Date column)")
    if "Energy (kcal)" not in fields:
        raise CronometerParseError("Not a Cronometer daily summary CSV (no Energy column)")

    by_date: dict[str, dict] = {}
    skipped = 0
    for raw in reader:
        date = (raw.get("Date") or "").strip()
        if not date:
            continue  # trailing blank line
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            skipped += 1
            continue

        completed_raw = (raw.get("Completed") or "").strip().lower()
        row = {
            "date": date,
            "completed": None if not completed_raw else (1 if completed_raw == "true" else 0),
            "raw_data": json.dumps(raw, ensure_ascii=False),
        }
        for header, column in CURATED.items():
            row[column] = _num(raw.get(header))
        by_date[date] = row

    return list(by_date.values()), skipped


def parse_biometrics(content: bytes) -> list[dict]:
    """Parse a Cronometer biometrics export into dated weight entries.

    Cronometer exports biometrics in long form (Day, Metric, Unit, Amount).
    UNVERIFIED against a real export -- confirm the headers before relying on it.
    """
    reader = csv.DictReader(io.StringIO(_decode(content)))
    fields = reader.fieldnames or []
    date_key = next((f for f in fields if f.strip() in ("Day", "Date")), None)
    metric_key = next((f for f in fields if f.strip() == "Metric"), None)
    amount_key = next((f for f in fields if f.strip() in ("Amount", "Value")), None)
    if not (date_key and metric_key and amount_key):
        raise CronometerParseError(
            "Not a Cronometer biometrics CSV (expected Day, Metric, Amount columns)"
        )
    unit_key = next((f for f in fields if f.strip() == "Unit"), None)

    by_date: dict[str, dict] = {}
    for raw in reader:
        if "weight" not in (raw.get(metric_key) or "").strip().lower():
            continue
        date = (raw.get(date_key) or "").strip()[:10]
        amount = _num(raw.get(amount_key))
        if not date or amount is None:
            continue
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            continue
        unit = (raw.get(unit_key) or "").strip().lower() if unit_key else ""
        weight_lb = amount / 0.45359237 if unit.startswith("kg") else amount
        by_date[date] = {"date": date, "weight_lb": round(weight_lb, 2)}

    return list(by_date.values())
