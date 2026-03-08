"""
Radar Chart Visualizations
---------------------------
Creates radar/spider charts for comparing player profiles.
Used both in the Streamlit app and for static exports.
"""

import plotly.graph_objects as go

import config

# ── Dark theme palette ────────────────────────────────────────────────
D_BG     = "#111827"        # chart / polar background
D_PAPER  = "#111827"        # figure background
D_GRID   = "rgba(255,255,255,0.08)"
D_LINE   = "rgba(255,255,255,0.15)"
D_TEXT   = "#cbd5e1"
D_TICK   = "#94a3b8"

# ── Player colour palette (vibrant on dark) ───────────────────────────
PLAYER_COLORS = [
    ("rgba(0, 149, 255, 0.20)",  "#0095FF"),   # blue
    ("rgba(255, 82,  82,  0.20)", "#FF5252"),   # red
    ("rgba(0, 230, 172, 0.20)",  "#00E6AC"),   # teal
    ("rgba(255, 196,  0,  0.20)", "#FFC400"),   # amber
    ("rgba(180, 80,  255, 0.20)", "#B450FF"),   # purple
]

METRIC_LABELS = {
    "key_passes_p90":               "Key Passes",
    "through_balls_p90":            "Through Balls",
    "passes_into_final_third_p90":  "Into Final Third",
    "passes_into_penalty_area_p90": "Into Box",
    "shot_creating_actions_p90":    "Shot-Creating Actions",
    "successful_dribbles_p90":      "Dribbles",
    "progressive_passes_p90":       "Progressive Passes",
}


def _display_name(metric: str) -> str:
    return METRIC_LABELS.get(metric, metric.replace("_p90", "").replace("_", " ").title())


def _dark_polar() -> dict:
    return dict(
        bgcolor=D_BG,
        radialaxis=dict(
            visible=True,
            range=[0, 100],
            tickvals=[25, 50, 75, 100],
            tickfont=dict(size=9, color=D_TICK),
            gridcolor=D_GRID,
            linecolor=D_LINE,
            ticksuffix="th",
        ),
        angularaxis=dict(
            tickfont=dict(size=11, color=D_TEXT),
            gridcolor=D_GRID,
            linecolor=D_LINE,
        ),
    )


def create_radar_chart(
    player_data: dict,
    metrics: list[str] | None = None,
    title: str = "",
    color_index: int = 0,
) -> go.Figure:
    """Single-player radar chart — dark theme, hover shows value + percentile."""
    if metrics is None:
        metrics = config.CHANCE_CREATION_METRICS

    fill_color, line_color = PLAYER_COLORS[color_index % len(PLAYER_COLORS)]
    display_names = [_display_name(m) for m in metrics]
    pct_values    = [float(player_data.get(f"{m}_pct", 0) or 0) for m in metrics]
    raw_values    = [float(player_data.get(m, 0) or 0) for m in metrics]

    theta = display_names + [display_names[0]]
    r     = pct_values    + [pct_values[0]]
    hover = [
        f"<b>{dn}</b><br>Percentile: {p:.0f}th<br>Value / 90: {v:.2f}"
        for dn, p, v in zip(display_names, pct_values, raw_values)
    ] + [f"<b>{display_names[0]}</b><br>Percentile: {pct_values[0]:.0f}th<br>Value / 90: {raw_values[0]:.2f}"]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=r, theta=theta,
        fill="toself",
        fillcolor=fill_color,
        line=dict(color=line_color, width=2.5),
        name=title or "Player",
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover,
    ))

    fig.update_layout(
        polar=_dark_polar(),
        showlegend=False,
        title=dict(text=title, font=dict(size=14, color=D_TEXT), x=0.5),
        paper_bgcolor=D_PAPER,
        height=420,
        margin=dict(t=50, b=30, l=60, r=60),
        font=dict(color=D_TEXT),
    )
    return fig


def create_comparison_radar(
    players: list[dict],
    names: list[str],
    metrics: list[str] | None = None,
    title: str = "Player Comparison",
) -> go.Figure:
    """Multi-player overlay radar — dark theme, hover shows value + percentile."""
    if metrics is None:
        metrics = config.CHANCE_CREATION_METRICS

    display_names = [_display_name(m) for m in metrics]
    fig = go.Figure()

    for i, (player, name) in enumerate(zip(players, names)):
        fill_color, line_color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        pct_values = [float(player.get(f"{m}_pct", 0) or 0) for m in metrics]
        raw_values = [float(player.get(m, 0) or 0) for m in metrics]

        theta = display_names + [display_names[0]]
        r     = pct_values    + [pct_values[0]]
        hover = [
            f"<b>{name}</b><br>{dn}<br>Percentile: {p:.0f}th<br>Value / 90: {v:.2f}"
            for dn, p, v in zip(display_names, pct_values, raw_values)
        ] + [f"<b>{name}</b><br>{display_names[0]}<br>Percentile: {pct_values[0]:.0f}th<br>Value / 90: {raw_values[0]:.2f}"]

        fig.add_trace(go.Scatterpolar(
            r=r, theta=theta,
            fill="toself",
            fillcolor=fill_color,
            line=dict(color=line_color, width=2.5),
            name=name,
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover,
        ))

    fig.update_layout(
        polar=_dark_polar(),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=-0.15,
            xanchor="center", x=0.5,
            font=dict(size=11, color=D_TEXT),
            bgcolor="rgba(0,0,0,0)",
        ),
        title=dict(text=title, font=dict(size=14, color=D_TEXT), x=0.5),
        paper_bgcolor=D_PAPER,
        height=480,
        margin=dict(t=50, b=60, l=60, r=60),
        font=dict(color=D_TEXT),
    )
    return fig
