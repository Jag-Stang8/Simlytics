"""FastAPI + Jinja spike: the Session view, ported from the mockup's own markup.

Run:  uv run uvicorn web.main:app --reload --port 8000

The point of the spike is fidelity — templates/session.html is the 2a mockup
with its inline styles lifted into static/app.css and its rows driven by real
data. Nothing here imports Streamlit.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app.lib import charts, fmt, metrics  # noqa: E402  — none import Streamlit
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


# --- season-wide pages ------------------------------------------------------

DEFAULT_METRICS = ["Points", "Avg finish", "Net passes", "Conversion %",
                   "Defense %", "Pit Δ median", "Passing score"]


def _scoped(season_id: int, r_from: int | None, r_to: int | None):
    """The driver x race matrix, sliced to a round range. Never re-queries per
    metric — the matrix holds counts, so a range is a row filter (see CLAUDE.md).
    """
    import pandas as pd

    matrix = pd.DataFrame(data.rows("driver_race_matrix.sql", season_id=season_id))
    if matrix.empty:
        return matrix, matrix, 1, 1
    lo_all, hi_all = int(matrix["round"].min()), int(matrix["round"].max())
    lo = lo_all if r_from is None else max(lo_all, r_from)
    hi = hi_all if r_to is None else min(hi_all, r_to)
    if lo > hi:
        lo, hi = lo_all, hi_all
    scoped = matrix[matrix["round"].between(lo, hi)]
    return matrix, scoped, lo, hi


@app.get("/season")
def season_page(request: Request, season_id: int | None = None,
                r_from: int | None = None, r_to: int | None = None,
                m: list[str] | None = Query(default=None)):
    seasons = data.rows("season_list.sql", league_id=None)
    if not seasons:
        return RedirectResponse("/")
    season = next((s for s in seasons if s["season_id"] == season_id), seasons[0])
    sid = season["season_id"]

    matrix, scoped, lo, hi = _scoped(sid, r_from, r_to)
    if scoped.empty:
        return RedirectResponse("/")

    chosen = [x for x in (m or DEFAULT_METRICS) if x in metrics.CATALOG] or DEFAULT_METRICS
    agg = metrics.aggregate(scoped, min_races=1)

    sort_col, better, _f = metrics.CATALOG[chosen[0]]
    agg = agg.sort_values(sort_col, ascending=not better)

    cols = []
    for label in chosen:
        col, good_high, spec = metrics.CATALOG[label]
        cols.append({"label": label, "col": col, "spec": spec, "high": good_high})

    rows = []
    for rank, rec in enumerate(agg.to_dict("records"), start=1):
        cells = []
        for c in cols:
            v = rec.get(c["col"])
            cells.append({
                "text": "—" if v is None or v != v else (c["spec"] % v).replace("%%", "%"),
                "cls": "gain" if (c["col"] == "net_passes" and v and v > 0)
                       else "loss" if (c["col"] == "net_passes" and v and v < 0) else "",
            })
        rows.append({"rank": rank, "name": rec["driver_name"],
                     "cust_id": rec["cust_id"], "cells": cells})

    # finish-position heatmap, best drivers x rounds
    top = [r["cust_id"] for r in rows[:8]]
    rounds = sorted(scoped["round"].unique().tolist())
    finishes = {
        (int(r["cust_id"]), int(r["round"])): int(r["finish"])
        for r in scoped.to_dict("records")
    }
    field = int(scoped["finish"].max() or 1)
    heat = []
    for r in rows[:8]:
        cells = []
        for rd in rounds:
            f = finishes.get((int(r["cust_id"]), rd))
            # one hue, dark = good; blank where the driver did not start
            alpha = 0 if f is None else 0.15 + 0.65 * (1 - (f - 1) / max(field - 1, 1))
            cells.append({"v": f, "alpha": alpha})
        heat.append({"name": r["name"], "cells": cells})

    prog = metrics.progression(scoped)
    leaders = [r["cust_id"] for r in rows[:5]]
    series = []
    for i, cust in enumerate(leaders):
        pts = prog[prog["cust_id"] == cust].sort_values("round")
        series.append({
            "name": next(r["name"] for r in rows if r["cust_id"] == cust),
            "color": fmt.HIGHLIGHT[i],
            "points": list(zip(pts["round"].tolist(),
                               pts["cumulative_points"].tolist())),
        })
    peak = max((p[1] for s in series for p in s["points"]), default=1) or 1

    all_rounds = sorted(matrix["round"].unique().tolist())
    field_size = {
        int(rd): int((matrix["round"] == rd).sum()) for rd in all_rounds
    }
    biggest = max(field_size.values(), default=1) or 1

    return templates.TemplateResponse(
        request=request, name="season.html",
        context={
            "season": season, "seasons": seasons,
            "rows": rows, "cols": cols, "chosen": chosen,
            "catalog": list(metrics.CATALOG),
            "lo": lo, "hi": hi, "all_rounds": all_rounds,
            "field_size": field_size, "biggest": biggest,
            "rounds": rounds, "heat": heat,
            "series": series, "peak": peak,
            "drivers": len(rows), "races": len(rounds),
        },
    )


@app.get("/h2h")
def h2h_page(request: Request, season_id: int | None = None,
             a: int | None = None, b: int | None = None,
             r_from: int | None = None, r_to: int | None = None):
    seasons = data.rows("season_list.sql", league_id=None)
    if not seasons:
        return RedirectResponse("/")
    season = next((s for s in seasons if s["season_id"] == season_id), seasons[0])
    sid = season["season_id"]

    _matrix, scoped, lo, hi = _scoped(sid, r_from, r_to)
    if scoped.empty:
        return RedirectResponse("/")

    agg = metrics.aggregate(scoped, min_races=1).sort_values("points", ascending=False)
    people = agg.to_dict("records")
    by_id = {int(p["cust_id"]): p for p in people}
    a_row = by_id.get(a) or people[0]
    b_row = by_id.get(b) or next((p for p in people if p is not a_row), people[0])

    compare = ["Points", "Wins", "Avg finish", "Laps led", "Net passes",
               "Conversion %", "Defense %", "Pit Δ median", "Incidents"]
    bars = []
    for label in compare:
        col, good_high, spec = metrics.CATALOG[label]
        av, bv = a_row.get(col), b_row.get(col)
        if (av is None or av != av) and (bv is None or bv != bv):
            continue
        pair = [x for x in (av, bv) if x is not None and x == x]
        widest = max(abs(float(x)) for x in pair) or 1.0

        def width(v):
            return 0 if v is None or v != v else abs(float(v)) / widest * 100

        def show(v):
            return "—" if v is None or v != v else (spec % v).replace("%%", "%")

        bars.append({"label": label, "a": show(av), "b": show(bv),
                     "aw": width(av), "bw": width(bv)})

    pair_rows = data.rows("driver_pair_passes.sql", season_id=sid,
                          a=int(a_row["cust_id"]), b=int(b_row["cust_id"]))
    keep = [r for r in pair_rows if lo <= r["round"] <= hi and r["is_green"]]
    a_over = sum(1 for r in keep if r["direction"] == "a_over_b")
    b_over = len(keep) - a_over
    total = max(a_over + b_over, 1)

    return templates.TemplateResponse(
        request=request, name="h2h.html",
        context={
            "season": season, "a": a_row, "b": b_row, "people": people,
            "bars": bars, "lo": lo, "hi": hi,
            "a_over": a_over, "b_over": b_over,
            "a_pct": a_over / total * 100, "b_pct": b_over / total * 100,
            "meetings": len(keep),
        },
    )
