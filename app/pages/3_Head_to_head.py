"""Head-to-head — two drivers over the same range of races.

Re-slices frames the other pages already cache: driver_race_matrix.sql for the
metrics and driver_pair_passes.sql for the meetings. The Result tab writes `a`
when a row is clicked, so arriving from a race pre-fills the first driver.
"""

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import pandas as pd
import streamlit as st

from lib import charts, data, filters, fmt, metrics, theme

st.set_page_config(page_title="Head-to-head · Simlytics", page_icon="🏁", layout="wide")

theme.inject()

league_id, season_id, _ = filters.sidebar(show_rail=False)
if season_id is None:
    st.stop()

sessions = data.sessions(season_id=season_id)
picked, _mode = filters.range_picker(sessions)

matrix = data.run_sql("driver_race_matrix.sql", season_id=int(season_id))
scoped = matrix[matrix["subsession_id"].isin(picked)] if picked else matrix.iloc[0:0]

theme.topbar("Head-to-head", f"{len(picked)} races")
if scoped.empty:
    st.info("No races in the selected range.")
    st.stop()

agg = metrics.aggregate(scoped, min_races=1)
names = agg.sort_values("driver_name")["driver_name"].tolist()
by_cust = dict(zip(agg["cust_id"], agg["driver_name"]))


def _preselect(key: str, fallback_index: int) -> str:
    """Honour ?a=<cust_id> / ?b=<cust_id> from the Result tab's row click."""
    raw = st.query_params.get(key)
    if raw:
        try:
            name = by_cust.get(int(raw))
            if name in names:
                return name
        except (TypeError, ValueError):
            pass
    return names[min(fallback_index, len(names) - 1)]


c1, c2 = st.columns(2)
a_name = c1.selectbox("Driver A", names, index=names.index(_preselect("a", 0)))
b_name = c2.selectbox("Driver B", names, index=names.index(_preselect("b", 1)))

if a_name == b_name:
    st.info("Pick two different drivers.")
    st.stop()

a_row = agg[agg["driver_name"] == a_name].iloc[0]
b_row = agg[agg["driver_name"] == b_name].iloc[0]
st.query_params["a"] = str(int(a_row["cust_id"]))
st.query_params["b"] = str(int(b_row["cust_id"]))

theme.tiles([
    (f"{a_name} races", str(int(a_row["races"])), None),
    (f"{b_name} races", str(int(b_row["races"])), None),
])
st.write("")

# --- mirrored metric bars ----------------------------------------------------
COMPARE = ["Points", "Avg finish", "Wins", "Laps led", "Net passes",
           "Conversion %", "Defense %", "Pit Δ median", "Incidents"]

rows = []
for label in COMPARE:
    col, better, spec = metrics.CATALOG[label]
    av, bv = a_row.get(col), b_row.get(col)
    if pd.isna(av) and pd.isna(bv):
        continue
    field = pd.to_numeric(agg[col], errors="coerce")
    lo, hi = float(field.min()), float(field.max())
    span = (hi - lo) or 1.0

    def norm(v):
        if pd.isna(v):
            return 0.0
        frac = (float(v) - lo) / span
        # For "lower is better" metrics, flip so a longer bar always means better.
        return frac if better else 1.0 - frac

    def show(v):
        return "—" if pd.isna(v) else (spec % v).replace("%%", "%")

    rows.append({"metric": label, "a_norm": norm(av), "b_norm": norm(bv),
                 "a_label": show(av), "b_label": show(bv)})

bars = pd.DataFrame(rows)
left, right = st.columns([3, 2])

with left:
    st.markdown(theme.micro("Metric comparison"), unsafe_allow_html=True)
    st.caption("Bar length is normalized across the field; longer is always better. Values are printed at the tip.")
    st.altair_chart(charts.mirrored_bars(bars, a_name, b_name), width="stretch")

with right:
    st.markdown(theme.micro("Passing profile"), unsafe_allow_html=True)
    st.altair_chart(charts.radar(a_row, b_row, a_name, b_name), width="stretch")
    st.dataframe(
        pd.DataFrame({
            "Component": [lbl for _c, lbl in charts.RADAR_AXES],
            a_name: [round(float(a_row[c]), 2) for c, _l in charts.RADAR_AXES],
            b_name: [round(float(b_row[c]), 2) for c, _l in charts.RADAR_AXES],
        }),
        hide_index=True, width="stretch",
    )

st.divider()

# --- the field, with both highlighted ---------------------------------------
fl, fr = st.columns([4, 3])

with fl:
    st.markdown(theme.micro("Where they sit in the field"), unsafe_allow_html=True)
    axes = [lbl for lbl in metrics.CATALOG if lbl not in ("Races",)]
    x_lbl = st.selectbox("X", axes, index=axes.index("Avg finish"))
    y_lbl = st.selectbox("Y", axes, index=axes.index("Passing score"))
    xcol, _b, _f = metrics.CATALOG[x_lbl]
    ycol, _b2, _f2 = metrics.CATALOG[y_lbl]
    field = agg.rename(columns={xcol: "pace_pct_median", ycol: "pace_pct_std"})
    field = field.assign(green_laps=field["races"]).dropna(
        subset=["pace_pct_median", "pace_pct_std"]
    )
    scatter = charts.pace_scatter(field, [a_name, b_name])
    st.altair_chart(
        scatter.properties(title=f"{y_lbl} vs {x_lbl}"), width="stretch"
    )
    st.caption(f"X = {x_lbl}, Y = {y_lbl}. Both selected drivers are highlighted; the field is grey.")

with fr:
    st.markdown(theme.micro("Meetings"), unsafe_allow_html=True)
    pair = data.run_sql(
        "driver_pair_passes.sql",
        season_id=int(season_id),
        a=int(a_row["cust_id"]),
        b=int(b_row["cust_id"]),
    )
    pair = pair[pair["subsession_id"].isin(picked)]
    green_only = st.toggle("Green-flag passes only", value=True)
    view = pair[pair["is_green"]] if green_only else pair

    if view.empty:
        st.caption("No recorded passes between these two in this range.")
    else:
        a_over = int((view["direction"] == "a_over_b").sum())
        b_over = int((view["direction"] == "b_over_a").sum())
        m1, m2, m3 = st.columns(3)
        m1.metric(f"{a_name.split()[0]} past", a_over)
        m2.metric(f"{b_name.split()[0]} past", b_over)
        m3.metric("Net", f"{a_over - b_over:+d}", help=f"Positive favours {a_name}")
        st.dataframe(
            pd.DataFrame({
                "R": view["round"],
                "Track": view["track_name"],
                "Lap": view["lap_num"],
                "Pass": view["direction"].map(
                    {"a_over_b": f"{a_name} ▸ {b_name}", "b_over_a": f"{b_name} ▸ {a_name}"}
                ),
                "Reverted": view["reverted"],
            }).sort_values(["R", "Lap"]),
            hide_index=True, width="stretch", height=300,
        )
