# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`simlytics` ingests **iRacing** race-result JSON (lap charts, event results) into a
**PostgreSQL** database and derives race analytics from it. Domain vocabulary comes
straight from iRacing: `subsession_id` (one race), `cust_id` (a driver), `sof`
(Strength of Field), `league_points`, `laps_led`, `incidents`, etc.

The **ingest pipeline is complete and verified** end-to-end against the live
database (parse → load for both file types, idempotent on re-run). Still empty
placeholders: `queries/`, `stats/`, and `schema/` (the DB itself is the schema
source of truth — see below). `main.py` is leftover PyCharm boilerplate and is not
part of the app.

## Environment & commands

Dependencies are managed with **uv** (`uv.lock`, `pyproject.toml`); Python >= 3.11.

```bash
uv sync                                          # install deps into .venv
uv run python -m ingest.ingest <path.json> ...   # ingest one or more result files
uv run python -m db.introspect                   # dump live DB schema (read-only)
```

`psycopg` requires the `[binary]` extra (bundles libpq); it's already in
`pyproject.toml`. The ingest CLI accepts multiple files and auto-orders
event-results before lap-charts within a batch (lap-chart rows have FKs onto the
event-result rows).

Database connection is read from environment variables (loaded via `python-dotenv`
from a `.env` file that is not committed and must be created):
`PGHOST`, `PGPORT` (default 5432), `PGDATABASE`, `PGUSER`, `PGPASSWORD`.

There is currently **no test suite, linter, or CI configured**.

### Schema management

The schema lives **only in the running PostgreSQL database** — there is no
migration tool (Flyway was removed) and `schema/` holds no DDL. `db/introspect.py`
is the way to see the current shape. When a schema change is needed, run `ALTER`
statements against the DB directly (as done for `laps.interval_units`, which was
widened from `integer` to `text` to hold the `"ms"`/`"lap"`/null enum).

## Architecture

The pipeline is layered: **raw JSON → normalized rows → analytics**.

- `db/connection.py` — the only DB access point. `_get_dsn()` builds the psycopg DSN
  from the `PG*` env vars. `get_connection()` returns a raw `psycopg.Connection`;
  the `connection()` context manager wraps commit/rollback/close. Prefer the context
  manager for anything transactional.

- `ingest/ingest.py` — CLI entrypoint. `detect_file_type()` classifies a payload
  (lap-chart has `lapData`; event-result has `data.session_results`), then
  `ingest_eventresult_json()` / `ingest_lap_chart_json()` dispatch to parsers +
  loader. Each file is ingested in its own `connection()` transaction; a bad file in
  a batch is reported and skipped.

- `ingest/parsers.py` — pure transformation layer. Defines a `Parsed*` dataclass for
  every target table (`ParsedRaceResult`, `ParsedLap`, `ParsedDriver`, `ParsedTrack`,
  `ParsedSeason`, `ParsedLeague`, `ParsedWeather`, ...) and `parse_*` functions that
  turn a raw iRacing JSON dict into lists of those dataclasses. No DB access here.

- `ingest/loader.py` — persistence layer. `load_*` functions take a live `conn` and
  write rows. Note the **raw-then-normalize** pattern: `load_raw_json()` upserts the
  full payload into a `raw_results` table keyed on `(subsession_id, file_type)` with
  `ON CONFLICT ... DO UPDATE`, so re-ingesting the same file is idempotent. Normalized
  `load_*` functions populate the typed tables from `Parsed*` objects.

- `db/introspect.py` — read-only schema dump (tables, columns, PKs, FKs, indexes).
- `queries/` — SQL for analytics. Standings: gross, progression, drop-adjusted,
  what-if. Passing: leaderboard, conversion, by-flag, by-track, restarts, and
  `passing_score.sql` (an overall score blending racecraft/attack/defense/restart
  as weighted z-scores). Pit: `pit_cycle_ranking.sql` (green pit-cycle time lost per
  driver). All are season-general (window functions, no hardcoded ids).
- `stats/passes.py` — derives passing data from the lap running order into two
  rebuilt-per-subsession tables: `lap_gaps` (per car/lap gap to the car ahead, as
  `gap_ms` and `gap_pct` of the median lap) and `passes` (order inversions tagged
  green / `pit_cycle` / `under_caution` / `reverted`). Run:
  `uv run python -m stats.passes`.
- `stats/pit_cycles.py` — derives green-flag pit-cycle times into the `pit_cycles`
  table: each green stop's in-lap + out-lap (consecutive `pitted` laps; cycle time
  from `session_time` deltas so invalid pit laps don't corrupt it), `time_lost_ms`
  vs the median lap, an `in_green_window` flag (a significant share of the field
  pitting nearby), and `is_outlier` (per-race Tukey Q3+3*IQR on time lost — flags
  repair/stall/penalty stops; pit-cycle queries exclude it). Run:
  `uv run python -m stats.pit_cycles`.
- `notebooks/` — Jupyter notebooks for exploration.

Run everything as a module from the repo root (`python -m ingest.ingest`). Within
the `ingest` package, modules import each other relatively (`from . import loader,
parsers`); the DB layer is imported by path (`from db.connection import ...`).

## Domain notes (learned from real payloads)

- **"season" = league season.** Parsers map `season_id`/`season_name` from
  `league_season_id`/`league_season_name`; the plain `season_id` is `0` (Hosted) and
  is not a usable key.
- **Field-name drift** between JSON and the model: `laps_led` ← `laps_lead`,
  `car_num` ← `livery.car_number`, `sof` ← `race_summary.field_strength`,
  weather `temp_values` ← `temp_value`, `laptime` ← `lap_time`, `position` ←
  `lap_position`.
- The lap-chart file is **wide-format** (one `lap_N` cell per lap on each driver row)
  and has no `data` wrapper; event-results nest everything under `data`.
- A lap-chart file can only be ingested **after** its event-result (FK dependency).

## Conventions

- Every target table gets a matching `Parsed*` dataclass; add both the dataclass and
  its `parse_*` function when introducing a new entity.
- Keep parsing (`parsers.py`) free of DB calls and loading (`loader.py`) free of JSON
  parsing — the separation is the point of the layering.
- Route all DB access through `db/connection.py` rather than opening psycopg
  connections directly.