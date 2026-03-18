"""
Quadrant Scatter Plots
-----------------------
Reusable function for quadrant scatter plots with median lines,
colored corner labels, and pill-badge player annotations.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ── Palette ──────────────────────────────────────────────────────────
BG          = "#0d0f14"
DOT_COLOR   = "#6b7280"
MEDIAN_LINE = "rgba(255,255,255,0.22)"

LABEL_GOOD_FG  = "#4ade80"   # green  — best-quadrant corners
LABEL_BAD_FG   = "#f59e0b"   # amber  — other corners

BADGE_BG       = "#1d4ed8"   # blue pill background
BADGE_BORDER   = "#3b82f6"   # blue pill border
BADGE_FG       = "#ffffff"   # white text inside pill


def create_quadrant_scatter(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    x_label: str,
    y_label: str,
    title: str,
    quadrant_labels: dict,
    best_quadrant: str = "top_right",
    top_n_annotate: int = 8,
    highlight_col: str = "chance_creation_score",
    subtitle: str = "Serie A, 2025/26",
    height: int = 420,
) -> go.Figure:
    """
    Create a quadrant scatter plot.

    Parameters
    ----------
    df : DataFrame containing player data (already filtered).
    x_col, y_col : Column names for the axes.
    x_label, y_label : Human-readable axis labels.
    title : Chart title.
    quadrant_labels : Dict with keys 'top_left', 'top_right',
                      'bottom_left', 'bottom_right'.
    best_quadrant : Which quadrant is 'best'. One of the
                    quadrant_labels keys.
    top_n_annotate : How many players to annotate with pill badges.
    highlight_col : Column used to rank players for annotation.
    subtitle : Small subtitle shown below the title.
    height : Figure height in pixels.

    Returns
    -------
    go.Figure
    """
    _cols = list(dict.fromkeys([x_col, y_col, "player_name", "team_name", highlight_col]))
    plot_df = df[_cols].copy()
    plot_df = plot_df.loc[:, ~plot_df.columns.duplicated()]
    plot_df = plot_df.replace([np.inf, -np.inf], np.nan).dropna(subset=[x_col, y_col])

    if plot_df.empty:
        fig = go.Figure()
        fig.update_layout(
            title=title,
            plot_bgcolor=BG, paper_bgcolor=BG,
            font=dict(color="#cbd5e1"),
            annotations=[dict(
                text="No data available", x=0.5, y=0.5,
                xref="paper", yref="paper", showarrow=False,
                font=dict(size=16),
            )],
        )
        return fig

    median_x = plot_df[x_col].median()
    median_y = plot_df[y_col].median()

    # Top players by highlight_col — they get the pill badge
    top_names = set(plot_df.nlargest(top_n_annotate, highlight_col)["player_name"])

    fig = go.Figure()

    # ── All dots (uniform gray) ───────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=plot_df[x_col],
        y=plot_df[y_col],
        mode="markers",
        marker=dict(
            color=DOT_COLOR,
            size=7,
            opacity=0.75,
            line=dict(width=0),
        ),
        text=plot_df["player_name"],
        customdata=plot_df[["team_name", x_col, y_col]].values,
        hovertemplate=(
            "<b>%{text}</b><br>"
            "%{customdata[0]}<br>"
            f"{x_label}: %{{customdata[1]:.2f}}<br>"
            f"{y_label}: %{{customdata[2]:.2f}}"
            "<extra></extra>"
        ),
        showlegend=False,
    ))

    # ── Median lines (solid, low opacity) ────────────────────────────
    fig.add_vline(
        x=median_x,
        line=dict(color=MEDIAN_LINE, width=1.5, dash="solid"),
    )
    fig.add_hline(
        y=median_y,
        line=dict(color=MEDIAN_LINE, width=1.5, dash="solid"),
    )

    # ── Pill-badge annotations for top players ────────────────────────
    top_df = plot_df[plot_df["player_name"].isin(top_names)]
    for _, row in top_df.iterrows():
        fig.add_annotation(
            x=row[x_col],
            y=row[y_col],
            text=f"  {row['player_name']}  ",
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            xshift=10,
            font=dict(size=10, color=BADGE_FG, family="Arial"),
            bgcolor=BADGE_BG,
            bordercolor=BADGE_BORDER,
            borderwidth=1,
            borderpad=3,
            opacity=0.92,
        )

    # ── Corner quadrant labels ────────────────────────────────────────
    x_min = plot_df[x_col].min()
    x_max = plot_df[x_col].max()
    y_min = plot_df[y_col].min()
    y_max = plot_df[y_col].max()
    pad_x = (x_max - x_min) * 0.025
    pad_y = (y_max - y_min) * 0.03

    corners = {
        "top_left":     (x_min + pad_x, y_max - pad_y, "left",  "top"),
        "top_right":    (x_max - pad_x, y_max - pad_y, "right", "top"),
        "bottom_left":  (x_min + pad_x, y_min + pad_y, "left",  "bottom"),
        "bottom_right": (x_max - pad_x, y_min + pad_y, "right", "bottom"),
    }

    for key, (cx, cy, xanchor, yanchor) in corners.items():
        label_text = quadrant_labels.get(key, "")
        color = LABEL_GOOD_FG if key == best_quadrant else LABEL_BAD_FG
        fig.add_annotation(
            x=cx, y=cy,
            text=label_text.replace("\n", "<br>"),
            showarrow=False,
            xanchor=xanchor,
            yanchor=yanchor,
            font=dict(size=10, color=color, family="Arial"),
            align="center",
        )

    # ── Subtitle annotation ───────────────────────────────────────────
    if subtitle:
        fig.add_annotation(
            x=0, y=1,
            xref="paper", yref="paper",
            text=subtitle,
            showarrow=False,
            xanchor="left",
            yanchor="bottom",
            yshift=-2,
            font=dict(size=10, color="#64748b", family="Arial"),
        )

    # ── Layout ───────────────────────────────────────────────────────
    fig.update_layout(
        title=dict(
            text=title.upper(),
            font=dict(size=12, color="#e2e8f0", family="Arial Black"),
            x=0,
            xref="paper",
            pad=dict(l=0, t=4),
        ),
        plot_bgcolor=BG,
        paper_bgcolor=BG,
        font=dict(color="#e2e8f0", family="Arial"),
        height=height,
        margin=dict(l=60, r=20, t=64, b=56),
        xaxis=dict(
            title=dict(
                text=x_label.upper(),
                font=dict(size=11, color="#94a3b8"),
            ),
            gridcolor="rgba(0,0,0,0)",   # no grid
            zeroline=False,
            tickcolor="#4b5563",
            tickfont=dict(color="#94a3b8", size=10),
            linecolor="rgba(255,255,255,0.08)",
        ),
        yaxis=dict(
            title=dict(
                text=y_label.upper(),
                font=dict(size=11, color="#94a3b8"),
            ),
            gridcolor="rgba(0,0,0,0)",   # no grid
            zeroline=False,
            tickcolor="#4b5563",
            tickfont=dict(color="#94a3b8", size=10),
            linecolor="rgba(255,255,255,0.08)",
        ),
        hoverlabel=dict(
            bgcolor="#1e293b",
            font_color="#e2e8f0",
            bordercolor="#334155",
        ),
    )

    return fig


def get_best_quadrant_df(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    best_quadrant: str,
    highlight_col: str = "chance_creation_score",
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Return the top N players in the 'best' quadrant.

    For most plots the best quadrant is top-right (above median X,
    above median Y). For possession the best quadrant is top-left
    (below median X, above median Y).
    """
    _cols = list(dict.fromkeys([x_col, y_col, "player_name", "team_name", highlight_col]))
    plot_df = df[_cols].copy()
    plot_df = plot_df.loc[:, ~plot_df.columns.duplicated()]
    plot_df = plot_df.replace([np.inf, -np.inf], np.nan).dropna(subset=[x_col, y_col])

    if plot_df.empty:
        return pd.DataFrame()

    median_x = plot_df[x_col].median()
    median_y = plot_df[y_col].median()

    if best_quadrant == "top_right":
        mask = (plot_df[x_col] >= median_x) & (plot_df[y_col] >= median_y)
    elif best_quadrant == "top_left":
        mask = (plot_df[x_col] <= median_x) & (plot_df[y_col] >= median_y)
    elif best_quadrant == "bottom_right":
        mask = (plot_df[x_col] >= median_x) & (plot_df[y_col] <= median_y)
    else:  # bottom_left
        mask = (plot_df[x_col] <= median_x) & (plot_df[y_col] <= median_y)

    return (
        plot_df[mask]
        .sort_values(highlight_col, ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
