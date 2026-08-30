"""Session home — one race, five tabs.

Only the Result tab is built (spec build order step 02); the rest are stubs that
name the step that fills them, so the shell is navigable without pretending to
have data it doesn't.
"""

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import pandas as pd
import streamlit as st

from lib import charts, data, filters, fmt

st.set_page_config(page_title="Session · Simlytics", page_icon="🏁", layout="wide")

league_id, season_id, subsession_id = filters.sidebar()

if subsession_id is None:
    st.info("Pick a race from the season rail.")
    st.stop()

sessions = data.sessions(season_id=season_id).set_index("subsession_id")
if subsession_id not in sessions.index:
    st.warning("That race is not in the selected season.")
    st.stop()

race = sessions.loc[subsession_id]

# --- header -----------------------------------------------------------------
st.markdown(f"### Round {race['round']} · {fmt.track_label(race['track_name'], race['track_config_name'])}")
st.markdown(
    f"<div style='color:{fmt.MUTED};font-size:0.9rem;margin-top:-0.6rem'>"
    f"{race['season_name']} · {fmt.race_date(race['start_time'], 'long')} · "
    f"subsession {subsession_id}</div>",
    unsafe_allow_html=True,
)
st.write("")

m = st.columns(5)
m[0].metric("Laps", int(race["laps_completed"]))
m[1].metric("SOF", fmt.compact(race["sof"]))
m[2].metric("Cautions", int(race["num_cautions"]), f"{int(race['num_caution_laps'])} laps")
m[3].metric("Green passes", fmt.compact(race["green_passes"]))
m[4].metric("Lead changes", int(race["num_lead_changes"]))

st.divider()

tab_result, tab_timeline, tab_passing, tab_pit, tab_pace = st.tabs(
    ["Result", "Timeline", "Passing", "Pit cycles", "Pace"]
)

with tab_result:
    result = data.run_sql("race_result.sql", subsession_id=int(subsession_id))

    view = pd.DataFrame(
        {
            "Pos": result["finish"],
            "Car": result["car_num"],
            "Driver": result["driver_name"],
            "Start": result["start"],
            "+/-": result["pos_gain"],
            "Laps": result["laps_completed"],
            "Led": result["laps_led"],
            "Pts": result["league_points"],
            "Inc": result["incidents"],
            "Best": result["best_lap_time"].map(fmt.laptime),
            "Net passes": result["net_passes"],
            "Pit Δ": result["median_time_lost_ms"] / 1000,
            "Status": result["reason_out"],
        }
    )

    pit_max = float(view["Pit Δ"].max()) if view["Pit Δ"].notna().any() else 1.0

    event = st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "+/-": st.column_config.NumberColumn(
                "+/-", help="Places gained; positive is a net gain", format="%+d"
            ),
            "Net passes": st.column_config.NumberColumn(
                help="Green passes made minus conceded", format="%+d"
            ),
            "Pit Δ": st.column_config.ProgressColumn(
                "Pit Δ",
                help="Median green pit-cycle time lost vs the median lap "
                     "(green-window stops, outliers excluded). Blank = no green stop.",
                format="%.1f s",
                min_value=0,
                max_value=pit_max,
            ),
        },
    )

    # st.dataframe's selection object shape is version-sensitive and AppTest
    # cannot drive it, so read it defensively.
    selection = getattr(event, "selection", None) if event is not None else None
    rows = list(selection.get("rows", []) or []) if selection else []
    if rows:
        picked = result.iloc[rows[0]]
        st.session_state["a"] = int(picked["cust_id"])
        st.query_params["a"] = str(int(picked["cust_id"]))
        st.caption(
            f"Selected {picked['driver_name']} — P{int(picked['finish'])} from "
            f"P{int(picked['start'])}, {int(picked['passes_made'])} passes made / "
            f"{int(picked['passes_conceded'])} conceded."
        )
        if st.button(f"Compare {picked['driver_name']} →", key="to_h2h"):
            st.switch_page("pages/3_Head_to_head.py")

