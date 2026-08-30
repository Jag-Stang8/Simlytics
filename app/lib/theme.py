"""Design tokens and chrome, lifted from resources/Simlytics Web UI Ideas.dc.html.

Most of the theme lives in `.streamlit/config.toml` (surfaces, fonts, radii,
chart colours). This module carries the rest: the parts of the mockups that are
composed elements rather than theme values — the top bar, the uppercase mono
micro-labels, the metric tiles, the season-rail rows — plus a small CSS block to
bring Streamlit's native widgets in line.

Values here are the design's own. Where it uses an rgba ink overlay the solid
equivalent is noted, since some Streamlit surfaces need a flat colour.
"""

from __future__ import annotations

import html

import streamlit as st

# --- surfaces ---------------------------------------------------------------
APP = "#1b2024"        # card / main surface
SIDEBAR = "#161b1f"
PANEL = "#212830"      # tiles, table header, inset blocks
INK_ON_LIGHT = "#16181a"

# --- ink --------------------------------------------------------------------
INK = "#e9eef2"
INK_75 = "rgba(233,238,242,.75)"
INK_60 = "rgba(233,238,242,.6)"
INK_40 = "rgba(233,238,242,.4)"
INK_35 = "rgba(233,238,242,.35)"
INK_30 = "rgba(233,238,242,.3)"

# --- lines ------------------------------------------------------------------
LINE_08 = "rgba(233,238,242,.08)"
LINE_10 = "rgba(233,238,242,.10)"
LINE_14 = "rgba(233,238,242,.14)"

# --- accents (the design's oklch values, converted) -------------------------
ACCENT = "#56acf0"        # oklch(0.72 0.13 245)
GAIN = "#72cf8e"          # oklch(0.78 0.13 152)
GAIN_TEXT = "#7fdc9a"     # oklch(0.82 0.13 152)
CAUTION = "#f2b95a"       # oklch(0.82 0.13 78)
CAUTION_BRIGHT = "#f9bf60"
LOSS = "#ef6661"          # oklch(0.68 0.17 25)

MONO = "'IBM Plex Mono',ui-monospace,monospace"
SANS = "Barlow,Helvetica,sans-serif"

_CSS = f"""
<style>
/* Tabs: the design's underline strip — 12.5px Barlow, active in full ink with a
   2px accent rule, inactive muted. */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0; border-bottom: 1px solid {LINE_08}; padding: 0 2px;
}}
.stTabs [data-baseweb="tab"] {{
    font-family: {SANS}; font-size: 12.5px; font-weight: 500;
    color: {INK_60}; padding: 11px 13px; background: transparent;
}}
.stTabs [aria-selected="true"] {{
    font-weight: 600; color: {INK};
    box-shadow: inset 0 -2px 0 {ACCENT};
}}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}

/* Season rail: each button is a row — round, track, date — not a chunky control. */
[data-testid="stSidebar"] .stButton button {{
    text-align: left; justify-content: flex-start;
    padding: 8px 10px; border-radius: 7px; min-height: 0;
    font-family: {SANS}; font-size: 12.5px; font-weight: 500;
    background: {PANEL}; border: 1px solid {LINE_08}; color: {INK_75};
    line-height: 1.35;
}}
[data-testid="stSidebar"] .stButton button:hover {{
    border-color: {LINE_14}; color: {INK}; background: {PANEL};
}}
/* Selected round: the mockups invert on dark — light fill, dark ink. */
[data-testid="stSidebar"] .stButton button[kind="primary"],
[data-testid="stSidebar"] .stButton button[data-testid="stBaseButton-primary"] {{
    background: {INK}; color: {INK_ON_LIGHT}; border-color: {INK};
}}

/* Segmented control: selected reads as the inverted chip from 3a. */
[data-testid="stSidebar"] [data-baseweb="button-group"] button {{
    font-family: {SANS}; font-size: 11.5px; font-weight: 500;
}}

/* Micro-labels do the section-heading work, so pull Streamlit's own headings
   down to the mockups' scale. */
h1, h2, h3 {{ font-family: {SANS}; letter-spacing: -.01em; }}
h3 {{ font-size: 25px !important; font-weight: 600 !important; }}

/* Tables: mono figures, panel header — as drawn. */
[data-testid="stDataFrame"] {{ font-variant-numeric: tabular-nums; }}

/* Tighten the default page padding toward the mockups' 24px gutter. */
.block-container {{ padding-top: 2.4rem; padding-bottom: 3rem; }}
</style>
"""


def inject() -> None:
    """Apply the CSS layer. Call once per page, after set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)


def _esc(v) -> str:
    return html.escape(str(v))


def micro(label: str, margin_bottom: int = 9) -> str:
    """The uppercase mono section label used throughout the mockups."""
    return (
        f"<div style=\"font:600 9.5px {MONO};letter-spacing:.09em;"
        f"color:{INK_35};margin-bottom:{margin_bottom}px\">{_esc(label).upper()}</div>"
    )


def topbar(breadcrumb: str, right: str = "") -> None:
    """The `simlytics` wordmark, a mono breadcrumb, and an optional right-hand stat."""
    st.markdown(
        f"""<div style="display:flex;align-items:center;justify-content:space-between;
             padding:0 0 14px;border-bottom:1px solid {LINE_08};margin-bottom:18px">
          <div style="display:flex;align-items:baseline;gap:14px">
            <span style="font:700 15px {SANS};color:{INK}">simlytics</span>
            <span style="font:500 10.5px {MONO};color:{INK_40}">{_esc(breadcrumb).upper()}</span>
          </div>
          <span style="font:500 10.5px {MONO};color:{INK_40}">{_esc(right).upper()}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def tiles(items: list[tuple[str, str, str | None]]) -> None:
    """The metric strip: mono label over a 20px Barlow figure, on a panel tile.

    Each item is (label, value, accent) — accent being a colour for the figure,
    or None for default ink.
    """
    cells = "".join(
        f"""<div style="flex:1;display:flex;flex-direction:column;gap:2px;
              padding:9px 11px;border-radius:8px;background:{PANEL};
              border:1px solid {LINE_08}">
              <span style="font:600 9.5px {MONO};letter-spacing:.08em;color:{INK_40}">{_esc(lbl).upper()}</span>
              <span style="font:600 20px {SANS};color:{accent or INK}">{_esc(val)}</span>
            </div>"""
        for lbl, val, accent in items
    )
    st.markdown(
        f'<div style="display:flex;gap:8px;margin:2px 0 6px">{cells}</div>',
        unsafe_allow_html=True,
    )


def pill(text: str, tone: str = ACCENT) -> str:
    """The small status chip — GREEN, CAUTION, OUTLIER."""
    return (
        f"<span style=\"font:600 9.5px {MONO};letter-spacing:.06em;padding:4px 9px;"
        f"border-radius:4px;background:{tone}29;color:{tone}\">{_esc(text).upper()}</span>"
    )


def note(text: str) -> None:
    """The inset explanatory block used under charts in the mockups."""
    st.markdown(
        f"""<div style="margin-top:12px;padding:12px 14px;border-radius:8px;
             background:{PANEL};border:1px solid {LINE_08};
             font:400 11.5px/1.6 {SANS};color:{INK_60}">{text}</div>""",
        unsafe_allow_html=True,
    )
