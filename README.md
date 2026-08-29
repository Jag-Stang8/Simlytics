# simlytics

League racing analytics for **iRacing**. It ingests race-result JSON into
PostgreSQL and turns it into standings, passing, and pit-strategy analysis —
including derived datasets that iRacing doesn't provide directly (per-lap gaps,
on-track passes, and green-flag pit-cycle times).

## What it does

- **Ingest** iRacing event-result and lap-chart JSON into a normalized schema,
  keeping the raw payloads alongside (idempotent re-runs).
- **Derive** analytics the raw data only implies:
  - **Passing** — every on-track pass (order inversion between laps), tagged
    green / pit-cycle / caution, plus per-lap gaps to the car ahead.
  - **Pit cycles** — green-flag pit-stop cycle times (in-lap + out-lap), with
    repair/stall outliers flagged.
- **Query** driver standings (gross, drop-adjusted, what-if), passing skill
  (leaderboard, conversion, by-flag, by-track, restarts, and a blended score),
  and pit-cycle rankings.
- **Visualize** it all in a matplotlib/seaborn notebook.

## Requirements

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/)
- A running **PostgreSQL** database

## Setup

```bash
uv sync                 # install dependencies into .venv
cp .env.example .env     # (Windows: copy .env.example .env)
# then edit .env with your PostgreSQL connection details
```

`.env` (gitignored) provides the connection used by everything:

```
PGHOST=localhost
PGPORT=5432
PGDATABASE=your_database
PGUSER=your_user
PGPASSWORD=your_password
```

The schema lives directly in the database (no migration tool). Inspect the current
tables, columns, and constraints with:

```bash
uv run python -m db.introspect
```

## Usage

### 1. Ingest race data

iRacing exports two JSON files per race — an event result and a lap chart. Ingest
one or many (a mixed batch is auto-ordered, since lap-chart rows reference the
event-result rows):

```bash
uv run python -m ingest.ingest eventresult-83742118.json iracing-lap-chart-83742118.json
```

### 2. Build the derived datasets

```bash
uv run python -m stats.passes       # -> lap_gaps, passes tables
uv run python -m stats.pit_cycles   # -> pit_cycles table
```

Both rebuild per subsession and are safe to re-run after ingesting new races.

### 3. Query

SQL lives in [`queries/`](queries/), all season-general (no hardcoded ids):

| Area | Files |
|------|-------|
| Standings | `driver_standings`, `driver_points_progression`, `driver_standings_drops`, `driver_standings_whatif` |
| Passing | `passing_leaderboard`, `passing_conversion`, `passing_by_flag`, `passing_by_track`, `passing_restarts`, `passing_score` |
| Pit cycles | `pit_cycle_ranking`, `pit_cycle_by_race` |

### 4. Explore in the notebook

```bash
uv run jupyter lab      # then open notebooks/notebook1.ipynb
```

The notebook reads the `.sql` files live and charts standings, passing, and
pit-cycle analysis. Notebook outputs are stripped on commit (via `nbstripout`), so
run the cells locally to render the charts.

## Project layout

```
db/            connection helper (single DB access point) + schema introspection
ingest/        JSON -> PostgreSQL: parsers (dataclasses), loader (upserts), CLI
stats/         derived analytics: passes.py (passing), pit_cycles.py (pit cycles)
queries/       analytics SQL (standings, passing, pit cycles)
notebooks/     matplotlib/seaborn analysis
```

## Notes

- **"Season" means the league season** (`league_season_id`); the plain iRacing
  `season_id` is `0` for hosted league races.
- **Passing** is derived from the per-lap running order — start/finish-line
  granularity, so passes made and given back within a single lap aren't visible.
- **Cautions** aren't marked in the data; they're inferred from lap-time inflation
  (validated against iRacing's reported caution counts).
- See [`CLAUDE.md`](CLAUDE.md) for deeper architecture and domain notes.