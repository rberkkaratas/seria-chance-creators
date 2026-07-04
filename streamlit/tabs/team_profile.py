"""Team Profile tab — one-club results, squad rating, style, and roster."""

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from tabs import TabRenderer
from core.models import AppState
from core.constants import team_label, league_badge
from core.theme import D_GRID, D_TEXT, D_TICK, dark_layout


def _fmt_eur(value) -> str:
    if pd.isna(value):
        return "—"
    value = float(value)
    if value >= 1_000_000_000:
        return f"€{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"€{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"€{value / 1_000:.0f}K"
    return f"€{value:.0f}"


def _fmt_delta(delta) -> tuple[str, str]:
    if pd.isna(delta):
        return "—", "#94a3b8"
    delta = int(delta)
    if delta < 0:
        return f"Over +{abs(delta)}", "#22c55e"
    if delta > 0:
        return f"Under {delta}", "#f87171"
    return "Par", "#94a3b8"


class TeamProfileTab(TabRenderer):
    def render(self, state: AppState) -> None:
        teams = state.teams_df.copy()
        st.markdown('<p class="section-title">Team Profile</p>', unsafe_allow_html=True)

        if teams.empty:
            st.info(
                "Team analytics file not found. Run "
                "`python -m src.features.team_features --season 2025-2026`."
            )
            return

        leagues = sorted(teams["league"].dropna().unique().tolist())
        league_col, team_col = st.columns([1, 2])
        with league_col:
            selected_league = st.selectbox(
                "League",
                options=leagues,
                format_func=league_badge,
                label_visibility="collapsed",
                key="team_profile_league",
            )
        league_df = teams[teams["league"] == selected_league].sort_values("team_name")
        with team_col:
            selected_team = st.selectbox(
                "Team",
                options=league_df["team_name"].tolist(),
                label_visibility="collapsed",
                key="team_profile_team",
            )

        row = league_df[league_df["team_name"] == selected_team].iloc[0]
        self._render_header(row)

        bar_col, style_col = st.columns([4, 5])
        with bar_col:
            self._render_group_ratings(row)
        with style_col:
            self._render_style_profile(row, league_df)

        st.markdown("---")
        self._render_roster(state, selected_league, selected_team)

    def _render_header(self, row: pd.Series) -> None:
        team_name = html.escape(str(row["team_name"]))
        league = league_badge(str(row["league"]))
        rating = row.get(config.TEAM_RATING_COL, np.nan)
        rating_str = f"{float(rating):.1f}" if pd.notna(rating) else "—"
        delta_label, delta_color = _fmt_delta(row.get("perf_delta_rank"))
        coverage = row.get("rating_coverage", np.nan)
        coverage_str = f"{float(coverage) * 100:.0f}%" if pd.notna(coverage) else "—"
        points_rank = row.get("league_rank_points")
        rating_rank = row.get("league_rank_rating")
        points_rank_str = f"#{int(points_rank)}" if pd.notna(points_rank) else "—"
        rating_rank_str = f"#{int(rating_rank)}" if pd.notna(rating_rank) else "—"
        ppm = row.get("points_per_match")
        ppm_str = f"{float(ppm):.2f}" if pd.notna(ppm) else "—"
        low_cov = bool(row.get("low_coverage", False))
        low_cov_html = (
            '<span style="background:#f59e0b22;color:#fbbf24;border:1px solid #f59e0b55;'
            'border-radius:4px;padding:2px 8px;font-size:0.74rem;font-weight:700">'
            "Low coverage</span>"
            if low_cov else ""
        )

        st.markdown(
            f'<div style="background:#1e293b;border-radius:8px;padding:18px 22px;'
            f'border-left:5px solid #0095FF;margin-bottom:16px">'
            f'<div style="display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap">'
            f'<div>'
            f'<h2 style="margin:0;color:#f1f5f9">{team_name}</h2>'
            f'<p style="margin:5px 0 0;color:#94a3b8">{league}'
            f' &nbsp;·&nbsp; {points_rank_str} points rank'
            f' &nbsp;·&nbsp; {rating_rank_str} rating rank {low_cov_html}</p>'
            f'</div>'
            f'<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">'
            f'<div style="text-align:center"><div style="color:#f1f5f9;font-size:1.5rem;'
            f'font-weight:800">{rating_str}</div><div style="color:#64748b;font-size:0.72rem">'
            f'Team Rating</div></div>'
            f'<div style="text-align:center"><div style="color:#f1f5f9;font-size:1.5rem;'
            f'font-weight:800">{ppm_str}</div>'
            f'<div style="color:#64748b;font-size:0.72rem">Pts / Match</div></div>'
            f'<div style="text-align:center"><div style="color:{delta_color};font-size:1.2rem;'
            f'font-weight:800">{delta_label}</div><div style="color:#64748b;font-size:0.72rem">'
            f'Performance</div></div>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )

        metric_cols = st.columns(5)
        values = [
            ("Record", f"{int(row['wins'])}-{int(row['draws'])}-{int(row['losses'])}"),
            ("Goals", f"{int(row['goals_for'])}-{int(row['goals_against'])}"),
            ("Squad Value", _fmt_eur(row.get("market_value_total_eur"))),
            ("Avg Age", f"{float(row['age_weighted']):.1f}" if pd.notna(row.get("age_weighted")) else "—"),
            ("Coverage", coverage_str),
        ]
        for col, (label, value) in zip(metric_cols, values):
            with col:
                st.metric(label, value)

    def _render_group_ratings(self, row: pd.Series) -> None:
        groups = ["DEF", "FB", "MID", "WING", "FW"]
        labels = ["DEF", "FB", "MID", "WING", "FW"]
        values = [row.get(f"rating_{group}", np.nan) for group in groups]
        text = ["—" if pd.isna(v) else f"{float(v):.0f}" for v in values]
        plot_values = [0 if pd.isna(v) else float(v) for v in values]
        colors = ["rgba(148,163,184,0.18)" if pd.isna(v) else "#0095FF" for v in values]

        st.markdown('<p class="section-title">Group Ratings</p>', unsafe_allow_html=True)
        fig = go.Figure(go.Bar(
            x=plot_values,
            y=labels,
            orientation="h",
            marker_color=colors,
            text=text,
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Rating: %{text}<extra></extra>",
        ))
        fig.update_layout(**dark_layout(
            height=320,
            xaxis=dict(range=[0, 105], gridcolor=D_GRID, color=D_TEXT),
            yaxis=dict(autorange="reversed", color=D_TEXT),
            margin=dict(l=10, r=45, t=10, b=10),
        ))
        st.plotly_chart(fig, use_container_width=True)

    def _render_style_profile(self, row: pd.Series, league_df: pd.DataFrame) -> None:
        metrics = [
            ("possession_share", False),
            ("passes_per_match", False),
            ("long_ball_share", False),
            ("ppda_proxy", True),
            ("possession_won_final_third_pm", False),
            ("ball_winning_height", False),
            ("crosses_pm", False),
            ("dribbles_pm", False),
            ("penalty_area_touches_pm", False),
        ]
        labels = []
        index_values = []
        hover = []
        for metric, lower_is_better in metrics:
            if metric not in league_df.columns or pd.isna(row.get(metric)):
                continue
            median = league_df[metric].median()
            value = row[metric]
            if pd.isna(median) or median == 0:
                continue
            idx = (median / value * 100) if lower_is_better and value else (value / median * 100)
            labels.append(team_label(metric))
            index_values.append(float(np.clip(idx, 0, 220)))
            hover.append(f"Team {value:.2f}<br>League median {median:.2f}")

        st.markdown('<p class="section-title">Style vs League Median</p>', unsafe_allow_html=True)
        if not labels:
            st.info("Style metrics unavailable for this team.")
            return

        fig = go.Figure(go.Bar(
            x=index_values,
            y=labels,
            orientation="h",
            marker_color=["#22c55e" if v >= 100 else "#f59e0b" for v in index_values],
            text=[f"{v:.0f}" for v in index_values],
            textposition="outside",
            customdata=hover,
            hovertemplate="<b>%{y}</b><br>Index: %{x:.0f}<br>%{customdata}<extra></extra>",
        ))
        fig.add_vline(x=100, line_dash="dot", line_color="rgba(255,255,255,0.35)")
        fig.update_layout(**dark_layout(
            height=360,
            xaxis=dict(title="League median = 100", gridcolor=D_GRID, color=D_TEXT),
            yaxis=dict(autorange="reversed", color=D_TEXT, tickfont=dict(size=11, color=D_TICK)),
            margin=dict(l=10, r=45, t=10, b=10),
        ))
        st.plotly_chart(fig, use_container_width=True)

    def _render_roster(self, state: AppState, league: str, team_name: str) -> None:
        st.markdown('<p class="section-title">Squad Table</p>', unsafe_allow_html=True)
        df = state.df.copy()
        if "league" in df.columns:
            df = df[df["league"] == league]
        df = df[df["team_name"] == team_name].copy()
        if df.empty:
            st.info("No player rows found for this team in the loaded player dataset.")
            return

        # Enriched rows are (player_id, position_group); show one row per
        # player — the group he played most minutes in — but keep every
        # qualified group visible in the Group column (dominant group first).
        df = df.sort_values(["player_id", "minutes_played"], ascending=[True, False])
        groups_by_player = df.groupby("player_id")[config.POSITION_GROUP_COL].agg(
            lambda g: " · ".join(dict.fromkeys(g))
        )
        df = (
            df.drop_duplicates("player_id")
            .sort_values(config.OVERALL_SCORE_COL, ascending=False)
        )
        df[config.POSITION_GROUP_COL] = df["player_id"].map(groups_by_player)
        cols = [
            "player_name",
            "position",
            config.POSITION_GROUP_COL,
            "age",
            "minutes_played",
            config.OVERALL_SCORE_COL,
            config.PRIMARY_ROLE_COL,
            "market_value_eur",
            "transfer_feasibility",
        ]
        display = df[[c for c in cols if c in df.columns]].copy()
        display = display.rename(columns={
            "player_name": "Player",
            "position": "Pos",
            config.POSITION_GROUP_COL: "Group",
            "age": "Age",
            "minutes_played": "Mins",
            config.OVERALL_SCORE_COL: "Overall Score",
            config.PRIMARY_ROLE_COL: "Role",
            "market_value_eur": "Market Value (€)",
            "transfer_feasibility": "Feasibility",
        })
        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            height=min(520, 80 + len(display) * 35),
            column_config={
                "Overall Score": st.column_config.ProgressColumn(
                    "Overall Score", min_value=0, max_value=100, format="%.1f"
                ),
                "Mins": st.column_config.NumberColumn("Mins", format="%d"),
                "Age": st.column_config.NumberColumn("Age", format="%d"),
                "Market Value (€)": st.column_config.NumberColumn("Market Value (€)", format="€%,.0f"),
            },
        )
