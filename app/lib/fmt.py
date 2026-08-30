"""Formatting and colour. No SQL, no Streamlit widgets.

Raw iRacing times are in **ten-thousandths of a second** (`laps.laptime`,
`laps.session_time`, `race_results.avg_lap`/`best_lap_time`). The `*_ms` columns
on `pit_cycles` are already milliseconds — `stats/pit_cycles.py` divides by 10 on
the way in. Use `laptime()` for the former and `delta_s()` for the latter.

Positions in the data are 0-based: `finish_pos = 0` is a win.
"""

from __future__ import annotations

import datetime as _dt

TICKS_PER_SECOND = 10_000

# --- palette (from the design; oklch is the source of truth) -----------------
BACKGROUND = "#1b2024"
PANEL = "#212830"
TEXT = "#e9eef2"
ACCENT = "#5aa2f0"   # oklch(0.72 0.13 245)
GAIN = "#72cf8e"     # oklch(0.78 0.13 152)
CAUTION = "#f2b95a"  # oklch(0.82 0.13 78)
LOSS = "#ef6661"     # oklch(0.68 0.17 25)
MUTED = "#8a949e"

# Highlight slots for driver emphasis. A league race has 35-45 entries, which is
# far past the point where hue can carry identity — so charts grey the field and
# spend these slots on the drivers actually under comparison. Order is fixed and
# never cycled; past 8 selected drivers, fall back to facets.
#
# These are the dark-surface steps, validated as a set against #1b2024: lightness
# band, chroma floor, adjacent CVD separation (worst 8.4), normal-vision floor
# (worst 19.3) and 3:1 contrast all pass. ACCENT above is UI chrome, not a series
# colour — it sits outside the dark band and is not part of this set.
HIGHLIGHT = [
    "#3987e5",  # blue
    "#d95926",  # orange
    "#199e70",  # aqua
    "#c98500",  # yellow
    "#d55181",  # magenta
    "#008300",  # green
    "#9085e9",  # violet
    "#e66767",  # red
]


def laptime(ticks: int | float | None) -> str:
    """Ten-thousandths of a second -> '1:23.456' / '23.456'."""
    if ticks is None or ticks <= 0:
        return "—"
    seconds = ticks / TICKS_PER_SECOND
    minutes, seconds = divmod(seconds, 60)
    if minutes:
        return f"{int(minutes)}:{seconds:06.3f}"
    return f"{seconds:.3f}"


def delta_s(ms: float | None, places: int = 2, signed: bool = True) -> str:
    """Milliseconds -> '+1.23 s'. For the already-ms pit_cycles columns."""
    if ms is None:
        return "—"
    value = ms / 1000
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value:.{places}f} s"


def pos(zero_based: int | None) -> str:
    """0-based position -> human 1-based."""
    return "—" if zero_based is None else str(int(zero_based) + 1)


def track_label(track_name: str, config_name: str | None = None) -> str:
    """'Phoenix Raceway' + 'Oval w/open dogleg' -> one display string.

    The config is dropped when it is absent, 'N/A', or already implied by the
    track name — iRacing repeats it often enough to be noise.
    """
    name = (track_name or "").strip()
    config = (config_name or "").strip()
    if not config or config.upper() == "N/A" or config.lower() in name.lower():
        return name
    return f"{name} — {config}"


def race_date(when: _dt.datetime | None, style: str = "short") -> str:
    """'20 MAY' for the rail, '20 May 2026' elsewhere."""
    if when is None:
        return "—"
    if style == "short":
        return when.strftime("%d %b").upper()
    return when.strftime("%d %b %Y")


def compact(n: float | int | None) -> str:
    """1284 -> '1,284'; 12934 -> '12.9K'."""
    if n is None:
        return "—"
    n = float(n)
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if abs(n) >= 10_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,.0f}"


def highlight_colors(cust_ids) -> dict[int, str]:
    """Stable colour per selected driver, assigned in the order given.

    Colour follows the driver, not their rank — so re-sorting or filtering a
    table never repaints the survivors. Callers hold the selection order stable
    (e.g. by cust_id) for this to mean anything across reruns.
    """
    return {c: HIGHLIGHT[i % len(HIGHLIGHT)] for i, c in enumerate(cust_ids)}