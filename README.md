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
- **Browse** it in a web UI — a race report with five tabs (result, timeline,
  passing, pit cycles, pace), a time-frame explorer for any range of rounds, and
  a head-to-head comparison.
- **Explore** further in a matplotlib/seaborn notebook.

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

Season-grained queries take no parameters and return every season at once:

| Area | Files |
|------|-------|
| Standings | `driver_standings`, `driver_points_progression`, `driver_standings_drops`, `driver_standings_whatif` |
| Passing | `passing_leaderboard`, `passing_conversion`, `passing_by_flag`, `passing_by_track`, `passing_restarts`, `passing_score` |
| Pit cycles | `pit_cycle_ranking`, `pit_cycle_by_race` |
| Pace | `green_laps` |

Parameterized queries (added for the web UI) take named parameters, and their
scope parameters accept `NULL` for "everything":

| Scope | Files |
|-------|-------|
| Catalog | `league_list`, `season_list`, `session_list` |
| One race | `race_result`, `race_running_order`, `race_events`, `race_pass_matrix`, `race_passing_by_flag`, `race_pit_cycles` |
| Season-wide | `driver_race_matrix`, `driver_pair_passes` |

`driver_race_matrix` is the one to reach for when comparing across a range of
races: it returns counts and raw values at (race, driver) grain and never a
ratio, so narrowing a date range is a row filter rather than a new query.

### 4. Browse the web UI

```bash
uv run uvicorn web.main:app --reload --port 8000
```

Then open <http://127.0.0.1:8000> — it redirects to the most recent race.

| Page | What's there |
|------|--------------|
| `/session/{subsession_id}` | One race: finishing table, lap-by-lap position chart with caution bands, pass matrix, pit windows, pace distribution |
| `/season` | Any range of rounds: build a stat table from 15 metrics, driver x round heatmap, points progression |
| `/h2h` | Two drivers over any range, plus their on-track meetings |

Every selection lives in the URL, so a view is a shareable link.

The design system is a plain stylesheet — [`web/static/app.css`](web/static/app.css).
Nothing generates it; edit it directly. Layout is driven by three custom
properties at the top of the file: `--rail-w`, `--aside-w` and `--gutter`.

### 5. Explore in the notebook

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
stats/         derived analytics:
                 passes.py          on-track passes + per-lap gaps
                 pit_cycles.py      green-flag pit-cycle times
                 driver_features.py per-driver pace/results feature vectors
                 metrics.py         range aggregation + passing z-scores
queries/       analytics SQL (season-grained and parameterized)
web/           FastAPI + Jinja UI
                 main.py            routes
                 data.py            the only place the app runs SQL
                 templates/         one file per page, one partial per tab
                 static/app.css     the design system, hand-edited
                 lib/               formatting and Altair chart builders
notebooks/     matplotlib/seaborn analysis
resources/     the UI design mockups the web layer was built from
```

## Notes

- **"Season" means the league season** (`league_season_id`); the plain iRacing
  `season_id` is `0` for hosted league races.
- **Passing** is derived from the per-lap running order — start/finish-line
  granularity, so passes made and given back within a single lap aren't visible.
- **Cautions** aren't marked in the data; they're inferred from lap-time
  inflation — a lap whose field median exceeds the race median by 1.46x, in a run
  of at least two laps. Both constants were fitted against iRacing's reported
  counts: caution *periods* then come out exact in every race that has lap data,
  and no race's caution-lap count is off by more than two. Treat the bands as
  indicative rather than official, and note that pass classification inherits the
  same imprecision. Changing either constant means re-running `stats.passes` and
  then `stats.pit_cycles`, in that order.
- **A race with no lap chart ingested** still shows its finishing result, but
  everything lap-derived (timeline, passing, pit, pace) is legitimately empty and
  its season passing totals are understated.
- See [`CLAUDE.md`](CLAUDE.md) for deeper architecture and domain notes.