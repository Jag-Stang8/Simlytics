"""Build a per-driver feature vector for modeling (clustering, similarity, etc.).

Combines green-lap pace -- normalized to each race's median lap so tracks are
comparable, with a fitted skew-normal plus moments -- with results, passing
z-scores, and pit-cycle speed. Returns a pandas DataFrame keyed by driver.

    from stats.driver_features import build_features, green_lap_pace
    features = build_features()          # opens its own connection
    # or, to reuse the per-lap frame downstream:
    with connection() as conn:
        gl = green_lap_pace(conn)
        features = build_features(conn, gl=gl)

CLI preview: uv run python -m stats.driver_features
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sstats

from db.connection import connection

QUERIES = Path(__file__).resolve().parent.parent / "queries"
TRIM_QUANTILE = 0.95  # drop each driver's slow tail (traffic / incident laps)


def _run(conn, name: str, params=None) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute((QUERIES / name).read_text(), params)
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def green_lap_pace(conn) -> pd.DataFrame:
    """Green laps with pace as percent off the race median lap, slow tail trimmed."""
    green = _run(conn, "green_laps.sql")
    green["laptime_s"] = green["laptime"].astype(float) / 10000.0
    green["race_median"] = green.groupby("subsession_id")["laptime_s"].transform("median")
    green["pace_pct"] = (green["laptime_s"] / green["race_median"] - 1.0) * 100.0
    keep = green.groupby("cust_id")["pace_pct"].transform(
        lambda s: s <= s.quantile(TRIM_QUANTILE)
    )
    return green[keep].copy()


def pace_features(gl: pd.DataFrame) -> pd.DataFrame:
    """Per-driver pace distribution: fitted skew-normal parameters + moments."""
    recs = []
    for drv, s in gl.groupby("driver_name")["pace_pct"]:
        v = s.to_numpy()
        a, loc, scale = sstats.skewnorm.fit(v)
        recs.append({
            "driver_name": drv,
            "green_laps": v.size,
            "pace_pct_median": float(np.median(v)),
            "pace_pct_std": float(v.std(ddof=1)),
            "pace_pct_skew": float(sstats.skew(v)),
            "skewnorm_a": a,
            "skewnorm_loc": loc,
            "skewnorm_scale": scale,
        })
    return pd.DataFrame(recs)


def build_features(conn=None, gl: pd.DataFrame | None = None) -> pd.DataFrame:
    """Assemble the full per-driver feature vector. Opens a connection if none given."""
    if conn is not None:
        return _build(conn, gl)
    with connection() as c:
        return _build(c, gl)


def _build(conn, gl: pd.DataFrame | None) -> pd.DataFrame:
    if gl is None:
        gl = green_lap_pace(conn)
    pace = pace_features(gl)

    stand = _run(conn, "driver_standings.sql")[
        ["driver_name", "races", "avg_finish", "avg_start", "incidents"]
    ]
    score = _run(conn, "passing_score.sql")[
        ["driver_name", "z_net", "z_conv", "z_def", "z_restart", "passing_score"]
    ]
    pit = _run(conn, "pit_cycle_ranking.sql")[
        ["driver_name", "median_time_lost_s"]
    ].rename(columns={"median_time_lost_s": "pit_median_lost_s"})

    features = (
        pace.merge(stand, on="driver_name", how="left")
            .merge(score, on="driver_name", how="left")
            .merge(pit, on="driver_name", how="left")
    )
    for col in features.columns:
        if col != "driver_name":
            features[col] = pd.to_numeric(features[col], errors="coerce")
    features["incidents_per_race"] = features["incidents"] / features["races"]
    return features


def main() -> None:
    features = build_features()
    cols = ["driver_name", "green_laps", "pace_pct_median", "pace_pct_std",
            "pace_pct_skew", "avg_finish", "incidents_per_race", "passing_score",
            "pit_median_lost_s"]
    regs = features[features["green_laps"] >= 300][cols].sort_values("pace_pct_median")
    print(regs.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
