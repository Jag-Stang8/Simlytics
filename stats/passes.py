"""Derive passing data from the per-lap running order and save it to the database.

Two derived tables, both rebuilt per subsession (delete-then-insert, idempotent):

* lap_gaps -- one row per car per lap: the time gap to the car directly ahead,
  as milliseconds and as a fraction of the race's median lap. A "passing
  opportunity" is a query over this table (gap_pct below your threshold, green).

* passes -- one row per order inversion between consecutive laps (car A ahead of
  B at lap N-1, behind at lap N => A passed B), tagged green / pit-cycle /
  caution so passes can be sorted by flag state.

Times in the laps table are in 1/10000 s; gap_ms divides by 10, and gap_pct is
unit-independent (gap / median lap in the same units).

Run: uv run python -m stats.passes [subsession_id ...]   (default: all with laps)
"""
import argparse
from itertools import combinations

from db.connection import connection

# Laps whose field-median lap time exceeds this multiple of the race median are
# candidate caution laps, and a caution period must be at least MIN_CAUTION_RUN
# consecutive laps -- a single slow lap is a wreck or a spin, not a caution.
#
# Both values were fitted against race_summary's reported counts over the 19
# races that have lap data: the period count then comes out EXACTLY right in all
# 19, and no race's caution-lap count is off by more than 2. The factor sits
# mid-plateau (any value in 1.44-1.48 gives zero period error) rather than at an
# edge, so it should hold up on new races. Without the run-length rule the same
# sweep cannot reach zero period error at any factor.
CAUTION_LAP_FACTOR = 1.46
MIN_CAUTION_RUN = 2
# A pass is "reverted" (contested/defended) if the pass is undone within this
# many laps.
REVERT_WINDOW = 2

DDL = [
    """
    CREATE TABLE IF NOT EXISTS lap_gaps (
        subsession_id     integer NOT NULL,
        lap_num           integer NOT NULL,
        cust_id           integer NOT NULL,
        car_ahead_cust_id integer,
        gap_ms            double precision,
        gap_pct           double precision,
        same_lap          boolean NOT NULL,
        under_caution     boolean NOT NULL,
        pit_cycle         boolean NOT NULL,
        PRIMARY KEY (subsession_id, lap_num, cust_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS passes (
        pass_id        bigserial PRIMARY KEY,
        subsession_id  integer NOT NULL,
        lap_num        integer NOT NULL,
        passer_cust_id integer NOT NULL,
        passed_cust_id integer NOT NULL,
        passer_pos     integer NOT NULL,
        passed_pos     integer NOT NULL,
        gap_ms         double precision,
        is_lead_change boolean NOT NULL,
        pit_cycle      boolean NOT NULL,
        under_caution  boolean NOT NULL,
        reverted       boolean NOT NULL DEFAULT false,
        UNIQUE (subsession_id, lap_num, passer_cust_id, passed_cust_id)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_lap_gaps_subsession ON lap_gaps (subsession_id);",
    "CREATE INDEX IF NOT EXISTS idx_passes_subsession ON passes (subsession_id);",
    "CREATE INDEX IF NOT EXISTS idx_passes_passer ON passes (passer_cust_id);",
    "CREATE INDEX IF NOT EXISTS idx_passes_passed ON passes (passed_cust_id);",
]


def ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        for stmt in DDL:
            cur.execute(stmt)


def _subsessions_with_laps(conn) -> list[int]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT subsession_id FROM laps ORDER BY subsession_id")
        return [r[0] for r in cur.fetchall()]


def _min_run(laps: set[int], minimum: int) -> set[int]:
    """Drop caution runs shorter than `minimum` consecutive laps."""
    keep: set[int] = set()
    run: list[int] = []
    for lap in sorted(laps):
        if run and lap == run[-1] + 1:
            run.append(lap)
        else:
            if len(run) >= minimum:
                keep.update(run)
            run = [lap]
    if len(run) >= minimum:
        keep.update(run)
    return keep


def _race_context(conn, ss: int):
    """Return (median_laptime, caution_lap_set, pitted_set) for a subsession."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY laptime) "
            "FROM laps WHERE subsession_id = %s AND laptime > 0",
            (ss,),
        )
        median = cur.fetchone()[0]
        median = float(median) if median else None

        cur.execute(
            """
            WITH race_med AS (
                SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY laptime) AS m
                FROM laps WHERE subsession_id = %s AND laptime > 0
            ),
            lap_med AS (
                SELECT lap_num, percentile_cont(0.5) WITHIN GROUP (ORDER BY laptime) AS m
                FROM laps WHERE subsession_id = %s AND lap_num > 0 AND laptime > 0
                GROUP BY lap_num
            )
            SELECT lap_num FROM lap_med, race_med WHERE lap_med.m > race_med.m * %s
            """,
            (ss, ss, CAUTION_LAP_FACTOR),
        )
        caution = _min_run({r[0] for r in cur.fetchall()}, MIN_CAUTION_RUN)

        cur.execute(
            "SELECT cust_id, lap_num FROM lap_events "
            "WHERE subsession_id = %s AND lap_event = 'pitted'",
            (ss,),
        )
        pitted = {(r[0], r[1]) for r in cur.fetchall()}
    return median, caution, pitted


