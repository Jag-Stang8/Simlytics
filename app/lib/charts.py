"""Altair builders. No SQL — every function takes a DataFrame and returns a chart.

Colour follows the dataviz rules the designs are built on:

* **Sequential** encoding (the heatmap) is ONE hue, light -> dark. Never a rainbow.
* **Emphasis** rather than categorical for the progression chart. A league race
  has 30-50 entries; hue cannot carry 50 identities, so the field is grey and the
  highlighted drivers take the fixed slots in `fmt.HIGHLIGHT`, assigned in a
  stable order so filtering never repaints a survivor.
* Marks stay thin, gridlines recessive, and no chart carries a second y-axis.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from . import fmt

# One hue, light -> dark (the blue ramp).
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281"]
GRID = "#2c2c2a"
AXIS = "#8a949e"


def _base(chart: alt.Chart) -> alt.Chart:
    return chart.configure_view(stroke=None).configure_axis(
        gridColor=GRID,
        domainColor=GRID,
        tickColor=GRID,
        labelColor=AXIS,
        titleColor=AXIS,
        labelFontSize=11,
        titleFontSize=11,
        grid=True,
    ).configure_legend(labelColor=AXIS, titleColor=AXIS, labelFontSize=11, titleFontSize=11)


def driver_round_heatmap(
    df: pd.DataFrame, metric: str, label: str, reverse: bool = False
) -> alt.Chart:
    """Driver x round grid, one sequential hue.

    `reverse` darkens LOW values — for metrics where less is better (finish
    position, incidents, pit delta).
    """
    scheme = list(reversed(SEQUENTIAL)) if reverse else SEQUENTIAL
    order = (
        df.groupby("driver_name")[metric]
        .mean()
        .sort_values(ascending=reverse)
        .index.tolist()
    )
    chart = (
        alt.Chart(df)
        .mark_rect(stroke=None)
        .encode(
            x=alt.X("round:O", title="Round", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("driver_name:N", title=None, sort=order),
            color=alt.Color(
                f"{metric}:Q",
                title=label,
                scale=alt.Scale(range=scheme),
                legend=alt.Legend(orient="top", direction="horizontal", gradientLength=180),
            ),
            tooltip=[
                alt.Tooltip("driver_name:N", title="Driver"),
                alt.Tooltip("round:O", title="Round"),
                alt.Tooltip("track_name:N", title="Track"),
                alt.Tooltip(f"{metric}:Q", title=label, format=".2f"),
            ],
        )
        .properties(height=alt.Step(15))
    )
    return _base(chart)


def points_progression(df: pd.DataFrame, highlight: list[str]) -> alt.Chart:
    """Cumulative points by round — highlighted drivers in colour, field in grey.

    `df` needs driver_name, round, cumulative_points.
    """
    colors = fmt.HIGHLIGHT[: len(highlight)]
    field = df[~df["driver_name"].isin(highlight)]
    lead = df[df["driver_name"].isin(highlight)]

    layers = []
    if not field.empty:
        layers.append(
            alt.Chart(field)
            .mark_line(strokeWidth=1, opacity=0.35, color="#5c6470")
            .encode(
                x=alt.X("round:Q", title="Round", axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("cumulative_points:Q", title="Points"),
                detail="driver_name:N",
                tooltip=[
                    alt.Tooltip("driver_name:N", title="Driver"),
                    alt.Tooltip("round:Q", title="Round"),
                    alt.Tooltip("cumulative_points:Q", title="Points"),
                ],
            )
        )
    if not lead.empty:
        layers.append(
            alt.Chart(lead)
            .mark_line(strokeWidth=2, interpolate="linear")
            .encode(
                x=alt.X("round:Q", title="Round", axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("cumulative_points:Q", title="Points"),
                color=alt.Color(
                    "driver_name:N",
                    title="Driver",
                    scale=alt.Scale(domain=highlight, range=colors),
                    legend=alt.Legend(orient="bottom", columns=4),
                ),
                tooltip=[
                    alt.Tooltip("driver_name:N", title="Driver"),
                    alt.Tooltip("round:Q", title="Round"),
                    alt.Tooltip("cumulative_points:Q", title="Points"),
                ],
            )
        )
    return _base(alt.layer(*layers).properties(height=380))


CAUTION_BAND = "#f2b95a"


def position_by_lap(
    running: pd.DataFrame,
    highlight: list[str],
    caution_laps: list[int],
) -> alt.Chart:
    """Position-by-lap lines with caution bands and a clickable lap cursor.

    Emphasis, not categorical: a 28-46 car field is far past what hue can carry,
    so the field is one grey and only the highlighted drivers take slots from
    `fmt.HIGHLIGHT`. y is inverted so P1 sits at the top, which is how a running
    order is read.
    """
    lap_sel = alt.selection_point(
        name="lap", fields=["lap_num"], on="click", nearest=True, empty=False
    )
    y = alt.Y(
        "position:Q",
        title="Position",
        scale=alt.Scale(reverse=True, zero=False, nice=False),
        axis=alt.Axis(tickMinStep=1),
    )
    x = alt.X("lap_num:Q", title="Lap", scale=alt.Scale(nice=False))

    layers = []

    # Caution bands first, so lines draw over them.
    if caution_laps:
        bands = pd.DataFrame(_contiguous(caution_laps), columns=["start", "end"])
        layers.append(
            alt.Chart(bands)
            .mark_rect(color=CAUTION_BAND, opacity=0.16)
            .encode(
                x=alt.X("start:Q", title="Lap"),
                x2="end:Q",
                tooltip=[alt.Tooltip("start:Q", title="Caution from lap"),
                         alt.Tooltip("end:Q", title="to lap")],
            )
        )

    field = running[~running["driver_name"].isin(highlight)]
    lead = running[running["driver_name"].isin(highlight)]

    if not field.empty:
        layers.append(
            alt.Chart(field)
            .mark_line(strokeWidth=1, opacity=0.28, color="#5c6470")
            .encode(x=x, y=y, detail="driver_name:N")
        )
    if not lead.empty:
        layers.append(
            alt.Chart(lead)
            .mark_line(strokeWidth=2)
            .encode(
                x=x,
                y=y,
                color=alt.Color(
                    "driver_name:N",
                    title="Driver",
                    scale=alt.Scale(domain=highlight, range=fmt.HIGHLIGHT[: len(highlight)]),
                    legend=alt.Legend(orient="bottom", columns=4),
                ),
                tooltip=[
                    alt.Tooltip("driver_name:N", title="Driver"),
                    alt.Tooltip("lap_num:Q", title="Lap"),
                    alt.Tooltip("position:Q", title="Pos"),
                ],
            )
        )

    # A transparent wide-hit-area layer so clicking anywhere on a lap selects it,
    # rather than requiring a hit on a 2px line.
    cursor = (
        alt.Chart(running)
        .mark_rule(strokeWidth=6, opacity=0)
        .encode(x=x, tooltip=alt.Tooltip("lap_num:Q", title="Lap"))
        .add_params(lap_sel)
    )
    layers.append(cursor)

    return _base(alt.layer(*layers).properties(height=440))


def _contiguous(laps: list[int]) -> list[tuple[int, int]]:
    """[8,9,10,20,21] -> [(8,11),(20,22)] — half-open, for mark_rect x/x2."""
    spans: list[tuple[int, int]] = []
    for lap in sorted(laps):
        if spans and lap == spans[-1][1]:
            spans[-1] = (spans[-1][0], lap + 1)
        else:
            spans.append((lap, lap + 1))
    return spans


# Flag-state colours. Semantic, not arbitrary: green = clean racing, yellow =
# caution, violet = pit-cycle artefact. Validated as a set on #1b2024 (chroma
# floor, adjacent CVD 17.3, normal-vision 24.6, all >= 3:1). An earlier grey for
# "pit" failed the chroma floor — in a stacked bar that segment carries identity,
# so it needs a real hue rather than a de-emphasis tone.
FLAG_COLORS = {"green": "#199e70", "pit": "#9085e9", "caution": "#c98500"}
SURFACE = "#1b2024"


def pass_matrix(df: pd.DataFrame) -> alt.Chart:
    """Passer x passed green passes. One hue, magnitude only."""
    order = (
        df.groupby("passer_name")["passes"].sum().sort_values(ascending=False).index.tolist()
    )
    chart = (
        alt.Chart(df)
        .mark_rect()
        .encode(
            x=alt.X("passed_name:N", title="Passed", sort=order,
                    axis=alt.Axis(labelAngle=-45, labelLimit=90)),
            y=alt.Y("passer_name:N", title="Passer", sort=order,
                    axis=alt.Axis(labelLimit=110)),
            color=alt.Color("passes:Q", title="Passes",
                            scale=alt.Scale(range=SEQUENTIAL),
                            legend=alt.Legend(orient="top", direction="horizontal",
                                              gradientLength=160)),
            tooltip=[
                alt.Tooltip("passer_name:N", title="Passer"),
                alt.Tooltip("passed_name:N", title="Passed"),
                alt.Tooltip("passes:Q", title="Passes"),
                alt.Tooltip("reverted:Q", title="Reverted"),
                alt.Tooltip("first_lap:Q", title="First lap"),
                alt.Tooltip("last_lap:Q", title="Last lap"),
            ],
        )
        .properties(height=alt.Step(14), width=alt.Step(14))
    )
    return _base(chart)


def passing_by_flag(df: pd.DataFrame, direction: str = "made") -> alt.Chart:
    """Stacked bars of passes by flag state, one bar per driver.

    Segments are separated by a 2px stroke in the surface colour — the spacer,
    not a border: it is the background showing through, carrying no ink of its own.
    """
    cols = [f"{direction}_{f}" for f in ("green", "pit", "caution")]
    long = df.melt(
        id_vars=["driver_name", "finish"], value_vars=cols,
        var_name="flag", value_name="passes",
    )
    long["flag"] = long["flag"].str.rsplit("_", n=1).str[-1]
    long = long[long["passes"] > 0]

    order = df.sort_values("finish")["driver_name"].tolist()
    chart = (
        alt.Chart(long)
        .mark_bar(stroke=SURFACE, strokeWidth=2)
        .encode(
            y=alt.Y("driver_name:N", title=None, sort=order, axis=alt.Axis(labelLimit=120)),
            x=alt.X("passes:Q", title=f"Passes {direction}"),
            color=alt.Color(
                "flag:N", title="Flag",
                scale=alt.Scale(domain=list(FLAG_COLORS), range=list(FLAG_COLORS.values())),
                legend=alt.Legend(orient="top", direction="horizontal"),
            ),
            tooltip=[
                alt.Tooltip("driver_name:N", title="Driver"),
                alt.Tooltip("flag:N", title="Flag"),
                alt.Tooltip("passes:Q", title="Passes"),
            ],
        )
        .properties(height=alt.Step(18))
    )
    return _base(chart)


def pit_window_strip(stops: pd.DataFrame) -> alt.Chart:
    """When each driver was in the pits — in-lap to out-lap, per stop."""
    chart = (
        alt.Chart(stops)
        .mark_rect(height=12, cornerRadius=2)
        .encode(
            x=alt.X("in_lap:Q", title="Lap"),
            x2="out_lap_end:Q",
            y=alt.Y("driver_name:N", title=None, sort="x", axis=alt.Axis(labelLimit=120)),
            color=alt.Color(
                "time_lost_s:Q", title="Time lost (s)",
                scale=alt.Scale(range=SEQUENTIAL),
                legend=alt.Legend(orient="top", direction="horizontal", gradientLength=160),
            ),
            tooltip=[
                alt.Tooltip("driver_name:N", title="Driver"),
                alt.Tooltip("in_lap:Q", title="In lap"),
                alt.Tooltip("out_lap:Q", title="Out lap"),
                alt.Tooltip("time_lost_s:Q", title="Time lost (s)", format=".1f"),
                alt.Tooltip("cycle_s:Q", title="Cycle (s)", format=".1f"),
            ],
        )
        .properties(height=alt.Step(16))
    )
    return _base(chart)


def pace_box_stats(green: pd.DataFrame) -> pd.DataFrame:
    """Per-driver box statistics, computed in pandas.

    A boxplot needs five numbers per driver, not every lap: a long race has
    thousands of green laps and shipping them all to the browser to draw 40 boxes
    is wasted payload (and trips Altair's row guard). Whiskers are Tukey 1.5*IQR
    clamped to observed data.
    """
    rows = []
    for name, g in green.groupby("driver_name"):
        v = g["pace_pct"]
        q1, med, q3 = v.quantile([0.25, 0.5, 0.75])
        iqr = q3 - q1
        rows.append({
            "driver_name": name,
            "q1": q1, "median": med, "q3": q3,
            "lo": max(v.min(), q1 - 1.5 * iqr),
            "hi": min(v.max(), q3 + 1.5 * iqr),
            "laps": int(v.size),
        })
    return pd.DataFrame(rows)


def pace_box(stats: pd.DataFrame, highlight: list[str]) -> alt.Chart:
    """Green-lap pace spread per driver, as percent off the race median."""
    order = stats.sort_values("median")["driver_name"].tolist()
    y = alt.Y("driver_name:N", title=None, sort=order, axis=alt.Axis(labelLimit=120))
    color = alt.condition(
        alt.FieldOneOfPredicate("driver_name", highlight or [""]),
        alt.value(fmt.HIGHLIGHT[0]),
        alt.value("#5c6470"),
    )
    tooltip = [
        alt.Tooltip("driver_name:N", title="Driver"),
        alt.Tooltip("median:Q", title="Median", format="+.2f"),
        alt.Tooltip("q1:Q", title="Q1", format="+.2f"),
        alt.Tooltip("q3:Q", title="Q3", format="+.2f"),
        alt.Tooltip("laps:Q", title="Green laps"),
    ]
    base = alt.Chart(stats)
    whisker = base.mark_rule(strokeWidth=1, opacity=0.7).encode(
        y=y, x=alt.X("lo:Q", title="% off race median lap"), x2="hi:Q", color=color,
        tooltip=tooltip,
    )
    box = base.mark_bar(height=9, cornerRadius=2).encode(
        y=y, x="q1:Q", x2="q3:Q", color=color, tooltip=tooltip
    )
    mid = base.mark_tick(
        thickness=2, size=13, color=SURFACE, opacity=0.9
    ).encode(y=y, x="median:Q", tooltip=tooltip)
    return _base(alt.layer(whisker, box, mid).properties(height=alt.Step(15)))


def pace_scatter(summary: pd.DataFrame, highlight: list[str]) -> alt.Chart:
    """Median pace vs consistency. Emphasis: highlighted drivers, grey field.

    Scatter is an all-pairs form, so this deliberately uses ONE accent hue plus
    grey rather than a categorical scale — any two dots can end up adjacent.
    """
    base = alt.Chart(summary).encode(
        x=alt.X("pace_pct_median:Q", title="Median pace (% off race median)"),
        y=alt.Y("pace_pct_std:Q", title="Spread (std dev, %)"),
        tooltip=[
            alt.Tooltip("driver_name:N", title="Driver"),
            alt.Tooltip("pace_pct_median:Q", title="Median", format=".2f"),
            alt.Tooltip("pace_pct_std:Q", title="Spread", format=".2f"),
            alt.Tooltip("green_laps:Q", title="Green laps"),
        ],
    )
    field = base.transform_filter(
        ~alt.FieldOneOfPredicate("driver_name", highlight or [""])
    ).mark_point(size=55, filled=True, opacity=0.45, color="#5c6470", stroke=SURFACE,
                 strokeWidth=2)
    lead = base.transform_filter(
        alt.FieldOneOfPredicate("driver_name", highlight or [""])
    ).mark_point(size=110, filled=True, color=fmt.HIGHLIGHT[0], stroke=SURFACE,
                 strokeWidth=2)
    labels = base.transform_filter(
        alt.FieldOneOfPredicate("driver_name", highlight or [""])
    ).mark_text(align="left", dx=9, dy=-2, fontSize=11, color=AXIS).encode(
        text="driver_name:N"
    )
    return _base(alt.layer(field, lead, labels).properties(height=400))


def mirrored_bars(rows: pd.DataFrame, a_name: str, b_name: str) -> alt.Chart:
    """Two drivers, one row per metric, bars growing out from a shared centre.

    Bar LENGTH is each value normalized against the field's range for that metric
    -- points and conversion % cannot share a length scale otherwise -- and the
    real number is printed at the tip, so the reader never has to infer a value
    from a normalized bar.
    """
    a = rows.assign(side=a_name, signed=-rows["a_norm"], value=rows["a_label"],
                    align="right", dx=-6)
    b = rows.assign(side=b_name, signed=rows["b_norm"], value=rows["b_label"],
                    align="left", dx=6)
    long = pd.concat([a, b], ignore_index=True)
    order = rows["metric"].tolist()

    y = alt.Y("metric:N", title=None, sort=order, axis=alt.Axis(labelLimit=130))
    color = alt.Color(
        "side:N", title=None,
        scale=alt.Scale(domain=[a_name, b_name], range=fmt.HIGHLIGHT[:2]),
        legend=alt.Legend(orient="top", direction="horizontal"),
    )
    bars = (
        alt.Chart(long)
        .mark_bar(height=13, cornerRadius=3, stroke=SURFACE, strokeWidth=2)
        .encode(
            y=y,
            x=alt.X("signed:Q", title=None,
                    scale=alt.Scale(domain=[-1.15, 1.15]),
                    axis=None),
            color=color,
            tooltip=[alt.Tooltip("side:N", title="Driver"),
                     alt.Tooltip("metric:N", title="Metric"),
                     alt.Tooltip("value:N", title="Value")],
        )
    )
    # align/dx are literals in Altair, not field encodings — so each side gets
    # its own text layer rather than one layer switching alignment per datum.
    a_labels = (
        alt.Chart(a)
        .mark_text(fontSize=11, color=AXIS, align="right", dx=-6)
        .encode(y=y, x=alt.X("signed:Q"), text="value:N")
    )
    b_labels = (
        alt.Chart(b)
        .mark_text(fontSize=11, color=AXIS, align="left", dx=6)
        .encode(y=y, x=alt.X("signed:Q"), text="value:N")
    )
    return _base(
        alt.layer(bars, a_labels, b_labels).properties(height=alt.Step(26))
    )


RADAR_AXES = [("z_net", "Racecraft"), ("z_conv", "Attack"),
              ("z_def", "Defense"), ("z_restart", "Restarts")]
RADAR_CLAMP = 2.5


def _radar_points(row: pd.Series, name: str) -> pd.DataFrame:
    import math
    pts = []
    n = len(RADAR_AXES)
    for i, (col, label) in enumerate(RADAR_AXES):
        z = float(row.get(col, 0) or 0)
        z = max(-RADAR_CLAMP, min(RADAR_CLAMP, z))
        r = (z + RADAR_CLAMP) / (2 * RADAR_CLAMP)
        theta = 2 * math.pi * i / n
        pts.append({"driver": name, "axis": label, "z": z, "order": i,
                    "x": r * math.sin(theta), "y": r * math.cos(theta)})
    pts.append({**pts[0], "order": n})  # close the polygon
    return pd.DataFrame(pts)


def radar(a_row: pd.Series, b_row: pd.Series, a_name: str, b_name: str) -> alt.Chart:
    """Four passing z-scores per driver as a closed polygon.

    The radial scale is z clamped to +-2.5 mapped onto [0, 1], so the centre is
    -2.5 and the rim is +2.5; the middle ring is the field average (z = 0).
    Radar area exaggerates differences, so the same four numbers are printed in
    the table beside this chart rather than left to the shape alone.
    """
    import math
    data = pd.concat([_radar_points(a_row, a_name), _radar_points(b_row, b_name)],
                     ignore_index=True)

    rings = pd.concat([
        pd.DataFrame({
            "x": [r * math.sin(2 * math.pi * i / 60) for i in range(61)],
            "y": [r * math.cos(2 * math.pi * i / 60) for i in range(61)],
            "ring": r,
        }) for r in (0.5, 1.0)
    ], ignore_index=True)
    spokes = pd.DataFrame([
        {"x": v * math.sin(2 * math.pi * i / len(RADAR_AXES)),
         "y": v * math.cos(2 * math.pi * i / len(RADAR_AXES)), "axis": label}
        for i, (_c, label) in enumerate(RADAR_AXES) for v in (0.0, 1.0)
    ])
    labels = pd.DataFrame([
        {"x": 1.22 * math.sin(2 * math.pi * i / len(RADAR_AXES)),
         "y": 1.22 * math.cos(2 * math.pi * i / len(RADAR_AXES)), "axis": label}
        for i, (_c, label) in enumerate(RADAR_AXES)
    ])

    enc = dict(
        x=alt.X("x:Q", axis=None, scale=alt.Scale(domain=[-1.45, 1.45])),
        y=alt.Y("y:Q", axis=None, scale=alt.Scale(domain=[-1.35, 1.35])),
    )
    ring_layer = alt.Chart(rings).mark_line(strokeWidth=1, color=GRID).encode(
        **enc, detail="ring:N"
    )
    spoke_layer = alt.Chart(spokes).mark_line(strokeWidth=1, color=GRID).encode(
        **enc, detail="axis:N"
    )
    label_layer = alt.Chart(labels).mark_text(fontSize=11, color=AXIS).encode(
        **enc, text="axis:N"
    )
    poly = alt.Chart(data).mark_line(strokeWidth=2, opacity=0.95).encode(
        **enc,
        order="order:Q",
        color=alt.Color("driver:N", title=None,
                        scale=alt.Scale(domain=[a_name, b_name], range=fmt.HIGHLIGHT[:2]),
                        legend=alt.Legend(orient="bottom", direction="horizontal")),
        tooltip=[alt.Tooltip("driver:N", title="Driver"),
                 alt.Tooltip("axis:N", title="Component"),
                 alt.Tooltip("z:Q", title="z-score", format="+.2f")],
    )
    dots = alt.Chart(data[data["order"] < len(RADAR_AXES)]).mark_point(
        size=55, filled=True, stroke=SURFACE, strokeWidth=2
    ).encode(
        **enc,
        color=alt.Color("driver:N", legend=None,
                        scale=alt.Scale(domain=[a_name, b_name], range=fmt.HIGHLIGHT[:2])),
        tooltip=[alt.Tooltip("driver:N", title="Driver"),
                 alt.Tooltip("axis:N", title="Component"),
                 alt.Tooltip("z:Q", title="z-score", format="+.2f")],
    )
    return _base(
        alt.layer(ring_layer, spoke_layer, label_layer, poly, dots)
        .properties(height=380)
    )
