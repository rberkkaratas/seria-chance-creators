"""Team Rankings tab — league tables, global rating table, and performance delta."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from tabs import TabRenderer
from core.models import AppState
from core.constants import team_label, league_badge
from core.theme import D_GRID, D_TEXT, D_TICK, dark_layout


def _fmt_delta(delta) -> str:
    if pd.isna(delta):
        return "—"
    delta = int(delta)
    if delta < 0:
        return f"Over +{abs(delta)}"
    if delta > 0:
        return f"Under {delta}"
    return "Par"


def _delta_color(delta) -> str:
    if pd.isna(delta) or int(delta) == 0:
        return "#94a3b8"
    return "#22c55e" if int(delta) < 0 else "#f87171"


class TeamRankingsTab(TabRenderer):
    def render(self, state: AppState) -> None:
        teams = state.teams_df.copy()
        st.markdown('<p class="section-title">Team Rankings</p>', unsafe_allow_html=True)

        if teams.empty:
            st.info(
                "Team analytics file not found. Run "
                "`python -m src.features.team_features --season 2025-2026`."
            )
            return

        teams = teams.sort_values(["league", "league_rank_points", "team_name"])
        leagues = sorted(teams["league"].dropna().unique().tolist())

        mode_col, league_col = st.columns([1, 2])
        with mode_col:
            mode = st.radio(
                "Ranking mode",
                ["League", "Global"],
                horizontal=True,
                label_visibility="collapsed",
            )
        with league_col:
            selected_league = st.selectbox(
                "League",
                options=leagues,
                format_func=league_badge,
                label_visibility="collapsed",
                disabled=mode == "Global",
            )

        if mode == "League":
            view = teams[teams["league"] == selected_league].copy()
            view = view.sort_values("league_rank_points")
            table_cols = [
                "league_rank_points",
                "team_name",
                "matches_played",
                "wins",
                "draws",
                "losses",
                "goals_for",
                "goals_against",
                "goal_diff",
                "points",
                "points_per_match",
                config.TEAM_RATING_COL,
                "league_rank_rating",
                "perf_delta_rank",
                "rating_coverage",
            ]
        else:
            view = teams.sort_values("global_rank").copy()
            table_cols = [
                "global_rank",
                "team_name",
                "league",
                config.TEAM_RATING_COL,
                "league_rank_rating",
                "league_rank_points",
                "points_per_match",
                "perf_delta_rank",
                "market_value_total_eur",
                "club_elo",
                "rating_coverage",
            ]

        top_cols = st.columns(4)
        with top_cols[0]:
            st.metric("Teams", f"{len(view):,}")
        with top_cols[1]:
            avg_rating = view[config.TEAM_RATING_COL].mean()
            st.metric("Avg Rating", f"{avg_rating:.1f}" if pd.notna(avg_rating) else "—")
        with top_cols[2]:
            avg_ppm = view["points_per_match"].mean()
            st.metric("Avg Pts/Match", f"{avg_ppm:.2f}" if pd.notna(avg_ppm) else "—")
        with top_cols[3]:
            low_cov = int(view["low_coverage"].fillna(False).sum()) if "low_coverage" in view else 0
            st.metric("Low Coverage", f"{low_cov}")

        display = view[[c for c in table_cols if c in view.columns]].copy()
        if "rating_coverage" in display.columns:
            display["rating_coverage"] = display["rating_coverage"] * 100
        if "league" in display.columns:
            display["league"] = display["league"].map(league_badge)
        if "perf_delta_rank" in display.columns:
            display["performance"] = display["perf_delta_rank"].map(_fmt_delta)
            display.drop(columns=["perf_delta_rank"], inplace=True)
        if "low_coverage" in view.columns:
            display["coverage_flag"] = view["low_coverage"].map(lambda v: "Low" if bool(v) else "")

        rename = {c: team_label(c) for c in display.columns}
        rename.update({
            "team_name": "Team",
            "league": "League",
            "performance": "Performance",
            "coverage_flag": "Coverage",
        })
        display = display.rename(columns=rename)

        column_config = {
            "Team Rating": st.column_config.ProgressColumn(
                "Team Rating", min_value=0, max_value=100, format="%.1f"
            ),
            "Rating Coverage": st.column_config.ProgressColumn(
                "Rating Coverage", min_value=0, max_value=100, format="%.0f%%"
            ),
            "Pts / Match": st.column_config.NumberColumn("Pts / Match", format="%.2f"),
            "Squad Value (€)": st.column_config.NumberColumn("Squad Value (€)", format="€%,.0f"),
            "Club Elo": st.column_config.NumberColumn("Club Elo", format="%.0f"),
            "Performance": st.column_config.TextColumn("Performance"),
        }
        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            height=min(620, 80 + len(display) * 35),
            column_config=column_config,
        )

        st.markdown("---")
        scatter_df = view.dropna(subset=["points_per_match", config.TEAM_RATING_COL]).copy()
        if len(scatter_df) < 2:
            st.info("Not enough teams for the performance scatter.")
            return

        scatter_df["_delta_color"] = scatter_df["perf_delta_rank"].map(_delta_color)
        scatter_df["_league_label"] = scatter_df["league"].map(league_badge)
        scatter_df["_performance"] = scatter_df["perf_delta_rank"].map(_fmt_delta)

        fig = go.Figure(go.Scatter(
            x=scatter_df["points_per_match"],
            y=scatter_df[config.TEAM_RATING_COL],
            mode="markers+text",
            text=scatter_df["team_name"],
            textposition="top center",
            textfont=dict(size=10, color=D_TICK),
            marker=dict(
                size=13,
                color=scatter_df["_delta_color"],
                line=dict(width=1, color="rgba(255,255,255,0.35)"),
            ),
            customdata=scatter_df[[
                "team_name",
                "_league_label",
                "league_rank_points",
                "league_rank_rating",
                "_performance",
            ]],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[1]}<br>"
                "Pts/Match: %{x:.2f}<br>"
                "Team Rating: %{y:.1f}<br>"
                "Points Rank: #%{customdata[2]}<br>"
                "Rating Rank: #%{customdata[3]}<br>"
                "%{customdata[4]}<extra></extra>"
            ),
        ))

        fig.add_vline(
            x=float(scatter_df["points_per_match"].median()),
            line_dash="dot",
            line_color="rgba(255,255,255,0.25)",
        )
        fig.add_hline(
            y=float(scatter_df[config.TEAM_RATING_COL].median()),
            line_dash="dot",
            line_color="rgba(255,255,255,0.25)",
        )
        fig.update_layout(**dark_layout(
            height=520,
            xaxis=dict(title="Points per Match", gridcolor=D_GRID, color=D_TEXT),
            yaxis=dict(title="Team Rating", gridcolor=D_GRID, color=D_TEXT, range=[0, 100]),
            margin=dict(l=10, r=10, t=30, b=10),
        ))
        st.plotly_chart(fig, use_container_width=True)
