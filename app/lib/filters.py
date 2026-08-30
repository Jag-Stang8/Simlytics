"""The sidebar: league -> season -> season rail.

Defined once here and imported by every page, so the selection block is
identical everywhere. Every selection lives in `st.query_params` as well as
`st.session_state`, which makes a URL a shareable view — the thing a league
needs when someone posts "look at lap 27".
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import data, fmt


def _qp_int(key: str) -> int | None:
    raw = st.query_params.get(key)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _set(key: str, value) -> None:
    """Mirror a selection into session_state and the URL."""
    st.session_state[key] = value
    if value is None:
        st.query_params.pop(key, None)
    else:
        st.query_params[key] = str(value)


# The selections this module owns, in dependency order.
_KEYS = ("league", "season", "subsession", "lap")


def _init_state() -> None:
    """Seed session_state from the URL, once per session.

    Without this the first run has an empty session_state, so the season-change
    check below fires on every fresh load and clears the very deep link it is
    about to read.
    """
    if st.session_state.get("_seeded"):
        return
    for key in _KEYS:
        value = _qp_int(key)
        if value is not None:
            st.session_state[key] = value
    st.session_state["_seeded"] = True


def _pick(state_key: str, options: list[int], default: int | None = None) -> int | None:
    """Current value for a key, falling back to the URL then to `default`."""
    current = st.session_state.get(state_key, _qp_int(state_key))
    if current in options:
        return current
    return default if default is not None else (options[0] if options else None)


def _rail(sessions: pd.DataFrame, selected: int | None, navigate_to: str | None) -> None:
    """The season rail — one card-ish button per race, newest at the top."""
    st.sidebar.markdown("###### Season rail")

    for row in sessions.sort_values("round", ascending=False).itertuples():
        is_current = row.subsession_id == selected
        label = (
            f"**R{row.round} · {fmt.race_date(row.start_time)}**  \n"
            f"{fmt.track_label(row.track_name, row.track_config_name)}"
        )
        if st.sidebar.button(
            label,
            key=f"rail_{row.subsession_id}",
            width="stretch",
            type="primary" if is_current else "secondary",
        ):
            _set("subsession", int(row.subsession_id))
            _set("lap", None)  # a new race invalidates the lap cursor
            if navigate_to:
                st.switch_page(navigate_to)
            st.rerun()


def sidebar(
    show_rail: bool = True, navigate_to: str | None = None
) -> tuple[int | None, int | None, int | None]:
    """Render the shared sidebar. Returns (league_id, season_id, subsession_id).

    `navigate_to` sends a rail click to that page (Home hands it the Session
    page, so picking a race opens it); pages already showing the race omit it
    and just rerun in place.
    """
    _init_state()

    leagues = data.leagues()
    if leagues.empty:
        st.sidebar.warning("No ingested races yet.")
        return None, None, None

    st.sidebar.markdown("## Simlytics")

    league_ids = leagues["league_id"].tolist()
    league_id = _pick("league", league_ids)
    league_id = st.sidebar.selectbox(
        "League",
        league_ids,
        index=league_ids.index(league_id),
        format_func=lambda i: leagues.set_index("league_id").at[i, "league_name"],
    )
    _set("league", int(league_id))

    seasons = data.seasons(league_id=int(league_id))
    season_ids = seasons["season_id"].tolist()
    season_id = _pick("season", season_ids)
    season_id = st.sidebar.selectbox(
        "Season",
        season_ids,
        index=season_ids.index(season_id),
        format_func=lambda i: seasons.set_index("season_id").at[i, "season_name"],
    )
    if season_id != st.session_state.get("season"):
        # Changing season invalidates anything race-scoped.
        _set("subsession", None)
        _set("lap", None)
    _set("season", int(season_id))

    sessions = data.sessions(season_id=int(season_id))
    subsession_ids = sessions["subsession_id"].tolist()
    newest = (
        int(sessions.sort_values("round").iloc[-1]["subsession_id"])
        if not sessions.empty
        else None
    )
    subsession_id = _pick("subsession", subsession_ids, default=newest)
    if subsession_id is not None:
        _set("subsession", int(subsession_id))

    if show_rail and not sessions.empty:
        _rail(sessions, subsession_id, navigate_to)

    st.sidebar.divider()
    if st.sidebar.button("Refresh data", width="stretch"):
        data.refresh()
        st.rerun()

    return int(league_id), int(season_id), subsession_id

def range_picker(sessions: pd.DataFrame) -> tuple[list[int], str]:
    """Four editors for one value: a list of subsession ids.

    Round / date / last-N / hand-pick all write the same `list[int]`, and every
    downstream aggregation takes that list — so the rest of the page never has to
    know which editor produced it.
    """
    if sessions.empty:
        return [], "Rounds"

    ordered = sessions.sort_values("round")
    modes = ["Rounds", "Dates", "Last N", "Pick"]
    stored = st.query_params.get("range_mode")
    mode = st.sidebar.segmented_control(
        "Range", modes, default=stored if stored in modes else "Rounds"
    ) or "Rounds"
    st.query_params["range_mode"] = mode

    rounds = ordered["round"].tolist()
    picked: list[int]

    if mode == "Rounds":
        lo, hi = st.sidebar.select_slider(
            "Rounds", options=rounds, value=(rounds[0], rounds[-1])
        )
        picked = ordered[ordered["round"].between(lo, hi)]["subsession_id"].tolist()

    elif mode == "Dates":
        dates = ordered["start_time"].dt.date
        span = st.sidebar.date_input(
            "Dates",
            value=(dates.min(), dates.max()),
            min_value=dates.min(),
            max_value=dates.max(),
        )
        if isinstance(span, tuple) and len(span) == 2:
            lo, hi = span
        else:  # mid-edit the widget returns a single date
            lo = hi = span if not isinstance(span, tuple) else span[0]
        picked = ordered[(dates >= lo) & (dates <= hi)]["subsession_id"].tolist()

    elif mode == "Last N":
        n = st.sidebar.number_input(
            "Last N races", min_value=1, max_value=len(rounds), value=min(5, len(rounds))
        )
        picked = ordered.tail(int(n))["subsession_id"].tolist()

    else:
        labels = {
            int(r.subsession_id): f"R{r.round} · {r.track_name}"
            for r in ordered.itertuples()
        }
        picked = st.sidebar.multiselect(
            "Races",
            list(labels),
            default=list(labels),
            format_func=lambda s: labels[s],
        )

    st.sidebar.caption(f"{len(picked)} of {len(ordered)} races selected")
    return [int(s) for s in picked], mode
