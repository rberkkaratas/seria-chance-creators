"""Explore tab — Lens Explorer + Statistical Profiles."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
from src.visualization.scatter_profiles import create_quadrant_scatter
from tabs import TabRenderer
from core.models import AppState
from core.constants import label, role_color, archetype_color, ARCHETYPE_COLORS, LEAGUE_FLAGS
from core.theme import D_TEXT, D_GRID, D_TICK, D_BG, dark_layout


# ── Preset scouting lenses ────────────────────────────────────────────────────
# Each lens pairs two metrics that together answer a specific scouting question.
LENSES = {
    "Creator":         {
        "x": "key_passes_p90",
        "y": "passes_into_penalty_area_p90",
        "question": "Who creates the most dangerous chances?",
        "elite_label": "Prolific creators",
    },
    "Ball Progressor": {
        "x": "successful_dribbles_p90",
        "y": "carries_into_final_third_p90",
        "question": "Who drives the team forward with the ball?",
        "elite_label": "Direct progressors",
    },
    "Box Threat": {
        "x": "shots_p90",
        "y": "penalty_area_touches_p90",
        "question": "Who lives in the box and creates direct goal threat?",
        "elite_label": "Box dominators",
    },
    "Deep Builder": {
        "x": "progressive_passes_p90",
        "y": "pass_accuracy",
        "question": "Who builds from deep with accuracy and intent?",
        "elite_label": "Reliable builders",
    },
"Wide Creator": {
        "x": "crosses_p90",
        "y": "passes_into_penalty_area_p90",
        "question": "Who delivers from wide and finds the box?",
        "elite_label": "Wide deliverers",
    },
    "Custom": None,
}


class ExploreTab(TabRenderer):
    def render(self, state: AppState) -> None:
        filtered       = state.filtered
        has_roles      = state.has_roles
        has_archetypes = state.has_archetypes
        has_league_col = state.has_league_col
        score_col      = state.score_col

        st.markdown('<p class="section-title">Scouting Explorer</p>', unsafe_allow_html=True)

        mode = st.radio(
            "View", ["Lens Explorer", "Statistical Profiles"],
            horizontal=True, label_visibility="collapsed",
        )

        # ── LENS EXPLORER ────────────────────────────────────────────────────
        if mode == "Lens Explorer":
            st.markdown(
                "Each lens pairs two metrics that together answer a specific scouting question. "
                "Use the **spotlight** to track any player across the plot.",
            )
            st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

            _rate_cols = [
                "pass_accuracy", "dribble_success_rate", "tackle_success_rate",
                "aerial_win_rate", "cross_accuracy", "forward_pass_pct",
            ]
            _p90_cols  = [c for c in filtered.columns if c.endswith("_p90")]
            _rate_dyn  = [c for c in _rate_cols if c in filtered.columns]
            all_metric_options = sorted(set(_p90_cols + _rate_dyn))

            if len(all_metric_options) < 2:
                st.warning("Not enough metrics available.")
                return

            # ── Controls row
            ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 2])

            valid_lenses = {
                k: v for k, v in LENSES.items()
                if k == "Custom" or (
                    v and v["x"] in filtered.columns and v["y"] in filtered.columns
                )
            }
            lens_name = ctrl1.selectbox(
                "Scouting lens", options=list(valid_lenses.keys()),
                help="Pre-built metric pairs that answer a specific question",
            )

            lens = valid_lenses[lens_name]

            if lens_name == "Custom":
                default_x = "key_passes_p90" if "key_passes_p90" in all_metric_options else all_metric_options[0]
                default_y = "passes_into_penalty_area_p90" if "passes_into_penalty_area_p90" in all_metric_options else all_metric_options[1]
                x_col = ctrl2.selectbox("X axis", all_metric_options,
                                        index=all_metric_options.index(default_x), format_func=label)
                y_col = ctrl3.selectbox("Y axis", all_metric_options,
                                        index=all_metric_options.index(default_y), format_func=label)
                question    = ""
                elite_label = "Elite"
            else:
                x_col       = lens["x"]
                y_col       = lens["y"]
                question    = lens["question"]
                elite_label = lens["elite_label"]
                size_options = ["(none)"] + all_metric_options
                size_sel     = ctrl2.selectbox(
                    "Bubble size", size_options,
                    format_func=lambda x: "None" if x == "(none)" else label(x),
                )
                size_col = None if size_sel == "(none)" else size_sel
                # spotlight in ctrl3 for preset lenses
                spotlight = ctrl3.text_input(
                    "Spotlight player", placeholder="e.g. Bellingham",
                    help="Highlights a player by surname",
                )

            if lens_name == "Custom":
                size_col  = None
                spotlight = ""

            # ── Lens question banner
            if question:
                rc = role_color(lens_name) if lens_name in config.ROLE_COLORS else "#0095FF"
                st.markdown(
                    f'<div style="background:{rc}12;border-left:3px solid {rc};'
                    f'border-radius:6px;padding:8px 14px;margin:8px 0 16px;'
                    f'font-size:0.83rem;color:#94a3b8">'
                    f'<span style="color:{rc};font-weight:700">{lens_name} lens</span>'
                    f' &nbsp;·&nbsp; {question}</div>',
                    unsafe_allow_html=True,
                )

            # ── Build figure
            color_col = config.PRIMARY_ROLE_COL if has_roles else ("archetype" if has_archetypes else "team_name")
            color_map = config.ROLE_COLORS if has_roles else (ARCHETYPE_COLORS if has_archetypes else None)

            x_med = filtered[x_col].median()
            y_med = filtered[y_col].median()
            x_min = max(0, filtered[x_col].min() * 0.92)
            y_min = max(0, filtered[y_col].min() * 0.92)
            x_max = filtered[x_col].max() * 1.05
            y_max = filtered[y_col].max() * 1.05

            fig = go.Figure()

            # Quadrant fills
            for x0, x1, y0, y1, fill in [
                (x_med, x_max, y_med, y_max, "rgba(0,230,120,0.07)"),
                (x_min, x_med, y_med, y_max, "rgba(255,200,0,0.05)"),
                (x_med, x_max, y_min, y_med, "rgba(0,149,255,0.04)"),
                (x_min, x_med, y_min, y_med, "rgba(255,255,255,0.01)"),
            ]:
                fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                              fillcolor=fill, line_width=0, layer="below")

            fig.add_vline(x=x_med, line_dash="dot", line_color="rgba(255,255,255,0.2)", line_width=1)
            fig.add_hline(y=y_med, line_dash="dot", line_color="rgba(255,255,255,0.2)", line_width=1)

            groups = filtered[color_col].dropna().unique() if color_col in filtered.columns else ["all"]
            _pal   = list((color_map or {}).values()) or px.colors.qualitative.Set2

            # Spotlight player lookup
            spotlight_name = spotlight.strip().lower() if spotlight else ""

            for gi, group in enumerate(sorted(groups)):
                sub = filtered[filtered[color_col] == group] if color_col in filtered.columns else filtered
                gc  = (color_map or {}).get(group, _pal[gi % len(_pal)])

                # Split spotlight from rest
                if spotlight_name:
                    in_spot = sub["player_name"].str.lower().str.contains(spotlight_name, na=False)
                    sub_bg  = sub[~in_spot]
                    sub_sp  = sub[in_spot]
                else:
                    sub_bg = sub
                    sub_sp = sub.iloc[0:0]

                def _marker_sizes(df_chunk):
                    if size_col and size_col in filtered.columns and filtered[size_col].max() > 0:
                        return (df_chunk[size_col] / filtered[size_col].max() * 30 + 8).clip(lower=8).tolist()
                    return [9] * len(df_chunk)

                def _hover(df_chunk):
                    league_flag = df_chunk["league"].map(LEAGUE_FLAGS).fillna("") if has_league_col and "league" in df_chunk.columns else [""] * len(df_chunk)
                    return list(zip(df_chunk["player_name"], df_chunk[score_col], df_chunk["team_name"], league_flag))

                # Background points
                if len(sub_bg):
                    fig.add_trace(go.Scatter(
                        x=sub_bg[x_col], y=sub_bg[y_col],
                        mode="markers", name=str(group),
                        marker=dict(size=_marker_sizes(sub_bg), color=gc, opacity=0.7,
                                    line=dict(width=0.5, color=D_BG)),
                        hovertemplate=(
                            "<b>%{customdata[0]}</b><br>"
                            f"{label(x_col)}: %{{x:.2f}}<br>"
                            f"{label(y_col)}: %{{y:.2f}}<br>"
                            "%{customdata[3]} %{customdata[2]}<extra></extra>"
                        ),
                        customdata=_hover(sub_bg),
                        showlegend=True,
                    ))

                # Spotlight points (larger, outlined, labeled)
                if len(sub_sp):
                    fig.add_trace(go.Scatter(
                        x=sub_sp[x_col], y=sub_sp[y_col],
                        mode="markers+text", name=f"{group} ★",
                        marker=dict(size=18, color=gc, opacity=1.0,
                                    line=dict(width=2, color="#ffffff")),
                        text=sub_sp["player_name"].str.split().str[-1],
                        textposition="top center",
                        textfont=dict(size=11, color="#f1f5f9"),
                        hovertemplate=(
                            "<b>%{customdata[0]}</b><br>"
                            f"{label(x_col)}: %{{x:.2f}}<br>"
                            f"{label(y_col)}: %{{y:.2f}}<extra></extra>"
                        ),
                        customdata=_hover(sub_sp),
                        showlegend=False,
                    ))

            # Annotate top-5 by the Y metric (most relevant for the current lens)
            top5 = filtered.nlargest(5, y_col)
            # Don't re-annotate spotlight players (already labeled)
            if spotlight_name:
                top5 = top5[~top5["player_name"].str.lower().str.contains(spotlight_name, na=False)]
            for _, r in top5.iterrows():
                fig.add_annotation(
                    x=r[x_col], y=r[y_col],
                    text=r["player_name"].split()[-1],
                    showarrow=True, arrowhead=2, arrowsize=0.8,
                    arrowcolor=D_TICK, ax=16, ay=-20,
                    font=dict(size=10, color=D_TEXT),
                    bgcolor="rgba(17,24,39,0.85)", borderpad=3,
                )

            # Quadrant corner labels
            fig.add_annotation(x=x_max * 0.99, y=y_max * 0.99, xanchor="right", yanchor="top",
                               text=elite_label or "Elite", showarrow=False,
                               font=dict(size=9, color="#22c55e"), opacity=0.7)
            fig.add_annotation(x=0.01, y=y_max * 0.99, xanchor="left", yanchor="top",
                               text=f"High {label(y_col)}", showarrow=False,
                               font=dict(size=9, color="#f59e0b"), opacity=0.6)

            fig.update_layout(**dark_layout(
                height=560,
                xaxis=dict(title=label(x_col), gridcolor=D_GRID, zeroline=False, color=D_TEXT, range=[x_min, x_max]),
                yaxis=dict(title=label(y_col), gridcolor=D_GRID, zeroline=False, color=D_TEXT, range=[y_min, y_max]),
                legend=dict(
                    title=dict(text=color_col.replace("_", " ").title(), font=dict(color=D_TICK, size=10)),
                    orientation="v", yanchor="top", y=1, xanchor="left", x=1.01,
                    font=dict(color=D_TEXT, size=10), bgcolor="rgba(0,0,0,0)",
                ),
                margin=dict(l=10, r=140, t=20, b=50),
            ))
            st.plotly_chart(fig, use_container_width=True)

            # ── Narrative insight ────────────────────────────────────────────
            import pandas as pd
            elite_df = filtered[(filtered[x_col] >= x_med) & (filtered[y_col] >= y_med)]
            n_elite  = len(elite_df)
            n_total  = len(filtered)

            if n_elite > 0:
                leader = elite_df.nlargest(1, y_col).iloc[0]
                l_name = leader["player_name"]
                l_team = leader.get("team_name", "")
                l_yval = leader[y_col]
                l_xval = leader[x_col]
                l_role = leader.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
                l_rc   = role_color(l_role) if l_role else "#0095FF"
                l_flag = LEAGUE_FLAGS.get(leader.get("league", ""), "") if has_league_col else ""

                insight = (
                    f'<b style="color:{l_rc}">{l_name}</b> ({l_flag} {l_team}) leads this lens — '
                    f'<b style="color:#f1f5f9">{l_yval:.2f}</b> {label(y_col)} · '
                    f'<b style="color:#f1f5f9">{l_xval:.2f}</b> {label(x_col)}. '
                    f'{n_elite} of {n_total} players ({n_elite/n_total*100:.0f}%) sit in the elite quadrant.'
                )
                st.markdown(
                    f'<div style="background:#1e293b;border-radius:8px;padding:12px 16px;'
                    f'font-size:0.83rem;color:#94a3b8;line-height:1.7;margin-top:4px">'
                    f'<span style="font-size:0.63rem;font-weight:700;color:#475569;'
                    f'text-transform:uppercase;letter-spacing:0.7px;margin-right:8px">Lens insight</span>'
                    f'{insight}</div>',
                    unsafe_allow_html=True,
                )

            # ── Top-10 table for this lens
            st.markdown("<div style='margin:16px 0 4px'></div>", unsafe_allow_html=True)
            st.markdown(f'<p class="section-title">Top 10 — {label(y_col)}</p>', unsafe_allow_html=True)
            _tbl_cols = ["player_name", "team_name", x_col, y_col]
            if has_roles and config.PRIMARY_ROLE_COL in filtered.columns:
                _tbl_cols.insert(2, config.PRIMARY_ROLE_COL)
            if has_league_col and "league" in filtered.columns:
                _tbl_cols.insert(2, "league")
            _tbl_cols = [c for c in _tbl_cols if c in filtered.columns]
            top10 = (
                filtered[_tbl_cols]
                .nlargest(10, y_col)
                .rename(columns={
                    "player_name": "Player", "team_name": "Team",
                    "league": "League", config.PRIMARY_ROLE_COL: "Role",
                    x_col: label(x_col), y_col: label(y_col),
                })
                .reset_index(drop=True)
            )
            top10.index += 1
            st.dataframe(top10, use_container_width=True)

        # ── STATISTICAL PROFILES ─────────────────────────────────────────────
        else:
            st.markdown(
                "Seven skill dimensions mapped across the full player pool. "
                "Solid lines mark the median — labelled players score highest in each view. "
                "Use the **Role filter** in the sidebar to zoom into a specific archetype."
            )
            st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

            SCATTER_PLOTS = [
                dict(
                    x_col="pass_accuracy", y_col="total_passes_p90",
                    x_label="Pass Accuracy (%)", y_label="Pass Attempts / 90",
                    title="Passing Volume & Accuracy",
                    insight="High-accuracy, high-volume passers are the engine room of build-up play.",
                    quadrant_labels={
                        "top_left":    "High volume,\nlow accuracy",
                        "top_right":   "Accurate\nvolume passer",
                        "bottom_left": "Low volume,\nlow accuracy",
                        "bottom_right":"Selective\nbut accurate",
                    },
                    best_quadrant="top_right",
                ),
                dict(
                    x_col="progressive_passes_p90", y_col="pass_accuracy",
                    x_label="Progressive Passes / 90", y_label="Pass Accuracy (%)",
                    title="Progressive Intent",
                    insight="The best deep builders combine forward ambition with the accuracy to execute it.",
                    quadrant_labels={
                        "top_left":    "Accurate but\nconservative",
                        "top_right":   "Accurate &\nprogressive",
                        "bottom_left": "Inaccurate,\nnot progressive",
                        "bottom_right":"Progressive but\nrisky",
                    },
                    best_quadrant="top_right",
                ),
                dict(
                    x_col="aerial_win_rate", y_col="aerials_total_p90",
                    x_label="Aerial Win Rate (%)", y_label="Aerial Attempts / 90",
                    title="Aerial Presence",
                    insight="Midfielders in the top-right win their duels consistently and contest them often — rare in creative profiles.",
                    quadrant_labels={
                        "top_left":    "High contest,\nlow win rate",
                        "top_right":   "Dominant\nin the air",
                        "bottom_left": "Avoids\naerials",
                        "bottom_right":"Selective,\nhigh win rate",
                    },
                    best_quadrant="top_right",
                ),
                dict(
                    x_col="clearances_p90", y_col="shots_blocked_p90",
                    x_label="Clearances / 90", y_label="Blocks / 90",
                    title="Defensive Contribution",
                    insight="Creative midfielders rarely appear here — look for dual-phase players who contribute in both directions.",
                    quadrant_labels={
                        "top_left":    "Shot-blocker,\nfew clearances",
                        "top_right":   "Active all-round\ndefender",
                        "bottom_left": "Limited\ndefensive output",
                        "bottom_right":"Clears often,\nfew blocks",
                    },
                    best_quadrant="top_right",
                ),
                dict(
                    x_col="possession_lost_p90", y_col="possession_won_p90",
                    x_label="Possession Lost / 90", y_label="Possession Won / 90",
                    title="Possession Battle",
                    insight="Top-left players win the ball frequently without giving it away — the ideal pressing midfielder profile.",
                    quadrant_labels={
                        "top_left":    "Ball winner,\nball secure",
                        "top_right":   "High\ninvolvement",
                        "bottom_left": "Low\ninvolvement",
                        "bottom_right":"Loses ball\noften",
                    },
                    best_quadrant="top_left",
                ),
                dict(
                    x_col="tackle_success_rate", y_col="tackles_p90",
                    x_label="Tackle Success Rate (%)", y_label="Tackle Attempts / 90",
                    title="Tackling",
                    insight="High volume + high success is rare — most ball-winners either tackle often or accurately, not both.",
                    quadrant_labels={
                        "top_left":    "Aggressive,\nlow success",
                        "top_right":   "High volume,\nhigh success",
                        "bottom_left": "Rarely\ntackles",
                        "bottom_right":"Selective &\naccurate",
                    },
                    best_quadrant="top_right",
                ),
                dict(
                    x_col="cross_accuracy", y_col="crosses_p90",
                    x_label="Cross Accuracy (%)", y_label="Cross Attempts / 90",
                    title="Crossing",
                    insight="Wide creators cluster top-right — volume crossers with accuracy are the rarest and most valuable deliverers.",
                    quadrant_labels={
                        "top_left":    "Frequent,\ninaccurate",
                        "top_right":   "Frequent &\naccurate",
                        "bottom_left": "Rarely\ncrosses",
                        "bottom_right":"Selective &\naccurate",
                    },
                    best_quadrant="top_right",
                ),
            ]

            _pipeline_warning_shown = False
            for row_start in range(0, len(SCATTER_PLOTS), 2):
                pair = SCATTER_PLOTS[row_start: row_start + 2]
                col_left, col_right = st.columns(2, gap="small")
                for col_widget, cfg in zip([col_left, col_right], pair):
                    with col_widget:
                        missing = [c for c in [cfg["x_col"], cfg["y_col"]] if c not in filtered.columns]
                        if missing:
                            if not _pipeline_warning_shown:
                                st.warning(
                                    f"Some columns are missing ({missing}). Re-run the pipeline:\n\n"
                                    "```bash\npython -m src.processing.build_tables\n"
                                    "python -m src.features.chance_creation\n```"
                                )
                                _pipeline_warning_shown = True
                        else:
                            fig = create_quadrant_scatter(
                                df=filtered,
                                x_col=cfg["x_col"], y_col=cfg["y_col"],
                                x_label=cfg["x_label"], y_label=cfg["y_label"],
                                title=cfg["title"],
                                quadrant_labels=cfg["quadrant_labels"],
                                best_quadrant=cfg["best_quadrant"],
                                top_n_annotate=5,
                                highlight_col=cfg["y_col"],
                                subtitle="Top 5 Leagues · 2025/26",
                                height=400,
                            )
                            st.plotly_chart(fig, use_container_width=True)
                            # Insight callout
                            st.markdown(
                                f'<div style="font-size:0.75rem;color:#475569;'
                                f'padding:0 4px 12px;line-height:1.5;font-style:italic">'
                                f'{cfg["insight"]}</div>',
                                unsafe_allow_html=True,
                            )
