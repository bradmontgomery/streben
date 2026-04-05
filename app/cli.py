"""CLI commands for managing the Strava activity tracker."""
import argparse
import sys
import time

from app.database import get_db, init_db
from app.services import strava_client
from app.routers.strava import _insert_strava_streams


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


def main():
    parser = argparse.ArgumentParser(description="Strava Activity Tracker CLI")
    sub = parser.add_subparsers(dest="command")

    bf = sub.add_parser("backfill-streams", help="Fetch missing stream data from Strava")
    bf.add_argument("--limit", type=int, default=None, help="Max number of activities to process")
    bf.set_defaults(func=backfill_streams)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
