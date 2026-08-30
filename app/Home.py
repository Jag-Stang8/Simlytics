"""Entry page: league / season pick, the season rail, and the season's races.

Once `pages/1_Session.py` exists this redirects to the selected session with
`st.switch_page`; until then it shows the season at a glance.
"""

import sys
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from lib import data, filters, fmt, theme

st.set_page_config(page_title="Simlytics", page_icon="🏁", layout="wide")

theme.inject()

league_id, season_id, subsession_id = filters.sidebar(
    navigate_to="pages/1_Session.py"
)

if season_id is None:
    st.title("Simlytics")
    st.info("No ingested races yet. Run `uv run python -m ingest.ingest <path.json>` first.")
    st.stop()

sessions = data.sessions(season_id=season_id)
seasons = data.seasons(league_id=league_id).set_index("season_id")
season_name = seasons.at[season_id, "season_name"]
league_name = seasons.at[season_id, "league_name"]

theme.topbar(
    f"{league_name} · {season_name}",
    f"{len(sessions)} races · {sessions['entries'].max()} entries · "
    f"{fmt.compact(sessions['green_passes'].sum())} green passes",
)

theme.tiles([
    ("Races", str(len(sessions)), None),
    ("Green passes", fmt.compact(sessions["green_passes"].sum()), theme.GAIN_TEXT),
    ("Cautions", str(int(sessions["num_cautions"].sum())), theme.CAUTION),
    ("Median SOF", fmt.compact(sessions["sof"].median()), None),
])
st.write("")
st.markdown(theme.micro("Season calendar"), unsafe_allow_html=True)

# --- the season's races -----------------------------------------------------
table = sessions.assign(
    Round=sessions["round"],
    Date=sessions["start_time"].map(lambda d: fmt.race_date(d, "long")),
    Track=[
        fmt.track_label(n, c)
        for n, c in zip(sessions["track_name"], sessions["track_config_name"])
    ],
    Entries=sessions["entries"],
    Laps=sessions["laps_completed"],
    SOF=sessions["sof"],
    Cautions=sessions["num_cautions"],
    Leads=sessions["num_lead_changes"],
    Passes=sessions["green_passes"],
)[
    ["Round", "Date", "Track", "Entries", "Laps", "SOF", "Cautions", "Leads", "Passes"]
]

st.dataframe(
    table,
    hide_index=True,
    width="stretch",
    column_config={
        "Leads": st.column_config.NumberColumn(
            "Lead changes", help="race_summary.num_lead_changes"
        ),
        "Passes": st.column_config.NumberColumn(
            "Green passes", help="Excludes pit-cycle and under-caution passes"
        ),
    },
)

if subsession_id is not None:
    picked = sessions.set_index("subsession_id").loc[subsession_id]
    st.caption(
        f"Selected: R{picked['round']} · "
        f"{fmt.track_label(picked['track_name'], picked['track_config_name'])} · "
        f"subsession {subsession_id}"
    )
