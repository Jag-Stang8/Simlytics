"""FastAPI + Jinja spike: the Session view, ported from the mockup's own markup.

Run:  uv run uvicorn web.main:app --reload --port 8000

The point of the spike is fidelity — templates/session.html is the 2a mockup
with its inline styles lifted into static/app.css and its rows driven by real
data. Nothing here imports Streamlit.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app.lib import charts, fmt  # noqa: E402  — neither imports Streamlit
from web import data  # noqa: E402

app = FastAPI(title="simlytics")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

templates.env.filters["laptime"] = fmt.laptime
templates.env.filters["race_date"] = fmt.race_date
templates.env.filters["track"] = lambda r: fmt.track_label(
    r["track_name"], r["track_config_name"]
)


def _sessions(season_id: int | None = None) -> list[dict]:
    return data.rows("session_list.sql", season_id=season_id)


@app.get("/")
def index():
    sessions = _sessions()
    if not sessions:
        return {"detail": "no races ingested"}
    newest = max(sessions, key=lambda s: s["round"])
    return RedirectResponse(f"/session/{newest['subsession_id']}")


def _contiguous(laps: list[int]) -> list[tuple[int, int]]:
    """[8,9,10,20] -> [(8,10),(20,20)] — inclusive caution runs."""
    spans: list[list[int]] = []
    for lap in sorted(laps):
        if spans and lap == spans[-1][1] + 1:
            spans[-1][1] = lap
        else:
            spans.append([lap, lap])
    return [(a, b) for a, b in spans]


def _flag_gradient(caution: list[int], first: int, last: int) -> str:
    """The mockup's flag strip, as one CSS linear-gradient across the race."""
    span = max(last - first + 1, 1)
    green, yellow = "oklch(0.55 0.13 152 / .45)", "oklch(0.82 0.13 78 / .5)"
    stops, cursor = [], 0.0
    for a, b in _contiguous(caution):
        start = (a - first) / span * 100
        end = (b - first + 1) / span * 100
        if start > cursor:
            stops.append(f"{green} {cursor:.2f}% {start:.2f}%")
        stops.append(f"{yellow} {start:.2f}% {end:.2f}%")
        cursor = end
    if cursor < 100:
        stops.append(f"{green} {cursor:.2f}% 100%")
    return "linear-gradient(90deg," + ",".join(stops) + ")"


def _timeline(subsession_id: int, race: dict, lap: int | None):
    running = data.rows("race_running_order.sql", subsession_id=subsession_id)
    if not running:
        return None

    laps = sorted({r["lap_num"] for r in running})
    caution = sorted({r["lap_num"] for r in running if r["under_caution"]})
    lap = lap if lap in laps else laps[-1]

    # Leaders get the highlight slots; the rest of the field stays grey.
    finish_order = [
        r["driver_name"]
        for r in sorted(
            (r for r in running if r["lap_num"] == laps[-1]),
            key=lambda r: r["position"],
        )
    ]
    highlight = finish_order[:5]

    import pandas as pd

    # The spec references the data by URL rather than inlining thousands of lap
    # rows — see charts.position_by_lap's data_url argument.
    spec = charts.position_by_lap(
        pd.DataFrame(running), highlight, caution,
        data_url=f"/api/session/{subsession_id}/running.json",
    ).to_dict()

    order = sorted(
        (r for r in running if r["lap_num"] == lap), key=lambda r: r["position"]
    )
    for r in order:
        # "close" = inside 1% of the median lap, the opportunity threshold used
        # by passing_score.sql and driver_race_matrix.sql.
        r["close"] = r["gap_pct"] is not None and 0 < r["gap_pct"] < 0.01
        r["gap_display"] = "—" if r["gap_ms"] is None else f"{r['gap_ms'] / 1000:+.2f}"

    events = data.rows("race_events.sql", subsession_id=subsession_id)
    lo, hi = max(laps[0], lap - 3), lap + 3
    feed = [e for e in events if lo <= e["lap_num"] <= hi]
    feed = [e for e in feed if e["kind"] != "pass"][:14] or feed[:14]

    return {
        "spec": spec,
        "lap": lap,
        "laps": laps,
        "first_lap": laps[0],
        "last_lap": laps[-1],
        "under_caution": lap in caution,
        "caution_runs": _contiguous(caution),
        "flag_css": _flag_gradient(caution, laps[0], laps[-1]),
        "cursor_pct": (lap - laps[0]) / max(laps[-1] - laps[0], 1) * 100,
        "order": order,
        "feed": feed,
        "feed_lo": lo,
        "feed_hi": hi,
        "highlight": highlight,
    }


