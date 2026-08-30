# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`simlytics` ingests **iRacing** race-result JSON (lap charts, event results) into a
**PostgreSQL** database and derives race analytics from it. Domain vocabulary comes
straight from iRacing: `subsession_id` (one race), `cust_id` (a driver), `sof`
(Strength of Field), `league_points`, `laps_led`, `incidents`, etc.

The **ingest pipeline is complete and verified** end-to-end against the live
database (parse → load for both file types, idempotent on re-run), and `queries/`
and `stats/` are populated. `web/` is a **FastAPI + Jinja web UI** on top of them —
a read-only consumer that never writes. `schema/` holds no DDL (the DB itself is the
schema source of truth — see below). `main.py` is leftover PyCharm boilerplate and
is not part of the app.

## Environment & commands

Dependencies are managed with **uv** (`uv.lock`, `pyproject.toml`); Python >= 3.11.

```bash
uv sync                                          # install deps into .venv
uv run python -m ingest.ingest <path.json> ...   # ingest one or more result files
uv run python -m db.introspect                   # dump live DB schema (read-only)
uv run uvicorn web.main:app --reload --port 8000 # the web UI
```

`web/main.py` puts the repo root on `sys.path` so `db`, `stats` and `queries`
resolve however uvicorn is launched.

There was a Streamlit UI under `app/` until it was removed: it could not reach
the designs in `resources/`, because Streamlit renders its own widget chrome and
spacing while the mockups are bespoke layouts. Its data and formatting layers
survive as `stats/metrics.py` and `web/lib/`; the git history has the rest.

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
statements against the DB directly, then update the matching `Parsed*` dataclass,
parser and loader so future ingests carry the column. Changes made so far:

- `laps.interval_units` — widened from `integer` to `text` for the
  `"ms"`/`"lap"`/null enum.
- `races.start_time timestamptz` — the race date. iRacing has no round number or
  date in the normalized tables; `weather.simulated_start_time` is in-sim time of
  day, not the calendar date. Backfilled for existing rows straight from
  `raw_results` (`raw_json->'data'->>'start_time'`), so no re-ingest was needed.
  Everything that orders or dates races (round numbers, the season rail) derives
  from this column.

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
- `queries/` — SQL for analytics. Two families:

  **Season-grained** (no parameters; every season in one result set): standings —
  gross, progression, drop-adjusted, what-if; passing — leaderboard, conversion,
  by-flag, by-track, restarts, and `passing_score.sql` (an overall score blending
  racecraft/attack/defense/restart as weighted z-scores, emitting the `z_*`
  columns so a caller can re-weight without re-querying); pit —
  `pit_cycle_ranking.sql`. All are season-general (window functions, no hardcoded
  ids).

  **Parameterized** (added for the app; every one takes named `%(...)s` params):
  `league_list`, `season_list`, `session_list`, `race_result`,
  `race_running_order`, `race_events`, `race_pass_matrix`, `race_passing_by_flag`,
  `race_pit_cycles`, `driver_race_matrix`, `driver_pair_passes`. Scope params
  accept `NULL` for "everything" via the `%(x)s::int IS NULL OR col = %(x)s::int`
  idiom — the cast is required or Postgres cannot infer the type.

  Two gotchas when writing new ones. **A literal `%` anywhere in the file — even
  in a comment — is parsed as a placeholder** and raises
  `only '%s', '%b', '%t' are allowed`; write "percent" or double it. And a query
  with named placeholders **cannot be run with `params=None`**, so making an
  existing query parameterized breaks callers that pass nothing (this is why
  `green_laps.sql` takes an optional `subsession_id` and `stats/driver_features.py`
  passes `{"subsession_id": None}` explicitly).
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
- `stats/driver_features.py` — assembles a per-driver feature vector (green-lap pace
  normalized to each race median + fitted skew-normal, results, passing z-scores,
  pit speed) as a pandas DataFrame via `build_features()`; the basis for clustering /
  similarity work. `green_laps.sql` extracts the clean racing laps it uses.
- `web/` — the **FastAPI + Jinja UI**, a read-only consumer of the same SQL.
  - `web/main.py` — routes and the per-page data assembly. Three pages:
    `/session/{id}` (five tabs: result, timeline, passing, pit, pace),
    `/season` (the time-frame explorer) and `/h2h` (head-to-head).
  - `web/data.py` — **the only place the app executes SQL.** `rows(name, **params)`
    returns a list of dicts. Templates never touch the database.
  - `web/templates/` — one file per page plus a partial per session tab.
  - `web/static/app.css` — **the design system, as real CSS**: tokens as custom
    properties, then one class per component. Lifted from
    `resources/Simlytics Web UI Ideas.dc.html`; every value there is the mockup's
    own. Nothing generates this file — edit it directly. The three layout knobs
    are `--rail-w`, `--aside-w` and `--gutter`.
  - `web/lib/fmt.py` — formatting and the palette. `web/lib/charts.py` — Altair
    builders that emit Vega-Lite specs; no SQL, no page code.

  **Charts are Vega-Lite, rendered by vega-embed.** `charts.position_by_lap()`
  takes a `data_url`: pass one and the spec references
  `/api/session/{id}/running.json` and splits the field with a Vega-Lite filter
  instead of in pandas. Without it the spec inlines every lap row, which put that
  page at 2.2 MB. Prefer the URL form for anything lap-grained. Most other
  visuals — the pass matrix, pit window, pace boxes, flag strip, points
  progression — are plain HTML/CSS or inline SVG, not charts at all.

  **The range rule.** `driver_race_matrix.sql` returns only counts and raw values
  at (subsession_id, cust_id) grain — never a ratio. So narrowing a range is a
  row filter on an already-fetched frame, and every rate is recomputed by summing
  numerator and denominator over the surviving races. Rates are computed from
  summed components, never averaged from per-race rates.

