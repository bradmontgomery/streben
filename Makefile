.PHONY: install run backfill backfill-all

install:  ## Install dependencies
	uv sync

run:  ## Start the web server on port 8000
	uv run uvicorn app.main:app --port 8000

backfill:  ## Backfill streams for up to 100 activities
	uv run strava-cli backfill-streams --limit 100

backfill-all:  ## Backfill all missing streams (runs in batches, stops when done)
	./scripts/run-backfill.sh

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'
