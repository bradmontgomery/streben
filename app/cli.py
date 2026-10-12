"""CLI commands for managing the Strava activity tracker."""
import argparse
import json
import sys
import time

from app.database import get_db, init_db
from app.services import strava_client
from app.routers.strava import _insert_strava_streams
from app.services.cronometer import CronometerParseError, parse_biometrics, parse_daily_summary
from app.services.nutrition import upsert_nutrition_rows, upsert_weights


def backfill_streams(args):
    init_db()
    db = get_db()
    rows = db.execute(
        """SELECT a.id, a.strava_id, a.name, a.start_date FROM activities a
           WHERE a.source = 'strava' AND a.strava_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM activity_streams s WHERE s.activity_id = a.id)
           ORDER BY a.start_date DESC"""
    ).fetchall()

    if not rows:
        print("All Strava activities already have stream data.")
        db.close()
        return

    limit = args.limit or len(rows)
    total = min(limit, len(rows))
    print(f"Found {len(rows)} activities without streams. Processing {total}...")

    filled = 0
    errors = 0
    for i, row in enumerate(rows[:total]):
        label = row["name"] or row["start_date"] or f"id={row['id']}"
        print(f"  [{i+1}/{total}] {label} (strava:{row['strava_id']})...", end=" ", flush=True)
        try:
            streams = strava_client.get_activity_streams(row["strava_id"])
            _insert_strava_streams(db, row["id"], streams)
            db.commit()
            count = db.execute(
                "SELECT COUNT(*) FROM activity_streams WHERE activity_id = ?", (row["id"],)
            ).fetchone()[0]
            print(f"{count} points")
            filled += 1
        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1

        # Respect Strava rate limits (100 req / 15 min)
        if i < total - 1:
            time.sleep(1)

    db.close()
    print(f"\nDone: {filled} backfilled, {errors} errors, {len(rows) - total} remaining.")


def backfill_fields(args):
    """Re-extract fields from stored raw_data JSON for existing activities."""
    init_db()
    db = get_db()
    rows = db.execute(
        "SELECT id, raw_data FROM activities WHERE source = 'strava' AND raw_data IS NOT NULL"
    ).fetchall()

    if not rows:
        print("No Strava activities with raw_data found.")
        db.close()
        return

    updated = 0
    for row in rows:
        act = json.loads(row["raw_data"])
        db.execute(
            """UPDATE activities SET
                total_elevation_gain = ?,
                calories = ?,
                description = ?,
                device_name = ?,
                average_temp = ?,
                summary_polyline = ?
               WHERE id = ?""",
            (
                act.get("total_elevation_gain"),
                act.get("calories"),
                act.get("description"),
                act.get("device_name"),
                act.get("average_temp"),
                (act.get("map") or {}).get("summary_polyline"),
                row["id"],
            ),
        )
        updated += 1

    db.commit()
    db.close()
    print(f"Updated {updated} activities from stored raw_data.")



def import_cronometer(args):
    """Import a Cronometer daily summary CSV. Re-importing a date overwrites it."""
    init_db()
    try:
        rows, skipped = parse_daily_summary(open(args.path, "rb").read())
    except (CronometerParseError, OSError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    db = get_db()
    upsert_nutrition_rows(db, rows)
    db.commit()
    total = db.execute("SELECT COUNT(*) FROM nutrition").fetchone()[0]
    db.close()

    logged = sum(1 for r in rows if r["energy_kcal"] is not None)
    print(f"Imported {len(rows)} days ({logged} logged, {len(rows) - logged} blank)"
          + (f", {skipped} skipped" if skipped else ""))
    print(f"{total} days now stored.")


def import_biometrics(args):
    """Import weight entries from a Cronometer biometrics CSV."""
    init_db()
    try:
        entries = parse_biometrics(open(args.path, "rb").read())
    except (CronometerParseError, OSError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    db = get_db()
    upsert_weights(db, entries, source="cronometer")
    db.commit()
    db.close()
    print(f"Imported {len(entries)} weight entries.")


def backfill_nutrition_fields(args):
    """Re-extract curated columns from stored nutrition raw_data."""
    init_db()
    from app.services.cronometer import CURATED, _num

    db = get_db()
    rows = db.execute("SELECT date, raw_data FROM nutrition WHERE raw_data IS NOT NULL").fetchall()
    assignments = ", ".join(f"{c} = ?" for c in CURATED.values())
    updated = 0
    for row in rows:
        raw = json.loads(row["raw_data"])
        values = [_num(raw.get(header)) for header in CURATED]
        db.execute(f"UPDATE nutrition SET {assignments} WHERE date = ?", (*values, row["date"]))
        updated += 1
    db.commit()
    db.close()
    print(f"Updated {updated} nutrition days from stored raw_data.")


def main():
    parser = argparse.ArgumentParser(description="Strava Activity Tracker CLI")
    sub = parser.add_subparsers(dest="command")

    bf = sub.add_parser("backfill-streams", help="Fetch missing stream data from Strava")
    bf.add_argument("--limit", type=int, default=None, help="Max number of activities to process")
    bf.set_defaults(func=backfill_streams)

    bf2 = sub.add_parser("backfill-fields", help="Re-extract fields from stored raw_data JSON")
    bf2.set_defaults(func=backfill_fields)

    ic = sub.add_parser("import-cronometer", help="Import a Cronometer daily summary CSV")
    ic.add_argument("path", help="Path to dailysummary.csv")
    ic.set_defaults(func=import_cronometer)

    ib = sub.add_parser("import-biometrics", help="Import weights from a Cronometer biometrics CSV")
    ib.add_argument("path", help="Path to biometrics CSV")
    ib.set_defaults(func=import_biometrics)

    bn = sub.add_parser("backfill-nutrition-fields",
                        help="Re-extract nutrition columns from stored raw_data")
    bn.set_defaults(func=backfill_nutrition_fields)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
