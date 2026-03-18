"""League Overview tab — cross-league tactical identity analysis."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import plotly.graph_objects as go
import streamlit as st

import config
from tabs import TabRenderer
from core.models import AppState
from core.constants import league_badge, role_color, LEAGUE_FLAGS, LEAGUE_DISPLAY, role_score_col
from core.theme import D_TEXT, D_GRID, D_TICK, dark_layout


class LeagueOverviewTab(TabRenderer):
    def render(self, state: AppState) -> None:
        df = state.df
        has_league_col = state.has_league_col
        has_roles = state.has_roles
        role_score_cols = state.role_score_cols
        all_roles = state.all_roles
        score_col = state.score_col

        # Access filter values from df + filtered for the overview mask
        # The overview uses full df filtered only by minutes/age/position
        # We re-apply the min_mins filter from the filtered df size as proxy
        # Actually we need to reconstruct the overview mask from state
        # The original code used: min_mins, age_range, selected_positions from sidebar
        # We reconstruct the broad overview from df with the same mins/age/position filters
        # stored in filtered's characteristics. Since AppState has no filter_state,
        # we reconstruct from df matching the broadest visible criteria.
        # Best approach: use filtered df but without league/team/role/feasibility filters.
        # We approximate by using state.filtered which has all filters applied.
        # For the league overview we need ov_df = df filtered by mins/age/pos only.
        # Since we don't store filter_state in AppState we derive from filtered stats.
        # Use filtered min minutes as lower bound on mins.
        _min_mins_used = int(state.filtered["minutes_played"].min()) if len(state.filtered) else 0

        if not has_league_col or not has_roles or not role_score_cols:
            st.info("League data not available. Run the multi-league pipeline first.")
            return

        # Use full df filtered only by minutes/age/position — not by league sidebar selection
        # Approximate the min_mins from the filter by looking at what's visible
        # Use all of df as the base for league overview (shows all players at default mins)
        # Apply the same mins filter as what filtered df used (minimum of filtered set)
        _ov_mask = df["minutes_played"] >= _min_mins_used
        ov_df = df[_ov_mask].copy()
        leagues_in_ov = sorted(ov_df["league"].dropna().unique().tolist())

        if len(leagues_in_ov) < 2:
            st.info("Load data for multiple leagues to see the League Overview.")
            return

        _lg_palette = {
            lg: c for lg, c in zip(
                leagues_in_ov,
                ["#0095FF", "#FF5252", "#00C896", "#FF9800", "#B450FF", "#FFC400"],
            )
        }
        _role_abbrev_lg = {
            "Creator":         "Creator",
            "Ball Progressor": "Progressor",
            "Box Threat":      "Box Threat",
            "Deep Builder":    "Deep Builder",
        }

        has_tm_data = "market_value_eur" in ov_df.columns
        import pandas as pd

        # Pre-compute per-league averages once
        _lg_avgs: dict[str, dict[str, float]] = {}
        _lg_mv_avgs: dict[str, float] = {}
        for _lg in leagues_in_ov:
            _lgdf = ov_df[ov_df["league"] == _lg]
            _lg_avgs[_lg] = {
                r: (_lgdf[role_score_col(r)].mean() if role_score_col(r) in _lgdf.columns else 0.0)
                for r in all_roles
            }
            if has_tm_data:
                _mv_vals = _lgdf["market_value_eur"].dropna()
                _lg_mv_avgs[_lg] = _mv_vals.mean() if len(_mv_vals) else 0.0

        # ── Header ──────────────────────────────────────────────────────────
        st.markdown('<p class="section-title">League Identity</p>', unsafe_allow_html=True)
        st.markdown(
            "Each of Europe's top five leagues has a distinct midfield character — shaped "
            "by tactical culture, coaching philosophy, and recruitment patterns. "
            "This page reveals those identities through the lens of four tactical roles."
        )
        st.markdown("<div style='margin:16px 0'></div>", unsafe_allow_html=True)

        # ── League identity cards ────────────────────────────────────────────
        _id_cols = st.columns(len(leagues_in_ov))
        for _ci, _lg in enumerate(leagues_in_ov):
            _avgs_lg  = _lg_avgs[_lg]
            _sorted_r = sorted(_avgs_lg.items(), key=lambda x: x[1], reverse=True)
            _top_role, _top_sc = _sorted_r[0]
            _r2, _r3  = _sorted_r[1][0], _sorted_r[2][0]
            _rc       = role_color(_top_role)
            _n_pl     = int((ov_df["league"] == _lg).sum())
            _avg_ov   = ov_df.loc[ov_df["league"] == _lg, score_col].mean() \
                        if score_col in ov_df.columns else 0
            with _id_cols[_ci]:
                st.markdown(
                    f'<div style="background:#1e293b;border-radius:10px;padding:16px;'
                    f'border-top:3px solid {_rc};text-align:center">'
                    f'<div style="font-size:1.8rem">{LEAGUE_FLAGS.get(_lg,"")}</div>'
                    f'<div style="font-size:0.88rem;font-weight:700;color:#f1f5f9;margin-top:6px">'
                    f'{LEAGUE_DISPLAY.get(_lg, _lg.replace("_"," "))}</div>'
                    f'<div style="margin:10px 0;padding:10px;background:{_rc}15;'
                    f'border-radius:8px;border:1px solid {_rc}30">'
                    f'<div style="color:{_rc};font-weight:700;font-size:0.85rem">'
                    f'{_top_role}</div>'
                    f'<div style="color:#64748b;font-size:0.72rem;margin-top:2px">'
                    f'dominant role · {_top_sc:.0f} avg</div>'
                    f'</div>'
                    f'<div style="font-size:0.75rem;color:#94a3b8;line-height:2">'
                    f'{_r2}<br>'
                    f'{_r3}</div>'
                    f'<div style="margin-top:10px;display:flex;justify-content:space-around;'
                    f'font-size:0.72rem">'
                    f'<span style="color:#64748b">{_n_pl} players</span>'
                    f'<span style="color:#94a3b8">avg OVR {_avg_ov:.0f}</span>'
                    f'</div>'
                    + (
                        f'<div style="margin-top:6px;font-size:0.71rem;color:#64748b">'
                        f'avg €{_lg_mv_avgs.get(_lg, 0)/1e6:.1f}M</div>'
                        if has_tm_data and _lg_mv_avgs.get(_lg, 0) > 0 else ""
                    ) +
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")

        # ── Role fingerprint heatmap ─────────────────────────────────────────
        st.markdown('<p class="section-title">Role Fingerprint by League</p>', unsafe_allow_html=True)
        st.caption(
            "Average role score across all qualified midfielders per league. "
            "★ marks the top league for each role."
        )
        _hm_roles   = [_role_abbrev_lg.get(r, r) for r in all_roles]
        _hm_leagues = [league_badge(_lg) for _lg in leagues_in_ov]
        _hm_z, _hm_text = [], []
        _role_max = {
            r: max(leagues_in_ov, key=lambda lg: _lg_avgs[lg].get(r, 0))
            for r in all_roles
        }
        for _lg in leagues_in_ov:
            _row_z, _row_t = [], []
            for r in all_roles:
                v = _lg_avgs[_lg].get(r, 0)
                _row_z.append(v)
                _row_t.append(f"{'★ ' if _role_max[r] == _lg else ''}{v:.1f}")
            _hm_z.append(_row_z)
            _hm_text.append(_row_t)

        fig_lg_hm = go.Figure(go.Heatmap(
            z=_hm_z,
            x=_hm_roles,
            y=_hm_leagues,
            text=_hm_text,
            texttemplate="%{text}",
            textfont=dict(size=13, color="#f1f5f9"),
            colorscale=[[0, "#0f172a"], [0.4, "#1e3a5f"], [1, "#0095FF"]],
            showscale=True,
            colorbar=dict(
                title=dict(text="Avg score", font=dict(color=D_TICK, size=11)),
                tickfont=dict(color=D_TICK, size=10),
                thickness=14, len=0.8,
                bgcolor="rgba(0,0,0,0)",
                outlinewidth=0,
            ),
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:.1f}<extra></extra>",
        ))
        fig_lg_hm.update_layout(**dark_layout(
            height=max(220, len(leagues_in_ov) * 56),
            xaxis=dict(tickfont=dict(size=12, color=D_TEXT), side="top", tickangle=-20),
            yaxis=dict(tickfont=dict(size=12, color=D_TEXT), autorange="reversed"),
            margin=dict(l=10, r=80, t=60, b=10),
        ))
        st.plotly_chart(fig_lg_hm, use_container_width=True)

        st.markdown("---")

        # ── League vs league — grouped bar ───────────────────────────────────
        st.markdown('<p class="section-title">Role Scores — League vs League</p>', unsafe_allow_html=True)
        st.caption("Average role score per league. Which league produces the strongest players in each archetype?")
        fig_lgbar = go.Figure()
        for _lg in leagues_in_ov:
            fig_lgbar.add_trace(go.Bar(
                name=league_badge(_lg),
                x=[_role_abbrev_lg.get(r, r) for r in all_roles],
                y=[_lg_avgs[_lg].get(r, 0) for r in all_roles],
                marker_color=_lg_palette[_lg],
                hovertemplate=f"<b>{league_badge(_lg)}</b><br>%{{x}}: %{{y:.1f}}<extra></extra>",
            ))
        fig_lgbar.update_layout(**dark_layout(
            barmode="group", height=360,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                font=dict(size=11, color=D_TEXT), bgcolor="rgba(0,0,0,0)",
            ),
            xaxis=dict(tickfont=dict(size=10, color=D_TEXT), tickangle=-20),
            yaxis=dict(
                title="Avg role score", range=[0, 80],
                gridcolor=D_GRID, color=D_TICK, dtick=20,
            ),
            margin=dict(l=10, r=10, t=50, b=10),
        ))
        st.plotly_chart(fig_lgbar, use_container_width=True)

        st.markdown("---")

        # ── Best player per role per league ─────────────────────────────────
        st.markdown('<p class="section-title">Best in Class — Top Player per Role per League</p>', unsafe_allow_html=True)
        st.caption(
            "The highest-scoring player for each role within each league. "
            "Only players whose **primary role** matches are included — scores reflect how well they fit that archetype."
        )
        import pandas as pd
        _best_rows = []
        for _role in all_roles:
            _sc_r = role_score_col(_role)
            _row  = {"Role": _role}
            for _lg in leagues_in_ov:
                _ldf = ov_df[
                    (ov_df["league"] == _lg) &
                    (ov_df.get(config.PRIMARY_ROLE_COL, pd.Series(dtype=str)) == _role)
                ] if config.PRIMARY_ROLE_COL in ov_df.columns else pd.DataFrame()
                if len(_ldf) > 0 and _sc_r in _ldf.columns:
                    _best = _ldf.nlargest(1, _sc_r).iloc[0]
                    _row[league_badge(_lg)] = f"{_best['player_name']} · {_best[_sc_r]:.0f}"
                else:
                    _row[league_badge(_lg)] = "—"
            _best_rows.append(_row)
        _best_df = pd.DataFrame(_best_rows).set_index("Role")
        st.dataframe(_best_df, use_container_width=True, hide_index=False)

        st.markdown("---")

        # ── Age profile by league ────────────────────────────────────────────
        if "age" in ov_df.columns:
            st.markdown('<p class="section-title">Age Profile by League</p>', unsafe_allow_html=True)
            st.caption("Distribution of midfielder ages per league — reveals which leagues trust young players vs. experienced ones.")
            fig_age = go.Figure()
            for _lg in leagues_in_ov:
                _ages = ov_df.loc[ov_df["league"] == _lg, "age"].dropna()
                fig_age.add_trace(go.Box(
                    y=_ages,
                    name=league_badge(_lg),
                    marker_color=_lg_palette[_lg],
                    boxmean="sd",
                    hovertemplate=f"<b>{league_badge(_lg)}</b><br>Age: %{{y}}<extra></extra>",
                ))
            fig_age.update_layout(**dark_layout(
                height=320,
                yaxis=dict(title="Age", gridcolor=D_GRID, color=D_TICK, dtick=2),
                xaxis=dict(tickfont=dict(size=12, color=D_TEXT)),
                margin=dict(l=10, r=10, t=20, b=10),
                showlegend=False,
            ))
            st.plotly_chart(fig_age, use_container_width=True)

        # ── Market value by league ───────────────────────────────────────────
        if has_tm_data and _lg_mv_avgs:
            st.markdown("---")
            st.markdown('<p class="section-title">Market Value by League</p>', unsafe_allow_html=True)
            st.caption("Average and median market value of qualified midfielders per league. Reflects squad investment and transfer market positioning.")
            _mv_leagues  = [league_badge(_lg) for _lg in leagues_in_ov]
            _mv_avgs_m   = [_lg_mv_avgs.get(_lg, 0) / 1e6 for _lg in leagues_in_ov]
            _mv_medians_m = []
            for _lg in leagues_in_ov:
                _mv_med = ov_df.loc[ov_df["league"] == _lg, "market_value_eur"].dropna().median()
                _mv_medians_m.append(_mv_med / 1e6 if pd.notna(_mv_med) else 0.0)
            fig_mv = go.Figure()
            fig_mv.add_trace(go.Bar(
                name="Average", x=_mv_leagues, y=_mv_avgs_m,
                marker_color=[_lg_palette[_lg] for _lg in leagues_in_ov],
                opacity=0.85,
                hovertemplate="<b>%{x}</b><br>Avg: €%{y:.1f}M<extra></extra>",
            ))
            fig_mv.add_trace(go.Scatter(
                name="Median", x=_mv_leagues, y=_mv_medians_m,
                mode="markers", marker=dict(symbol="diamond", size=10, color="#f1f5f9"),
                hovertemplate="<b>%{x}</b><br>Median: €%{y:.1f}M<extra></extra>",
            ))
            fig_mv.update_layout(**dark_layout(
                height=320, barmode="group",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                            font=dict(size=11, color=D_TEXT), bgcolor="rgba(0,0,0,0)"),
                xaxis=dict(tickfont=dict(size=12, color=D_TEXT)),
                yaxis=dict(title="Market value (€M)", gridcolor=D_GRID, color=D_TICK, tickprefix="€", ticksuffix="M"),
                margin=dict(l=10, r=10, t=50, b=10),
            ))
            st.plotly_chart(fig_mv, use_container_width=True)

