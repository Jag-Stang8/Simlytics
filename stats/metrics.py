"""Range aggregation — pure pandas over the driver x race matrix.

`queries/driver_race_matrix.sql` returns only counts and raw values at
(subsession_id, cust_id) grain, so narrowing the range is a row filter and every
rate is recomputed by summing numerator and denominator over the surviving
races. Nothing here re-queries, which is why changing the range is instant.

Rates are computed from summed components, never averaged from per-race rates —
a driver with 40 opportunities in one race and 2 in another should not have those
races weighted equally.
"""

from __future__ import annotations

import pandas as pd

# label -> (column, higher_is_better, format)
CATALOG: dict[str, tuple[str, bool, str]] = {
    "Points":          ("points",            True,  "%d"),
    "Races":           ("races",             True,  "%d"),
    "Wins":            ("wins",              True,  "%d"),
    "Podiums":         ("podiums",           True,  "%d"),
    "Avg finish":      ("avg_finish",        False, "%.2f"),
    "Avg start":       ("avg_start",         False, "%.2f"),
    "Laps led":        ("laps_led",          True,  "%d"),
    "Incidents":       ("incidents",         False, "%d"),
    "Net passes":      ("net_passes",        True,  "%+d"),
    "Net per race":    ("net_per_race",      True,  "%+.2f"),
    "Conversion %":    ("conversion_pct",    True,  "%.1f%%"),
    "Defense %":       ("defense_pct",       True,  "%.1f%%"),
    "Restart net":     ("restart_net",       True,  "%+.2f"),
    "Pit Δ median":    ("pit_delta_s",       False, "%.1f s"),
    "Passing score":   ("passing_score",     True,  "%+.2f"),
}

# passing_score.sql's weights, kept in sync with it.
WEIGHTS = {"z_net": 0.35, "z_conv": 0.20, "z_def": 0.20, "z_restart": 0.25}


def aggregate(matrix: pd.DataFrame, min_races: int = 1) -> pd.DataFrame:
    """Collapse the per-race matrix to one row per driver."""
    if matrix.empty:
        return pd.DataFrame()

    g = matrix.groupby(["cust_id", "driver_name"], as_index=False)
    out = g.agg(
        races=("subsession_id", "nunique"),
        points=("league_points", "sum"),
        laps_led=("laps_led", "sum"),
        incidents=("incidents", "sum"),
        avg_finish=("finish", "mean"),
        avg_start=("start", "mean"),
        best_finish=("finish", "min"),
        passes_made=("passes_made", "sum"),
        passes_conceded=("passes_conceded", "sum"),
        opportunities=("opportunities", "sum"),
        conversions=("conversions", "sum"),
        faced=("faced", "sum"),
        defended=("defended", "sum"),
        restarts=("restarts", "sum"),
        restart_made=("restart_made", "sum"),
        restart_conceded=("restart_conceded", "sum"),
        pit_delta_s=("median_time_lost_ms", lambda s: s.median() / 1000),
    )
    wins = g.apply(lambda d: (d["finish"] == 1).sum(), include_groups=False)
    podiums = g.apply(lambda d: (d["finish"] <= 3).sum(), include_groups=False)
    out["wins"] = wins.iloc[:, -1].to_numpy()
    out["podiums"] = podiums.iloc[:, -1].to_numpy()

    out["net_passes"] = out["passes_made"] - out["passes_conceded"]
    out["net_per_race"] = out["net_passes"] / out["races"]
    out["conversion_pct"] = 100 * out["conversions"] / out["opportunities"].replace(0, pd.NA)
    out["defense_pct"] = 100 * out["defended"] / out["faced"].replace(0, pd.NA)
    out["restart_net"] = (
        out["restart_made"] - out["restart_conceded"]
    ) / out["restarts"].replace(0, pd.NA)

    out = out[out["races"] >= min_races].copy()
    return _score(out)


def _score(df: pd.DataFrame) -> pd.DataFrame:
    """z-score the four passing components and blend them.

    Mirrors passing_score.sql: a missing component scores neutral (filled with
    the field mean before standardizing, so its z is 0).
    """
    pairs = {
        "z_net": "net_per_race",
        "z_conv": "conversion_pct",
        "z_def": "defense_pct",
        "z_restart": "restart_net",
    }
    for z, col in pairs.items():
        series = pd.to_numeric(df[col], errors="coerce")
        filled = series.fillna(series.mean())
        sd = filled.std(ddof=1)
        df[z] = 0.0 if not sd or pd.isna(sd) else (filled - filled.mean()) / sd
    df["passing_score"] = sum(df[z] * w for z, w in WEIGHTS.items())
    return df


def progression(matrix: pd.DataFrame) -> pd.DataFrame:
    """Cumulative points by round, within the selected range."""
    if matrix.empty:
        return pd.DataFrame(columns=["driver_name", "round", "cumulative_points"])
    m = matrix.sort_values("round")
    m = m.assign(
        cumulative_points=m.groupby("cust_id")["league_points"].cumsum()
    )
    return m[["cust_id", "driver_name", "round", "league_points", "cumulative_points"]]
