"""Time frame — pick a range of races, pick metrics, compare drivers across them.

One query (`driver_race_matrix.sql`, cached per season) backs the whole page;
the range picker slices it in pandas, so changing the range never re-queries.
"""

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import pandas as pd
import streamlit as st

from lib import charts, data, filters, fmt, metrics, theme

st.set_page_config(page_title="Time frame · Simlytics", page_icon="🏁", layout="wide")

theme.inject()

league_id, season_id, _ = filters.sidebar(show_rail=False)
if season_id is None:
    st.stop()

sessions = data.sessions(season_id=season_id)
picked, mode = filters.range_picker(sessions)

matrix = data.run_sql("driver_race_matrix.sql", season_id=int(season_id))
scoped = matrix[matrix["subsession_id"].isin(picked)] if picked else matrix.iloc[0:0]

theme.topbar(
    "Time frame",
    f"{len(picked)} races · "
    f"{scoped['cust_id'].nunique() if not scoped.empty else 0} drivers",
)

if scoped.empty:
    st.info("No races in the selected range.")
    st.stop()

# --- options ----------------------------------------------------------------
o1, o2, o3 = st.columns([2, 2, 3])
min_races = o1.number_input(
    "Min races to qualify", min_value=1, max_value=len(picked), value=min(3, len(picked)),
    help="Small samples distort the z-scored passing metrics.",
)
default_metrics = ["Points", "Avg finish", "Net passes", "Conversion %", "Pit Δ median"]
chosen = o3.multiselect(
    "Metrics", list(metrics.CATALOG), default=default_metrics
)

agg = metrics.aggregate(scoped, min_races=int(min_races))
if agg.empty:
    st.info("No driver meets the minimum race count for this range.")
    st.stop()

# --- table ------------------------------------------------------------------
table = pd.DataFrame({"Driver": agg["driver_name"]})
for label in chosen:
    col, _better, _fmt = metrics.CATALOG[label]
    table[label] = agg[col]

sort_by = chosen[0] if chosen else None
if sort_by:
    _, better, _ = metrics.CATALOG[sort_by]
    table = table.sort_values(sort_by, ascending=not better)

st.dataframe(
    table,
    hide_index=True,
    width="stretch",
    column_config={
        label: st.column_config.NumberColumn(label, format=metrics.CATALOG[label][2])
        for label in chosen
    },
)

st.divider()

# --- heatmap + progression --------------------------------------------------
left, right = st.columns([3, 4])

with left:
    st.markdown(theme.micro("Driver × round"), unsafe_allow_html=True)
    heat_options = {
        "Points": ("league_points", False),
        "Finish": ("finish", True),
        "Net passes": ("net_passes", False),
        "Laps led": ("laps_led", False),
        "Incidents": ("incidents", True),
    }
    heat_metric = st.selectbox("Cell value", list(heat_options), label_visibility="collapsed")
    col, reverse = heat_options[heat_metric]
    keep = scoped[scoped["cust_id"].isin(agg["cust_id"])]
    st.altair_chart(
        charts.driver_round_heatmap(keep, col, heat_metric, reverse=reverse),
        width="stretch",
    )

with right:
    st.markdown(theme.micro("Points progression"), unsafe_allow_html=True)
    prog = metrics.progression(scoped)
    prog = prog[prog["cust_id"].isin(agg["cust_id"])]
    leaders = (
        agg.sort_values("points", ascending=False)["driver_name"].head(5).tolist()
    )
    highlight = st.multiselect(
        "Highlight", sorted(agg["driver_name"]), default=leaders, max_selections=8,
        help="The field stays grey — hue cannot carry 40 identities.",
    )
    st.altair_chart(
        charts.points_progression(prog, highlight), width="stretch"
    )
