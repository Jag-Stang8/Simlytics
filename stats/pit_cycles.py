"""Derive green-flag pit-cycle times from the lap data and save them.

A pit cycle is a maximal run of consecutive 'pitted' laps: the in-lap (drive in)
and the out-lap (drive out), which is almost always two laps because the stop
straddles the start/finish line -- the stationary time lands in whichever of the
two laps holds the line. The cycle counts as green only if neither those laps nor
the green lap before them are under caution.

Cycle time is measured as session_time(last pit lap) - session_time(last green lap
before pitting): the elapsed time across the in-lap + out-lap. That equals the sum
of those lap times but is immune to the invalid (-1) lap times pit stops sometimes
record. time_lost subtracts what those laps would have taken at the race's median
green lap.

A stop is "in a green pit window" when at least MIN_FIELD_FRACTION of the field
made a green stop within WINDOW_LAPS laps of it -- a real pit cycle where a
significant portion of the field pits, not a one-off stop.

Times are stored in milliseconds. Run: uv run python -m stats.pit_cycles
"""
import argparse
import statistics
from collections import defaultdict

from db.connection import connection

WINDOW_LAPS = 3            # +/- laps that define a shared pit window
MIN_FIELD_FRACTION = 0.30  # share of the field pitting to call it a real window
# A stop is an outlier (repair / stall / penalty, not a normal green stop) when its
# time lost exceeds Q3 + OUTLIER_IQR_MULT * IQR of the race's green-window stops.
OUTLIER_IQR_MULT = 3.0

DDL = [
    """
    CREATE TABLE IF NOT EXISTS pit_cycles (
        subsession_id   integer NOT NULL,
        cust_id         integer NOT NULL,
        stop_num        integer NOT NULL,
        in_lap          integer NOT NULL,
        out_lap         integer NOT NULL,
        n_pit_laps      integer NOT NULL,
        in_lap_time_ms  double precision,
        out_lap_time_ms double precision,
        cycle_time_ms   double precision NOT NULL,
        time_lost_ms    double precision NOT NULL,
        window_pitters  integer NOT NULL,
        in_green_window boolean NOT NULL,
        is_outlier      boolean NOT NULL DEFAULT false,
        PRIMARY KEY (subsession_id, cust_id, in_lap)
    );
    """,
    "ALTER TABLE pit_cycles ADD COLUMN IF NOT EXISTS is_outlier boolean NOT NULL DEFAULT false;",
    "CREATE INDEX IF NOT EXISTS idx_pit_cycles_subsession ON pit_cycles (subsession_id);",
    "CREATE INDEX IF NOT EXISTS idx_pit_cycles_cust ON pit_cycles (cust_id);",
]


def ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        for stmt in DDL:
            cur.execute(stmt)


def _subsessions_with_laps(conn) -> list[int]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT subsession_id FROM laps ORDER BY subsession_id")
        return [r[0] for r in cur.fetchall()]


def _group_consecutive(laps: list[int]) -> list[list[int]]:
    groups, run = [], [laps[0]]
    for lap in laps[1:]:
        if lap == run[-1] + 1:
            run.append(lap)
        else:
            groups.append(run)
            run = [lap]
    groups.append(run)
    return groups