def _passing(subsession_id: int, top: int = 8):
    matrix = data.rows("race_pass_matrix.sql", subsession_id=subsession_id)
    by_flag = data.rows("race_passing_by_flag.sql", subsession_id=subsession_id)
    if not by_flag:
        return None

    # A 28x28 grid is unreadable; the mockup shows a corner. Take the drivers
    # most involved in passing, by total passes made plus conceded.
    involved: dict[str, int] = {}
    for m in matrix:
        involved[m["passer_name"]] = involved.get(m["passer_name"], 0) + m["passes"]
        involved[m["passed_name"]] = involved.get(m["passed_name"], 0) + m["passes"]
    names = [n for n, _ in sorted(involved.items(), key=lambda kv: -kv[1])[:top]]
    lookup = {(m["passer_name"], m["passed_name"]): m["passes"] for m in matrix}
    peak = max(lookup.values(), default=1)

    grid = []
    for row in names:
        cells = []
        for col in names:
            n = lookup.get((row, col), 0)
            cells.append({
                "n": n, "self": row == col,
                # one hue, light -> dark: opacity carries magnitude
                "alpha": 0 if not n else 0.12 + 0.68 * (n / peak),
            })
        grid.append({"name": row, "cells": cells})

    flags = sorted(by_flag, key=lambda r: -r["total_made"])[:12]
    widest = max((r["total_made"] for r in flags), default=1) or 1
    for r in flags:
        r["pct"] = {k: 100 * r[f"made_{k}"] / widest for k in ("green", "pit", "caution")}

    # conversion / defense, from the matrix query's own counts
    season_rows = data.rows("driver_race_matrix.sql", season_id=None)
    race_rows = [r for r in season_rows if r["subsession_id"] == subsession_id]
    conv = []
    for r in race_rows:
        if r["opportunities"]:
            conv.append({
                "name": r["driver_name"],
                "opps": r["opportunities"],
                "conv": r["conversions"],
                "rate": 100 * r["conversions"] / r["opportunities"],
                "faced": r["faced"],
                "defense": (100 * r["defended"] / r["faced"]) if r["faced"] else None,
            })
    conv.sort(key=lambda r: -r["rate"])

    return {"names": names, "grid": grid, "flags": flags,
            "conv": conv[:12], "total": sum(m["passes"] for m in matrix)}


def _pit(subsession_id: int, show_outliers: bool = False):
    stops = data.rows("race_pit_cycles.sql", subsession_id=subsession_id)
    if not stops:
        return None
    shown = stops if show_outliers else [s for s in stops if not s["is_outlier"]]
    if not shown:
        return {"empty": True, "hidden": len(stops), "show_outliers": show_outliers}

    lo = min(s["in_lap"] for s in shown)
    hi = max(s["out_lap"] for s in shown)
    span = max(hi - lo + 1, 1)

    by_driver: dict[str, list] = {}
    for s in shown:
        s["left"] = (s["in_lap"] - lo) / span * 100
        s["width"] = max((s["out_lap"] - s["in_lap"] + 1) / span * 100, 1.5)
        s["lost_s"] = s["time_lost_ms"] / 1000
        by_driver.setdefault(s["driver_name"], []).append(s)

    rows = sorted(
        ({"name": n, "stops": v,
          "median": sorted(x["lost_s"] for x in v)[len(v) // 2]}
         for n, v in by_driver.items()),
        key=lambda r: r["median"],
    )
    return {
        "rows": rows, "lo": lo, "hi": hi,
        "count": len(shown), "outliers": sum(1 for s in stops if s["is_outlier"]),
        "show_outliers": show_outliers, "empty": False,
        "window": f"L{lo}–L{hi}",
    }


def _pace(subsession_id: int, top: int = 14):
    green = data.rows("green_laps.sql", subsession_id=subsession_id)
    if not green:
        return None
    import pandas as pd

    df = pd.DataFrame(green)
    df["laptime_s"] = df["laptime"].astype(float) / 10000.0
    median = float(df["laptime_s"].median())
    df["pace_pct"] = (df["laptime_s"] / median - 1.0) * 100.0

    stats = charts.pace_box_stats(df).sort_values("median")
    rows = stats.head(top).to_dict("records")

    lo = min(r["lo"] for r in rows)
    hi = max(r["hi"] for r in rows)
    span = (hi - lo) or 1.0

    def pos(v: float) -> float:
        return (v - lo) / span * 100

    for r in rows:
        r["l_lo"], r["l_hi"] = pos(r["lo"]), pos(r["hi"])
        r["l_q1"], r["l_q3"] = pos(r["q1"]), pos(r["q3"])
        r["l_med"] = pos(r["median"])
    return {
        "rows": rows, "lo": lo, "hi": hi,
        "zero": pos(0.0) if lo <= 0 <= hi else None,
        "median_lap": median * 10000,
        "green_laps": len(df), "drivers": len(stats),
    }


@app.get("/api/session/{subsession_id}/running.json")
def running_json(subsession_id: int):
    """Chart data for the position lines — only the columns the spec encodes."""
    rows = data.rows("race_running_order.sql", subsession_id=subsession_id)
    return [
        {"lap_num": r["lap_num"], "position": r["position"],
         "driver_name": r["driver_name"]}
        for r in rows
    ]


@app.get("/session/{subsession_id}")
def session(request: Request, subsession_id: int, tab: str = "result",
            lap: int | None = None, outliers: int = 0):
    sessions = _sessions()
    race = next((s for s in sessions if s["subsession_id"] == subsession_id), None)
    if race is None:
        return RedirectResponse("/")

    season_sessions = [s for s in sessions if s["season_id"] == race["season_id"]]
    season = data.one("season_list.sql", league_id=None) or {}
    result = data.rows("race_result.sql", subsession_id=subsession_id)

    # NET+/- gets a direction colour, as the mockup draws it.
    for r in result:
        r["net_class"] = (
            "gain" if r["net_passes"] > 0 else "loss" if r["net_passes"] < 0 else "flat"
        )
        r["pit_display"] = (
            "—" if r["median_time_lost_ms"] is None
            else f"{r['median_time_lost_ms'] / 1000:.1f}"
        )

    timeline = _timeline(subsession_id, race, lap) if tab == "timeline" else None
    passing = _passing(subsession_id) if tab == "passing" else None
    pit = _pit(subsession_id, bool(outliers)) if tab == "pit" else None
    pace = _pace(subsession_id) if tab == "pace" else None

    return templates.TemplateResponse(
        request=request,
        name="session.html",
        context={
            "race": race,
            "season": season,
            "sessions": sorted(season_sessions, key=lambda s: -s["round"]),
            "result": result,
            "tab": tab,
            "tl": timeline,
            "pass_": passing,
            "pit": pit,
            "pace": pace,
        },
    )