with tab_timeline:
    running = data.run_sql("race_running_order.sql", subsession_id=int(subsession_id))
    events = data.run_sql("race_events.sql", subsession_id=int(subsession_id))

    if running.empty:
        st.info("No lap data ingested for this race.")
    else:
        caution_laps = sorted(
            running.loc[running["under_caution"], "lap_num"].unique().tolist()
        )
        finishers = (
            running[running["lap_num"] == running["lap_num"].max()]
            .sort_values("position")["driver_name"].tolist()
        )

        c1, c2 = st.columns([3, 2])
        highlight = c1.multiselect(
            "Highlight drivers",
            sorted(running["driver_name"].unique()),
            default=finishers[:5],
            max_selections=8,
            help="The field stays grey — hue cannot carry a 40-car running order.",
        )
        laps = sorted(running["lap_num"].unique().tolist())
        lap = c2.select_slider(
            "Lap", options=laps, value=st.session_state.get("lap") or laps[-1]
        )
        st.session_state["lap"] = int(lap)
        st.query_params["lap"] = str(int(lap))

        chart = charts.position_by_lap(running, highlight, caution_laps)
        selection = st.altair_chart(chart, width="stretch", on_select="rerun")

        # A click on the chart wins over the slider for the next rerun.
        picked = None
        try:
            points = selection["selection"]["lap"]
            if points:
                picked = int(points[0]["lap_num"])
        except (KeyError, IndexError, TypeError):
            picked = None
        if picked is not None and picked != lap:
            st.session_state["lap"] = picked
            st.query_params["lap"] = str(picked)
            st.rerun()

        if caution_laps:
            st.caption(
                f"{len(charts._contiguous(caution_laps))} caution period(s), "
                f"{len(caution_laps)} laps shaded. Cautions are derived "
                "(stats/passes.py flags a lap whose median exceeds the race median "
                f"by 1.4x); race_summary reports {int(race['num_caution_laps'])} "
                "caution laps for this race."
            )

        st.divider()
        left, right = st.columns([3, 4])

        with left:
            st.markdown(f"**Running order — lap {lap}**")
            order = running[running["lap_num"] == lap].sort_values("position")
            st.dataframe(
                pd.DataFrame({
                    "Pos": order["position"],
                    "Car": order["car_num"],
                    "Driver": order["driver_name"],
                    "Gap": order["gap_ms"].map(
                        lambda v: "—" if pd.isna(v) else f"{v / 1000:.2f} s"
                    ),
                    "Lap": order["laptime"].map(fmt.laptime),
                }),
                hide_index=True, width="stretch", height=420,
            )

        with right:
            st.markdown("**Event feed**")
            kinds = st.multiselect(
                "Kinds",
                ["pass", "lead_change", "pit", "caution", "restart"],
                default=["lead_change", "pit", "caution", "restart"],
                label_visibility="collapsed",
            )
            window = events[
                events["kind"].isin(kinds)
                & events["lap_num"].between(max(laps[0], lap - 3), lap + 3)
            ]
            if window.empty:
                st.caption("Nothing of those kinds within 3 laps of this one.")
            else:
                st.dataframe(
                    pd.DataFrame({
                        "Lap": window["lap_num"],
                        "Event": window["kind"],
                        "Driver": window["driver_name"].fillna("—"),
                        "On": window["other_driver_name"].fillna("—"),
                        "Note": window["detail"].fillna(""),
                    }),
                    hide_index=True, width="stretch", height=380,
                )