- `stats/metrics.py` — range aggregation in pandas over that matrix, plus the
  four passing z-scores and the blended score. Reproduces `passing_score.sql`
  to that query's display rounding. Frontend-independent; a notebook can use it.

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
- **Time units.** Raw iRacing times — `laps.laptime`, `laps.session_time`,
  `race_results.avg_lap` / `best_lap_time` — are in **ten-thousandths of a second**
  (Bristol's median lap of 163692 is 16.37 s). The `*_ms` columns on `pit_cycles`
  are already **milliseconds**: `stats/pit_cycles.py` divides by 10 on the way in.
  `web/lib/fmt.py` has `laptime()` for the former and `delta_s()` for the latter.
- **Caution laps are derived, not reported.** `stats/passes.py` flags a lap whose
  field-median laptime exceeds the race median by `CAUTION_LAP_FACTOR` (1.46) and
  requires a run of at least `MIN_CAUTION_RUN` (2) consecutive laps — a single slow
  lap is a wreck or a spin, not a caution. The verdict persists on
  `lap_gaps.under_caution`, and everything downstream (pass classification, the
  Timeline's yellow bands, `pit_cycles`' green-stop test) reads it back rather than
  re-deriving it.

  Both constants were fitted against `race_summary`'s reported counts over the 19
  races with lap data: **the caution-period count is exact in all 19**, and no
  race's caution-lap count is off by more than 2 (total absolute error 13, ten
  races exact). The factor sits mid-plateau — anything in 1.44–1.48 gives zero
  period error — rather than at an edge, so it should hold on new races. The
  ratio distribution is sharply bimodal (green laps cluster at 1.00, caution laps
  at 2.0+), so the threshold sits in an empty valley and the residual error is
  boundary laps, not misclassification. Hysteresis was tried and did not beat the
  simple threshold.

  **Changing either constant invalidates stored data.** Re-run
  `python -m stats.passes` and then `python -m stats.pit_cycles`, in that order —
  `pit_cycles` reads `lap_gaps.under_caution` to decide which stops are green.
- **Two races have no lap chart ingested**: `86440695` and `87132390` have zero rows
  in `laps`, `lap_gaps`, `passes` and `pit_cycles`, though their event results are
  present. Anything lap-derived is legitimately empty for them, and their season
  passing totals are understated. Not a bug — missing input files.

## Conventions

- Every target table gets a matching `Parsed*` dataclass; add both the dataclass and
  its `parse_*` function when introducing a new entity.
- Keep parsing (`parsers.py`) free of DB calls and loading (`loader.py`) free of JSON
  parsing — the separation is the point of the layering.
- Route all DB access through `db/connection.py` rather than opening psycopg
  connections directly.
- In the app, the same rule one level up: SQL lives in `queries/*.sql` and runs
  only through `web/data.py`. Routes call `data.rows(...)`; they never build SQL
  and never open a connection, and templates never touch either.
- Keep formatting out of SQL. Queries emit raw values (ticks, milliseconds,
  0-based positions where the source is 0-based); `web/lib/fmt.py` formats them.
  The exception is the pre-existing `pit_cycle_by_race.sql`, which rounds to
  seconds — it predates this rule and notebooks depend on its shape, which is why
  `race_pit_cycles.sql` exists alongside it rather than replacing it.
- **Chart colour is validated, not chosen.** A league race has 30–50 entries, far
  past what hue can carry, so charts use **emphasis** — grey the field, spend the
  fixed slots in `fmt.HIGHLIGHT` on the drivers under comparison, capped at 8 and
  never cycled. Those slots are the dark-surface steps, validated as a set against
  the `#1b2024` chart surface (lightness band, chroma floor, adjacent CVD
  separation, normal-vision floor, 3:1 contrast). `fmt.ACCENT` (`#5aa2f0`) is UI
  chrome only — it sits outside the dark band and must not carry series identity.
  Re-run the validator before adding or changing any series colour; a de-emphasis
  grey fails the chroma floor if it is asked to carry identity in a stacked bar.