"""Role Map tab — creation role taxonomy, distribution, and DNA."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import plotly.graph_objects as go
import streamlit as st

import config
from tabs import TabRenderer
from core.models import AppState
from core.constants import label, role_color, LEAGUE_FLAGS, role_score_col, ROLE_DESCRIPTIONS
from core.theme import D_TEXT, D_GRID, D_TICK, dark_layout


class RoleMapTab(TabRenderer):
    def render(self, state: AppState) -> None:
        filtered = state.filtered
        has_roles = state.has_roles
        has_league_col = state.has_league_col
        has_league_scores = state.has_league_scores
        all_roles = state.all_roles
        role_score_cols = state.role_score_cols
        active_pct_suffix = state.active_pct_suffix
        all_leagues = state.all_leagues

        # ── Zone taxonomy ──────────────────────────────────────────────────
        _PITCH_ZONES = {
            "Deep Builder":    "Deep",
            "Ball Progressor": "Dynamic",
            "Creator":         "Advanced",
            "Box Threat":      "Advanced",
        }
        _ZONE_COLORS = {
            "Deep":     "#FF9800",
            "Dynamic":  "#00C896",
            "Advanced": "#0095FF",
        }
        _ZONE_LABELS = {
            "Deep":     "Deep — builds from the back third",
            "Dynamic":  "Dynamic — drives through midfield",
            "Advanced": "Advanced — creates and threatens in the final third",
        }
        _ZONE_ORDER  = ["Deep", "Dynamic", "Advanced"]
        _ROLE_ABBREV = {
            "Creator":         "Creator",
            "Ball Progressor": "Progressor",
            "Box Threat":      "Box Threat",
            "Deep Builder":    "Deep Builder",
        }

        # ── Header ──────────────────────────────────────────────────────────
        st.markdown('<p class="section-title">Creation Role Taxonomy</p>', unsafe_allow_html=True)
        st.markdown(
            "Four creation-focused roles cover every way a midfielder can generate chances — "
            "from the deep builder to the box threat. Each player is scored 0–100 "
            "per role based on weighted percentile ranks of its defining metrics, and assigned "
            "a **primary role** where they score highest."
        )
        st.markdown("<div style='margin:20px 0 4px'></div>", unsafe_allow_html=True)

        has_tm_data = "market_value_eur" in filtered.columns
        import pandas as pd

        # ── Role cards — single row ──────────────────────────────────────────
        # Compute uniform card height from the role with the most metrics so all cards match.
        _max_metrics = max(len(w) for w in config.ROLE_WEIGHTS.values())
        _card_min_h  = 240 + _max_metrics * 26   # base + 26px per metric bar
        _card_cols = st.columns(len(all_roles))
        for _ci, _role in enumerate(all_roles):
            _rc    = role_color(_role)
            _desc  = ROLE_DESCRIPTIONS.get(_role, "")
            _zone  = _PITCH_ZONES.get(_role, "")
            _zc    = _ZONE_COLORS.get(_zone, "#64748b")
            _weights = config.ROLE_WEIGHTS.get(_role, {})

            _n = int((filtered[config.PRIMARY_ROLE_COL] == _role).sum()) \
                 if has_roles and config.PRIMARY_ROLE_COL in filtered.columns else 0
            _avg = filtered.loc[
                filtered[config.PRIMARY_ROLE_COL] == _role, role_score_col(_role)
            ].mean() if _n > 0 and role_score_col(_role) in filtered.columns else 0

            _mv_avg_str = ""
            if has_tm_data and _n > 0:
                _mv_vals = filtered.loc[
                    filtered[config.PRIMARY_ROLE_COL] == _role, "market_value_eur"
                ].dropna()
                if len(_mv_vals):
                    _mv_avg_str = f"€{_mv_vals.mean()/1e6:.1f}M"

            # Build metric weight bars (bar width = weight × 100%)
            _bars_html = ""
            for _m, _w in _weights.items():
                _bar_w = int(_w * 100)
                _bars_html += (
                    f'<div style="margin-bottom:7px">'
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:3px">'
                    f'<span style="font-size:0.67rem;color:#94a3b8;white-space:nowrap;'
                    f'overflow:hidden;text-overflow:ellipsis;max-width:80%">{label(_m)}</span>'
                    f'<span style="font-size:0.63rem;color:{_rc};opacity:0.8;font-weight:600">'
                    f'{int(_w*100)}%</span>'
                    f'</div>'
                    f'<div style="background:#0f172a;border-radius:2px;height:3px">'
                    f'<div style="background:{_rc};border-radius:2px;height:3px;'
                    f'width:{_bar_w}%;opacity:0.85"></div>'
                    f'</div>'
                    f'</div>'
                )

            _stats_html = (
                f'<span style="font-size:0.71rem;color:#64748b">{_n} players</span>'
                f'<span style="font-size:0.71rem;color:{_rc};font-weight:700">avg {_avg:.0f}</span>'
                + (f'<span style="font-size:0.71rem;color:#475569">{_mv_avg_str}</span>' if _mv_avg_str else "")
            )

            with _card_cols[_ci]:
                st.markdown(
                    f'<div style="background:#1e293b;border-radius:12px;padding:18px 16px;'
                    f'border-left:4px solid {_rc};min-height:{_card_min_h}px;'
                    f'display:flex;flex-direction:column">'
                    # ── title row
                    f'<div style="display:flex;justify-content:space-between;'
                    f'align-items:flex-start;margin-bottom:10px">'
                    f'<span style="font-size:1rem;font-weight:800;color:{_rc}">{_role}</span>'
                    f'<span style="background:{_zc}18;color:{_zc};border:1px solid {_zc}33;'
                    f'border-radius:4px;padding:2px 7px;font-size:0.60rem;font-weight:700;'
                    f'text-transform:uppercase;letter-spacing:0.7px;white-space:nowrap">{_zone}</span>'
                    f'</div>'
                    # ── description
                    f'<p style="margin:0 0 14px;font-size:0.74rem;color:#64748b;'
                    f'line-height:1.55">{_desc}</p>'
                    # ── weight bars
                    f'<div style="font-size:0.60rem;font-weight:700;color:#334155;'
                    f'text-transform:uppercase;letter-spacing:0.7px;margin-bottom:8px">'
                    f'Role weight</div>'
                    f'{_bars_html}'
                    # ── stats footer (pushed to bottom via flex margin-top:auto)
                    f'<div style="border-top:1px solid #1e3a5f;margin-top:auto;padding-top:10px;'
                    f'display:flex;justify-content:space-between;align-items:center">'
                    f'{_stats_html}'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        if has_roles and role_score_cols and len(filtered):

            st.markdown("---")

            # ── Distribution + Versatility Matrix ──────────────────────────
            st.markdown('<p class="section-title">Who plays what?</p>', unsafe_allow_html=True)
            st.caption("Role distribution across the filtered player pool, and how specialised each group is.")

            col_donut, col_heat = st.columns([1, 2])

            with col_donut:
                _counts = filtered[config.PRIMARY_ROLE_COL].value_counts().reindex(all_roles, fill_value=0)
                _total  = int(_counts.sum())
                fig_donut = go.Figure(go.Pie(
                    labels=_counts.index,
                    values=_counts.values,
                    hole=0.6,
                    marker_colors=[role_color(r) for r in _counts.index],
                    textinfo="percent",
                    textposition="outside",
                    hovertemplate="<b>%{label}</b><br>%{value} players · %{percent}<extra></extra>",
                    pull=[0.05 if v == _counts.max() else 0 for v in _counts.values],
                ))
                fig_donut.add_annotation(
                    text=f"<b>{_total}</b><br><span style='font-size:10px;color:#64748b'>players</span>",
                    x=0.5, y=0.5, xref="paper", yref="paper",
                    showarrow=False, font=dict(color="#f1f5f9", size=20), align="center",
                )
                fig_donut.update_layout(**dark_layout(
                    height=360, showlegend=True,
                    legend=dict(
                        orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02,
                        font=dict(size=9, color=D_TEXT), bgcolor="rgba(0,0,0,0)",
                    ),
                    margin=dict(l=10, r=150, t=20, b=20),
                    title=dict(text="Role Distribution", font=dict(size=12, color=D_TICK), x=0),
                ))
                st.plotly_chart(fig_donut, use_container_width=True)

            with col_heat:
                _active_roles = [r for r in all_roles if (filtered[config.PRIMARY_ROLE_COL] == r).any()]
                _heat_z, _heat_text = [], []
                for _r in _active_roles:
                    _sub  = filtered[filtered[config.PRIMARY_ROLE_COL] == _r]
                    _vals = [
                        round(_sub[role_score_col(r2)].mean(), 1)
                        if role_score_col(r2) in _sub.columns else 0.0
                        for r2 in _active_roles
                    ]
                    _heat_z.append(_vals)
                    _heat_text.append([f"{v:.0f}" for v in _vals])
                _abbrevs = [_ROLE_ABBREV.get(r, r) for r in _active_roles]
                fig_matrix = go.Figure(go.Heatmap(
                    z=_heat_z, x=_abbrevs, y=_abbrevs,
                    colorscale=[[0,"#0d1117"],[0.35,"#1e3a5f"],[0.7,"#0095FF"],[1.0,"#00d4aa"]],
                    zmin=0, zmax=100,
                    text=_heat_text, texttemplate="%{text}",
                    textfont=dict(size=10, color="#f1f5f9"),
                    hovertemplate="<b>%{y}</b> players avg <b>%{x}</b> score: %{z:.1f}<extra></extra>",
                    showscale=False,
                ))
                fig_matrix.update_layout(**dark_layout(
                    height=360,
                    xaxis=dict(
                        title="Scored as →", tickfont=dict(size=9, color=D_TEXT), tickangle=-30,
                    ),
                    yaxis=dict(
                        title="Primary role ↓", tickfont=dict(size=9, color=D_TEXT), autorange="reversed",
                    ),
                    margin=dict(l=10, r=10, t=44, b=10),
                    title=dict(
                        text="Role Versatility Matrix — bright diagonal = highly specialised",
                        font=dict(size=11, color=D_TICK), x=0,
                    ),
                ))
                st.plotly_chart(fig_matrix, use_container_width=True)

            st.markdown("---")

            # ── Role DNA heatmap ────────────────────────────────────────────
            st.markdown('<p class="section-title">Role DNA — what makes each role tick?</p>', unsafe_allow_html=True)
            st.caption(
                "Average percentile rank of every metric used across all 9 roles, grouped by primary role. "
                "Bright cells show where each archetype genuinely excels — dark cells reveal where they don't."
            )

            _all_dna_metrics = list(dict.fromkeys(
                m for weights in config.ROLE_WEIGHTS.values() for m in weights
            ))
            _dna_labels = [label(m) for m in _all_dna_metrics]
            _dna_z, _dna_y = [], []
            for _role in all_roles:
                _rp = filtered[filtered[config.PRIMARY_ROLE_COL] == _role]
                if len(_rp) == 0:
                    continue
                _dna_y.append(_role)
                _dna_z.append([
                    round(_rp[f"{m}{active_pct_suffix}"].mean(), 1)
                    if f"{m}{active_pct_suffix}" in _rp.columns else 0.0
                    for m in _all_dna_metrics
                ])

            fig_dna = go.Figure(go.Heatmap(
                z=_dna_z, x=_dna_labels, y=_dna_y,
                colorscale=[[0,"#0d1117"],[0.3,"#0c2a4a"],[0.6,"#0095FF"],[1.0,"#00d4aa"]],
                zmin=0, zmax=100,
                hovertemplate="<b>%{y}</b><br>%{x}: %{z:.0f}th pct<extra></extra>",
                colorbar=dict(
                    thickness=12, len=0.85,
                    tickfont=dict(color=D_TICK, size=9),
                    title=dict(text="Pct", font=dict(color=D_TICK, size=10), side="right"),
                ),
            ))
            fig_dna.update_layout(**dark_layout(
                height=max(300, len(_dna_y) * 36),
                xaxis=dict(tickfont=dict(size=9, color=D_TEXT), tickangle=-40),
                yaxis=dict(tickfont=dict(size=10, color=D_TEXT), autorange="reversed"),
                margin=dict(l=10, r=80, t=44, b=100),
                title=dict(
                    text="Role DNA — avg metric percentile among players assigned to each role",
                    font=dict(size=11, color=D_TICK), x=0,
                ),
            ))
            st.plotly_chart(fig_dna, use_container_width=True)

            st.markdown("---")

            # ── Role share by league (% stacked bar) ───────────────────────
            if has_league_col and filtered["league"].nunique() > 1:
                st.markdown('<p class="section-title">Role Share by League</p>', unsafe_allow_html=True)
                st.caption("What percentage of each league's midfielders fall into each role? Reveals each league's tactical identity.")

                import pandas as pd
                _lr_rows = []
                for _lg in all_leagues:
                    _lg_df   = filtered[filtered["league"] == _lg]
                    _lg_tot  = max(len(_lg_df), 1)
                    for _role in all_roles:
                        _n_role = int((_lg_df[config.PRIMARY_ROLE_COL] == _role).sum())
                        _lr_rows.append({
                            "league_badge": self._league_badge(_lg),
                            "role": _role,
                            "pct": round(_n_role / _lg_tot * 100, 1),
                            "count": _n_role,
                        })
                _lr_df = pd.DataFrame(_lr_rows)

                fig_lr = go.Figure()
                for _role in all_roles:
                    _rs = _lr_df[_lr_df["role"] == _role]
                    fig_lr.add_trace(go.Bar(
                        name=_role,
                        x=_rs["league_badge"].tolist(),
                        y=_rs["pct"].tolist(),
                        marker_color=role_color(_role),
                        text=[f"{v:.0f}%" if v >= 5 else "" for v in _rs["pct"]],
                        textposition="inside",
                        textfont=dict(size=9),
                        hovertemplate=(
                            f"<b>{_role}</b><br>%{{x}}: %{{y:.1f}}% · %{{customdata}} players<extra></extra>"
                        ),
                        customdata=_rs["count"].tolist(),
                    ))
                fig_lr.update_layout(**dark_layout(
                    barmode="stack", height=340,
                    legend=dict(
                        orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                        font=dict(size=9, color=D_TEXT), bgcolor="rgba(0,0,0,0)",
                    ),
                    xaxis=dict(tickfont=dict(size=12, color=D_TEXT)),
                    yaxis=dict(
                        title="% of league midfielders", ticksuffix="%",
                        gridcolor=D_GRID, color=D_TEXT, range=[0, 101],
                    ),
                    margin=dict(l=10, r=10, t=50, b=10),
                    title=dict(
                        text="Which leagues over-index on each role?",
                        font=dict(size=11, color=D_TICK), x=0,
                    ),
                ))
                st.plotly_chart(fig_lr, use_container_width=True)
                st.markdown("---")

            # ── Top players per role, grouped by zone ──────────────────────
            st.markdown('<p class="section-title">Top Players by Role</p>', unsafe_allow_html=True)

            for _zone in _ZONE_ORDER:
                _zr = [r for r in all_roles
                       if _PITCH_ZONES.get(r) == _zone
                       and has_roles
                       and (filtered[config.PRIMARY_ROLE_COL] == r).any()]
                if not _zr:
                    continue
                _zc = _ZONE_COLORS[_zone]
                st.markdown(
                    f'<div style="margin:16px 0 8px">'
                    f'<span style="background:{_zc}22;color:{_zc};border:1px solid {_zc}44;'
                    f'border-radius:6px;padding:2px 10px;font-size:0.72rem;font-weight:700;'
                    f'text-transform:uppercase;letter-spacing:0.8px">{_zone}</span>'
                    f'<span style="color:#94a3b8;font-size:0.8rem;margin-left:8px">'
                    f'{_ZONE_LABELS[_zone]}</span></div>',
                    unsafe_allow_html=True,
                )
                _zcols = st.columns(len(_zr))
                for _ci, _role in enumerate(_zr):
                    _rc      = role_color(_role)
                    _sc_col  = role_score_col(_role)
                    _rp_top  = (
                        filtered[filtered[config.PRIMARY_ROLE_COL] == _role]
                        .sort_values(_sc_col, ascending=False)
                        .head(8)
                    )
                    with _zcols[_ci]:
                        st.markdown(
                            f'<p style="margin:0 0 8px;font-size:0.85rem;font-weight:700;color:{_rc}">'
                            f'{_role}</p>',
                            unsafe_allow_html=True,
                        )
                        for _, _pr in _rp_top.iterrows():
                            _ps   = float(_pr.get(_sc_col, 0) or 0)
                            _flag = LEAGUE_FLAGS.get(_pr.get("league", ""), "") if has_league_col else ""
                            st.markdown(
                                f'<div style="margin-bottom:7px">'
                                f'<div style="display:flex;justify-content:space-between;'
                                f'align-items:baseline;margin-bottom:2px">'
                                f'<span style="font-size:0.78rem;color:#e2e8f0;white-space:nowrap;'
                                f'overflow:hidden;text-overflow:ellipsis;max-width:74%">'
                                f'{_flag} {_pr["player_name"]}</span>'
                                f'<span style="font-size:0.74rem;color:{_rc};font-weight:600">'
                                f'{_ps:.0f}</span></div>'
                                f'<div style="background:#1e293b;border-radius:3px;height:3px">'
                                f'<div style="background:{_rc};border-radius:3px;height:3px;'
                                f'width:{int(_ps)}%"></div></div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                st.markdown("<div style='margin-bottom:4px'></div>", unsafe_allow_html=True)

            # ── Role score vs market value scatter ──────────────────────────
            if has_tm_data:
                _scatter_df = filtered[
                    filtered["market_value_eur"].notna() &
                    filtered[config.PRIMARY_ROLE_COL].notna()
                ].copy()
                _scatter_df = _scatter_df[_scatter_df[config.PRIMARY_ROLE_COL].isin(all_roles)]

                if len(_scatter_df) >= 5:
                    st.markdown("---")
                    st.markdown('<p class="section-title">Role Score vs Market Value</p>', unsafe_allow_html=True)
                    st.caption(
                        "Each dot is a player scored against their primary role. "
                        "Top-left = high performance, low cost — the undervalued quadrant."
                    )

                    fig_mv_scatter = go.Figure()
                    for _r in all_roles:
                        _rdf = _scatter_df[_scatter_df[config.PRIMARY_ROLE_COL] == _r]
                        if _rdf.empty:
                            continue
                        _rc      = role_color(_r)
                        _sc_col  = role_score_col(_r)
                        _scores  = _rdf[_sc_col].fillna(0) if _sc_col in _rdf.columns else pd.Series(0, index=_rdf.index)
                        _mv_m    = _rdf["market_value_eur"] / 1e6
                        _flag    = _rdf["league"].map(LEAGUE_FLAGS).fillna("") if has_league_col else pd.Series("", index=_rdf.index)
                        _hover   = (
                            "<b>%{customdata[0]}</b><br>"
                            "%{customdata[1]} %{customdata[2]}<br>"
                            f"{_r}: " + "%{y:.0f}<br>"
                            "€%{x:.1f}M<extra></extra>"
                        )
                        fig_mv_scatter.add_trace(go.Scatter(
                            x=_mv_m,
                            y=_scores,
                            mode="markers",
                            name=_r,
                            marker=dict(color=_rc, size=7, opacity=0.75,
                                        line=dict(width=0.5, color="#0f172a")),
                            customdata=list(zip(
                                _rdf["player_name"],
                                _flag,
                                _rdf["team_name"],
                            )),
                            hovertemplate=_hover,
                        ))

                    # Median lines
                    _med_mv  = _scatter_df["market_value_eur"].median() / 1e6
                    _med_sc  = _scatter_df.apply(
                        lambda r: r.get(role_score_col(r[config.PRIMARY_ROLE_COL]), 0) or 0, axis=1
                    ).median()
                    for _mv_line in [_med_mv]:
                        fig_mv_scatter.add_vline(
                            x=_mv_line, line=dict(color="#334155", width=1, dash="dot"),
                        )
                    fig_mv_scatter.add_hline(
                        y=_med_sc, line=dict(color="#334155", width=1, dash="dot"),
                    )
                    # Quadrant labels
                    _x_max = (_scatter_df["market_value_eur"].max() / 1e6) * 1.05
                    fig_mv_scatter.add_annotation(
                        x=0, y=100, xanchor="left", yanchor="top", showarrow=False,
                        text="Undervalued", font=dict(size=9, color="#22c55e"), opacity=0.6,
                    )
                    fig_mv_scatter.add_annotation(
                        x=_x_max, y=100, xanchor="right", yanchor="top", showarrow=False,
                        text="Elite", font=dict(size=9, color="#94a3b8"), opacity=0.6,
                    )
                    fig_mv_scatter.add_annotation(
                        x=0, y=0, xanchor="left", yanchor="bottom", showarrow=False,
                        text="Underperforming", font=dict(size=9, color="#94a3b8"), opacity=0.6,
                    )

                    fig_mv_scatter.update_layout(**dark_layout(
                        height=420,
                        xaxis=dict(title="Market value (€M)", gridcolor=D_GRID, color=D_TICK,
                                   tickprefix="€", ticksuffix="M"),
                        yaxis=dict(title="Role score", range=[0, 105], gridcolor=D_GRID,
                                   color=D_TICK, dtick=25),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                                    font=dict(size=11, color=D_TEXT), bgcolor="rgba(0,0,0,0)"),
                        margin=dict(l=10, r=10, t=50, b=10),
                    ))
                    st.plotly_chart(fig_mv_scatter, use_container_width=True)

        else:
            st.info(
                "Role scores are not available yet. Re-run the pipeline:\n\n"
                "```bash\n"
                "python -m src.features.chance_creation\n"
                "```"
            )

    def _league_badge(self, league_key: str) -> str:
        from core.constants import league_badge
        return league_badge(league_key)