with tab_passing:
    matrix = data.run_sql("race_pass_matrix.sql", subsession_id=int(subsession_id))
    by_flag = data.run_sql("race_passing_by_flag.sql", subsession_id=int(subsession_id))

    if matrix.empty:
        st.info("No pass data for this race — its lap chart has not been ingested.")
    else:
        pc1, pc2 = st.columns([4, 3])
        with pc1:
            st.markdown("**Who passed whom**")
            st.altair_chart(charts.pass_matrix(matrix), width="stretch")
        with pc2:
            direction = st.radio(
                "Direction", ["made", "conceded"], horizontal=True,
                label_visibility="collapsed",
            )
            st.altair_chart(charts.passing_by_flag(by_flag, direction), width="stretch")

        st.divider()
        st.markdown("**Opportunity conversion and restarts**")
        race_rows = data.run_sql(
            "driver_race_matrix.sql", season_id=int(season_id)
        )
        race_rows = race_rows[race_rows["subsession_id"] == subsession_id]
        conv = pd.DataFrame({
            "Driver": race_rows["driver_name"],
            "Opportunities": race_rows["opportunities"],
            "Converted": race_rows["conversions"],
            "Conversion %": 100 * race_rows["conversions"] / race_rows["opportunities"].replace(0, pd.NA),
            "Faced": race_rows["faced"],
            "Defended": race_rows["defended"],
            "Defense %": 100 * race_rows["defended"] / race_rows["faced"].replace(0, pd.NA),
            "Restarts": race_rows["restarts"],
            "Restart net": race_rows["restart_made"] - race_rows["restart_conceded"],
        }).sort_values("Conversion %", ascending=False)
        st.dataframe(
            conv, hide_index=True, width="stretch",
            column_config={
                "Conversion %": st.column_config.NumberColumn(format="%.1f%%"),
                "Defense %": st.column_config.NumberColumn(format="%.1f%%"),
                "Restart net": st.column_config.NumberColumn(format="%+d"),
            },
        )


with tab_pit:
    stops = data.run_sql("race_pit_cycles.sql", subsession_id=int(subsession_id))
    if stops.empty:
        st.info("No green-window pit stops recorded for this race.")
    else:
        show_outliers = st.toggle(
            "Show outliers", value=False,
            help="Outliers are per-race Tukey Q3+3*IQR on time lost — repair, "
                 "stall or penalty stops. Masked client-side, no re-query.",
        )
        view = stops if show_outliers else stops[~stops["is_outlier"]]
        if view.empty:
            st.info("Every stop in this race is flagged as an outlier.")
        else:
            strip = view.assign(
                out_lap_end=view["out_lap"] + 1,
                time_lost_s=view["time_lost_ms"] / 1000,
                cycle_s=view["cycle_time_ms"] / 1000,
            )
            st.altair_chart(charts.pit_window_strip(strip), width="stretch")
            st.dataframe(
                pd.DataFrame({
                    "Driver": view["driver_name"],
                    "Stop": view["stop_num"],
                    "In": view["in_lap"],
                    "Out": view["out_lap"],
                    "Cycle": (view["cycle_time_ms"] / 1000).round(2),
                    "Time lost": (view["time_lost_ms"] / 1000).round(2),
                    "Outlier": view["is_outlier"],
                }).sort_values("Time lost"),
                hide_index=True, width="stretch",
            )


with tab_pace:
    green = data.run_sql("green_laps.sql", subsession_id=int(subsession_id))
    if green.empty:
        st.info("No green laps for this race — its lap chart has not been ingested.")
    else:
        green = green.assign(laptime_s=green["laptime"].astype(float) / 10000.0)
        median = green["laptime_s"].median()
        green = green.assign(pace_pct=(green["laptime_s"] / median - 1.0) * 100.0)

        summary = (
            green.groupby("driver_name")
            .agg(pace_pct_median=("pace_pct", "median"),
                 pace_pct_std=("pace_pct", "std"),
                 green_laps=("pace_pct", "size"))
            .reset_index()
            .dropna(subset=["pace_pct_std"])
        )
        fastest = summary.sort_values("pace_pct_median")["driver_name"].head(5).tolist()
        picked_pace = st.multiselect(
            "Highlight", sorted(summary["driver_name"]), default=fastest,
            max_selections=8,
        )
        st.caption(
            f"Race median green lap {fmt.laptime(median * 10000)} — every value below "
            "is percent off that."
        )
        g1, g2 = st.columns([3, 4])
        with g1:
            st.markdown("**Pace distribution**")
            st.altair_chart(
                charts.pace_box(charts.pace_box_stats(green), picked_pace),
                width="stretch",
            )
        with g2:
            st.markdown("**Consistency — median vs spread**")
            st.altair_chart(charts.pace_scatter(summary, picked_pace), width="stretch")