def build_subsession(conn, ss: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY laptime) "
            "FROM laps WHERE subsession_id = %s AND laptime > 0",
            (ss,),
        )
        median = cur.fetchone()[0]
        if not median:
            return 0
        median_ms = float(median) / 10.0

        cur.execute(
            "SELECT DISTINCT lap_num FROM lap_gaps WHERE subsession_id = %s AND under_caution",
            (ss,),
        )
        caution = {r[0] for r in cur.fetchall()}

        cur.execute(
            "SELECT lap_num, cust_id, laptime, session_time FROM laps WHERE subsession_id = %s",
            (ss,),
        )
        laps_data: dict[tuple[int, int], tuple[int, int]] = {}
        field: set[int] = set()
        for lap, cust, laptime, st in cur.fetchall():
            laps_data[(cust, lap)] = (laptime, st)
            field.add(cust)

        cur.execute(
            "SELECT cust_id, lap_num FROM lap_events "
            "WHERE subsession_id = %s AND lap_event = 'pitted' AND lap_num > 0",
            (ss,),
        )
        pitted: dict[int, list[int]] = defaultdict(list)
        for cust, lap in cur.fetchall():
            pitted[cust].append(lap)

    field_size = len(field)
    stops = []
    for cust, plaps in pitted.items():
        for run in _group_consecutive(sorted(set(plaps))):
            in_lap, out_lap = run[0], run[-1]  # in-lap ... out-lap (last pit lap)
            prev = in_lap - 1
            # need a green lap before the stop (skip pit-on-grid / start-in-pit)
            if (cust, prev) not in laps_data:
                continue
            # green-flag stop: no caution on the pit laps or the lap before
            if prev in caution or any(l in caution for l in run):
                continue
            cycle_ms = (laps_data[(cust, out_lap)][1] - laps_data[(cust, prev)][1]) / 10.0
            n_pit_laps = len(run)
            in_lt = laps_data[(cust, in_lap)][0]
            out_lt = laps_data[(cust, out_lap)][0]
            stops.append({
                "cust": cust, "in_lap": in_lap, "out_lap": out_lap, "n_pit": n_pit_laps,
                "cycle_ms": cycle_ms,
                "time_lost_ms": cycle_ms - n_pit_laps * median_ms,
                "in_lt_ms": in_lt / 10.0 if in_lt > 0 else None,
                "out_lt_ms": out_lt / 10.0 if out_lt > 0 else None,
            })

    # window membership: how many distinct drivers pit within +/- WINDOW_LAPS
    in_laps = [(s["cust"], s["in_lap"]) for s in stops]
    for s in stops:
        lo, hi = s["in_lap"] - WINDOW_LAPS, s["in_lap"] + WINDOW_LAPS
        pitters = len({c for c, l in in_laps if lo <= l <= hi})
        s["window_pitters"] = pitters
        s["in_window"] = pitters >= MIN_FIELD_FRACTION * field_size

    # outliers: per-race Tukey rule on the green-window stops' time lost
    window_losses = [s["time_lost_ms"] for s in stops if s["in_window"]]
    if len(window_losses) >= 4:
        q1, _q2, q3 = statistics.quantiles(window_losses, n=4, method="inclusive")
        outlier_threshold = q3 + OUTLIER_IQR_MULT * (q3 - q1)
    else:
        outlier_threshold = float("inf")
    for s in stops:
        s["is_outlier"] = s["time_lost_ms"] > outlier_threshold

    rows = []
    by_cust = defaultdict(list)
    for s in stops:
        by_cust[s["cust"]].append(s)
    for cust, cust_stops in by_cust.items():
        for i, s in enumerate(sorted(cust_stops, key=lambda x: x["in_lap"]), start=1):
            rows.append((
                ss, cust, i, s["in_lap"], s["out_lap"], s["n_pit"],
                s["in_lt_ms"], s["out_lt_ms"], s["cycle_ms"], s["time_lost_ms"],
                s["window_pitters"], s["in_window"], s["is_outlier"],
            ))

    with conn.cursor() as cur:
        cur.execute("DELETE FROM pit_cycles WHERE subsession_id = %s", (ss,))
        cur.executemany(
            "INSERT INTO pit_cycles (subsession_id, cust_id, stop_num, in_lap, out_lap, "
            "n_pit_laps, in_lap_time_ms, out_lap_time_ms, cycle_time_ms, time_lost_ms, "
            "window_pitters, in_green_window, is_outlier) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            rows,
        )
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Derive green-flag pit-cycle times")
    ap.add_argument("subsessions", type=int, nargs="*",
                    help="subsession ids to rebuild (default: all with lap data)")
    args = ap.parse_args()

    with connection() as conn:
        ensure_tables(conn)
        targets = args.subsessions or _subsessions_with_laps(conn)
        for ss in targets:
            n = build_subsession(conn, ss)
            print(f"{ss}: {n} green pit cycles")


if __name__ == "__main__":
    main()