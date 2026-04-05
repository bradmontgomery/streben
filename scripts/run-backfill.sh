#!/bin/bash
while true; do
    output=$(uv run strava-cli backfill-streams --limit 100)
    echo "$output"
    if echo "$output" | grep -q "All Strava activities already have stream data"; then
        echo "Backfill complete!"
        break
    fi
    sleep 30
done
