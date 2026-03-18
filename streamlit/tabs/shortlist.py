"""Shortlist tab — ranked player list with bar chart and table."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import config
from tabs import TabRenderer
from core.models import AppState
from core.constants import (
    label, role_color, archetype_color, LEAGUE_FLAGS, LEAGUE_DISPLAY,
    role_score_col,
)
from core.theme import D_TEXT, D_GRID, D_TICK, dark_layout


class ShortlistTab(TabRenderer):
    def render(self, state: AppState) -> None:
        filtered = state.filtered
        has_roles = state.has_roles
        has_archetypes = state.has_archetypes
        has_league_col = state.has_league_col
        has_tm_data = state.has_tm_data
        score_col = state.score_col
        active_role_score_cols = state.active_role_score_cols
        all_roles = state.all_roles
        rename_map = state.rename_map
        role_score_cols = state.role_score_cols

        st.markdown('<p class="section-title">Midfielder Shortlist</p>', unsafe_allow_html=True)

        _active_rsc = active_role_score_cols

        # ── Sort pill buttons — Overall + per-role ─────────────────────────
        _sort_labels = ["Overall"] + [
            r for r in all_roles
            if role_score_col(r) in filtered.columns
        ]
        _sort_keys = [score_col] + [
            role_score_col(r) for r in all_roles
            if role_score_col(r) in filtered.columns
        ]
        _prev_label = st.session_state.get("sl_sort_label")
        _default_label = _prev_label if _prev_label in _sort_labels else _sort_labels[0]

        _selected_label = st.pills(
            "Sort shortlist by",
            options=_sort_labels,
            default=_default_label,
            key="sl_sort_pills",
            label_visibility="collapsed",
        )
        _sel = _selected_label if _selected_label in _sort_labels else _sort_labels[0]
        st.session_state["sl_sort_label"] = _sel
        sort_col = _sort_keys[_sort_labels.index(_sel)]
        # Strip leading emoji+space for chart hover labels
        sort_label_clean = _sel.split(" ", 1)[-1] if " " in _sel else _sel

        ranked = (
            filtered.sort_values(sort_col, ascending=False)
            .reset_index(drop=True)
        )

        # ── Top 3 podium cards ──
        if len(ranked) >= 1:
            podium = ranked.head(3)
            medals = ["🥇", "🥈", "🥉"]
            pod_cols = st.columns(3)
            for ci, (_, pr) in enumerate(podium.iterrows()):
                pr_role  = pr.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
                pr_rc    = role_color(pr_role) if pr_role else "#0095FF"
                pr_score = pr.get(sort_col, 0)
                pr_lg    = LEAGUE_FLAGS.get(pr.get("league", ""), "") if has_league_col else ""
                with pod_cols[ci]:
                    st.markdown(
                        f'<div style="background:#1e293b;border-radius:10px;padding:14px 16px;'
                        f'border-top:3px solid {pr_rc};text-align:center">'
                        f'<div style="font-size:1.4rem">{medals[ci]}</div>'
                        f'<div style="font-size:0.95rem;font-weight:700;color:#f1f5f9;margin-top:6px;'
                        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                        f'{pr["player_name"]}</div>'
                        f'<div style="font-size:0.78rem;color:#64748b;margin-top:2px">'
                        f'{pr_lg} {pr["team_name"]}</div>'
                        f'<div style="margin-top:8px">'
                        f'<span style="background:{pr_rc};color:white;border-radius:6px;'
                        f'padding:3px 10px;font-size:1.05rem;font-weight:700">{pr_score:.1f}</span>'
                        f'</div>'
                        f'<div style="font-size:0.75rem;color:{pr_rc};margin-top:5px">'
                        f'{pr_role}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            st.markdown("<div style='margin:12px 0'></div>", unsafe_allow_html=True)

        # ── Horizontal bar chart – top 25 ──
        top_n = ranked.head(25).copy()
        top_n["_rank"] = range(1, len(top_n) + 1)
        if has_league_col:
            top_n["rank_label"] = (
                "#" + top_n["_rank"].astype(str) + "  "
                + top_n["league"].map(lambda l: LEAGUE_FLAGS.get(l, "")) + " "
                + top_n["player_name"] + "  ·  " + top_n["team_name"]
            )
        else:
            top_n["rank_label"] = (
                "#" + top_n["_rank"].astype(str) + "  "
                + top_n["player_name"] + "  ·  " + top_n["team_name"]
            )

        bar_color = (
            top_n[config.PRIMARY_ROLE_COL].map(role_color)
            if has_roles and config.PRIMARY_ROLE_COL in top_n.columns
            else (top_n["archetype"].map(archetype_color) if has_archetypes and "archetype" in top_n.columns else "#007BFF")
        )

        # Background track at the axis max so bars read as fills
        _x_max  = float(top_n[sort_col].max()) * 1.18
        _x_avg  = float(ranked[sort_col].mean())
        _is_score = sort_col == score_col or sort_col in [role_score_col(r) for r in all_roles]
        _track_max = 100.0 if _is_score else _x_max

        fig_bar = go.Figure()

        # Grey background tracks
        fig_bar.add_trace(go.Bar(
            x=[_track_max] * len(top_n),
            y=top_n["rank_label"],
            orientation="h",
            marker_color="rgba(255,255,255,0.05)",
            marker_line_width=0,
            showlegend=False,
            hoverinfo="skip",
        ))

        # Colored value bars
        fig_bar.add_trace(go.Bar(
            x=top_n[sort_col],
            y=top_n["rank_label"],
            orientation="h",
            marker_color=bar_color,
            marker_line_width=0,
            text=[f"{v:.1f}" for v in top_n[sort_col]],
            textposition="outside",
            textfont=dict(size=11, color=D_TEXT),
            cliponaxis=False,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Team: %{customdata[1]}<br>"
                "League: %{customdata[3]}<br>"
                f"{sort_label_clean}: %{{x:.2f}}<br>"
                "Overall Score: %{customdata[2]:.1f}<extra></extra>"
            ),
            customdata=top_n[["player_name", "team_name", score_col,
                               "league" if has_league_col else "team_name"]].values,
            showlegend=False,
        ))

        # Average reference line
        fig_bar.add_vline(
            x=_x_avg,
            line_dash="dot",
            line_color="rgba(255,255,255,0.30)",
            line_width=1.5,
            annotation_text=f"avg {_x_avg:.1f}",
            annotation_position="top",
            annotation_font=dict(size=10, color=D_TICK),
        )

        fig_bar.update_layout(**dark_layout(
            barmode="overlay",
            height=max(400, len(top_n) * 32),
            yaxis=dict(
                autorange="reversed",
                tickfont=dict(size=11, color=D_TEXT),
                ticklabeloverflow="allow",
            ),
            xaxis=dict(
                title=sort_label_clean,
                gridcolor=D_GRID,
                color=D_TEXT,
                range=[0, _track_max * 1.12],
                showgrid=False,
            ),
            margin=dict(l=10, r=60, t=20, b=30),
        ))
        bar_event = st.plotly_chart(fig_bar, use_container_width=True, on_select="rerun")

        if bar_event.selection.points:
            clicked_player = bar_event.selection.points[0]["customdata"][0]
            st.session_state["profile_player"] = clicked_player
            components.html("""
                <script>
                    const tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
                    for (const tab of tabs) {
                        if (tab.innerText.includes('Scout Report')) {
                            tab.click();
                            break;
                        }
                    }
                </script>
            """, height=0)

        # ── Full table ──
        st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)
        st.caption(f"Showing {len(ranked)} players · sorted by {sort_label_clean} · click a bar above to open the Scout Report")

        display_cols = ["player_name", "team_name"]
        if has_league_col:
            display_cols.append("league")
        display_cols += ["position", "age", "minutes_played"]
        if has_roles:
            display_cols.append(config.PRIMARY_ROLE_COL)
        elif has_archetypes:
            display_cols.append("archetype")
        display_cols += [score_col] + [c for c in role_score_cols if c in ranked.columns]
        if has_tm_data:
            display_cols += ["market_value_eur", "contract_expires", "transfer_feasibility"]
        available_cols = [c for c in display_cols if c in ranked.columns]

        tbl = ranked[available_cols].copy()
        tbl.index = range(1, len(tbl) + 1)
        if has_league_col:
            tbl["league"] = tbl["league"].map(lambda l: f"{LEAGUE_FLAGS.get(l,'')} {LEAGUE_DISPLAY.get(l, l.replace('_',' '))}")
        if has_roles and config.PRIMARY_ROLE_COL in tbl.columns:
            tbl[config.PRIMARY_ROLE_COL] = tbl[config.PRIMARY_ROLE_COL].map(
                lambda r: r if pd.notna(r) else r
            )
        tbl_rename = {
            **rename_map,
            "market_value_eur":    "Market Value (€)",
            "contract_expires":    "Contract Until",
            "transfer_feasibility": "Feasibility",
        }
        tbl_display = tbl.rename(columns=tbl_rename)

        col_cfg = {
            "Overall Score":          st.column_config.NumberColumn("Overall Score", format="%.1f"),
            "Mins":              st.column_config.NumberColumn("Mins", format="%d"),
            "Age":               st.column_config.NumberColumn("Age",  format="%d"),
            "Market Value (€)":  st.column_config.NumberColumn("Market Value (€)", format="%,.0f"),
            "Contract Until":    st.column_config.NumberColumn("Contract Until", format="%d"),
        }
        for r in all_roles:
            col_cfg[r] = st.column_config.NumberColumn(r, format="%.0f")
        st.dataframe(tbl_display, use_container_width=True, height=440, column_config=col_cfg)