def build_subsession(conn, ss: int) -> tuple[int, int, int]:
    median, caution, pitted = _race_context(conn, ss)

    def pit_near(cust: int, lap: int) -> bool:
        # A car is in its pit cycle on the lap it pits and the lap after.
        return (cust, lap) in pitted or (cust, lap - 1) in pitted

    with conn.cursor() as cur:
        cur.execute(
            "SELECT lap_num, cust_id, position, session_time, interval_units "
            "FROM laps WHERE subsession_id = %s",
            (ss,),
        )
        by_lap: dict[int, dict[int, tuple[int, int, str | None]]] = {}
        for lap, cust, pos, st, units in cur.fetchall():
            by_lap.setdefault(lap, {})[cust] = (pos, st, units)

    # --- lap_gaps: gap to the car directly ahead, ordered by position ---
    gap_rows = []
    for lap, cars in by_lap.items():
        if lap < 1:
            continue  # lap 0 is the grid crossing; no meaningful gap
        ordered = sorted(cars.items(), key=lambda kv: kv[1][0])  # by position
        prev = None
        for cust, (pos, st, units) in ordered:
            if prev is None:  # race leader: no car ahead
                gap_rows.append(
                    (ss, lap, cust, None, None, None, False,
                     lap in caution, pit_near(cust, lap))
                )
            else:
                pcust, (_ppos, pst, punits) = prev
                gap_units = st - pst
                gap_rows.append((
                    ss, lap, cust, pcust,
                    gap_units / 10.0,
                    (gap_units / median) if median else None,
                    units == "ms" and punits == "ms",
                    lap in caution,
                    pit_near(cust, lap) or pit_near(pcust, lap),
                ))
            prev = (cust, (pos, st, units))

    # --- passes: order inversions between consecutive laps ---
    pass_rows = []
    for lap in sorted(l for l in by_lap if l >= 1):
        if lap - 1 not in by_lap:
            continue
        cur_cars, prev_cars = by_lap[lap], by_lap[lap - 1]
        common = [c for c in cur_cars if c in prev_cars]
        for a, b in combinations(common, 2):
            # inversion when the pair's relative order flips between laps
            if (prev_cars[a][0] - prev_cars[b][0]) * (cur_cars[a][0] - cur_cars[b][0]) < 0:
                passer, passed = (a, b) if cur_cars[a][0] < cur_cars[b][0] else (b, a)
                gap_units = abs(prev_cars[passer][1] - prev_cars[passed][1])
                pass_rows.append([
                    ss, lap, passer, passed,
                    cur_cars[passer][0], cur_cars[passed][0],
                    gap_units / 10.0,
                    cur_cars[passer][0] == 1,           # is_lead_change
                    pit_near(passer, lap) or pit_near(passed, lap),
                    lap in caution,
                ])

    # --- reverted: a pass undone (retaken by the passed car) within the window ---
    reverse_index: dict[tuple[int, int], list[int]] = {}
    for r in pass_rows:
        reverse_index.setdefault((r[2], r[3]), []).append(r[1])  # (passer,passed)->laps
    for r in pass_rows:
        lap, passer, passed = r[1], r[2], r[3]
        retakes = reverse_index.get((passed, passer), [])
        r.append(any(lap < rl <= lap + REVERT_WINDOW for rl in retakes))

    with conn.cursor() as cur:
        cur.execute("DELETE FROM lap_gaps WHERE subsession_id = %s", (ss,))
        cur.execute("DELETE FROM passes WHERE subsession_id = %s", (ss,))
        cur.executemany(
            "INSERT INTO lap_gaps (subsession_id, lap_num, cust_id, car_ahead_cust_id, "
            "gap_ms, gap_pct, same_lap, under_caution, pit_cycle) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            gap_rows,
        )
        cur.executemany(
            "INSERT INTO passes (subsession_id, lap_num, passer_cust_id, passed_cust_id, "
            "passer_pos, passed_pos, gap_ms, is_lead_change, pit_cycle, under_caution, "
            "reverted) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            pass_rows,
        )
    return len(gap_rows), len(pass_rows), len(caution)


def main() -> None:
    ap = argparse.ArgumentParser(description="Derive and save passing data")
    ap.add_argument("subsessions", type=int, nargs="*",
                    help="subsession ids to rebuild (default: all with lap data)")
    args = ap.parse_args()

    with connection() as conn:
        ensure_tables(conn)
        targets = args.subsessions or _subsessions_with_laps(conn)
        for ss in targets:
            gaps, passes_, cautions = build_subsession(conn, ss)
            print(f"{ss}: {gaps} gaps, {passes_} passes, {cautions} caution laps")


if __name__ == "__main__":
    main()