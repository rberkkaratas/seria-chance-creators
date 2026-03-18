"""Compare tab — side-by-side tactical breakdown."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import plotly.graph_objects as go
import streamlit as st

import config
from src.visualization.radar import create_comparison_radar, PLAYER_COLORS
from tabs import TabRenderer
from core.models import AppState
from core.constants import (
    label, role_color, LEAGUE_FLAGS, role_score_col, ROLE_DESCRIPTIONS,
)
from core.theme import D_TEXT, D_GRID, D_TICK, dark_layout


class CompareTab(TabRenderer):
    def render(self, state: AppState) -> None:
        df = state.df
        has_roles = state.has_roles
        has_league_col = state.has_league_col
        score_col = state.score_col
        all_roles = state.all_roles
        role_score_cols = state.role_score_cols
        core_metrics = state.core_metrics
        active_pct_suffix = state.active_pct_suffix
        league_mode = state.league_mode

        # ── Selector ──────────────────────────────────────────────────────
        st.markdown('<p class="section-title">Scouting Dossier</p>', unsafe_allow_html=True)
        st.markdown(
            "Side-by-side tactical breakdown — role fit, key battlegrounds, and where each player "
            "gives you something the other can't."
        )

        # Pool from full df so sidebar filters don't restrict who can be compared
        _cmp_list = df.sort_values(score_col, ascending=False)["player_name"].tolist()
        selected_players = st.multiselect(
            "Select players",
            options=_cmp_list,
            max_selections=4,
            placeholder="Choose 2–4 players...",
            label_visibility="collapsed",
        )

        if len(selected_players) < 2:
            st.markdown(
                '<div style="background:#1e293b;border-radius:10px;padding:40px;text-align:center;'
                'border:1px dashed #334155;margin-top:24px">'
                '<p style="margin:0;color:#64748b;font-size:0.95rem">'
                'Select 2–4 players from the dropdown above to begin the comparison.</p>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            # Always pull from full df regardless of sidebar filters
            import pandas as pd
            compare_df = df[df["player_name"].isin(selected_players)].copy()
            _order_idx = {p: i for i, p in enumerate(selected_players)}
            compare_df = compare_df.sort_values("player_name", key=lambda s: s.map(_order_idx))

            _cmp_colors = {
                p: PLAYER_COLORS[i % len(PLAYER_COLORS)][1]
                for i, p in enumerate(selected_players)
            }

            # ── Player header cards ────────────────────────────────────────
            st.markdown("<div style='margin:16px 0 4px'></div>", unsafe_allow_html=True)
            has_tm_data = state.has_tm_data
            _FEASIBILITY_COLORS = {
                "Expiring": "#22c55e", "Mid-term": "#f59e0b",
                "Locked": "#ef4444", "Unknown": "#64748b",
            }
            _hdr_cols = st.columns(len(selected_players))
            for _ci, _pn in enumerate(selected_players):
                _pr      = compare_df[compare_df["player_name"] == _pn].iloc[0]
                _pc      = _cmp_colors[_pn]
                _pr_role = _pr.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
                _rc      = role_color(_pr_role) if _pr_role else _pc
                _pr_sc   = float(_pr.get(score_col, 0) or 0)
                _pr_age  = int(_pr["age"]) if "age" in _pr and pd.notna(_pr["age"]) else "—"
                _pr_mins = int(_pr.get("minutes_played", 0) or 0)
                _pr_flag = LEAGUE_FLAGS.get(_pr.get("league", ""), "") if has_league_col else ""
                _pr_rank = int((df[score_col] > _pr_sc).sum()) + 1
                # TM data
                _tm_html = ""
                if has_tm_data:
                    _mv_raw = _pr.get("market_value_eur")
                    _ct_raw = _pr.get("contract_expires")
                    _fe_raw = str(_pr.get("transfer_feasibility", "Unknown") or "Unknown")
                    _fe_col = _FEASIBILITY_COLORS.get(_fe_raw, "#64748b")
                    _mv_str = (
                        f"€{_mv_raw / 1_000_000:.1f}M" if pd.notna(_mv_raw) and _mv_raw >= 1_000_000 else
                        f"€{_mv_raw / 1_000:.0f}K"     if pd.notna(_mv_raw) else "—"
                    )
                    _ct_str = str(int(_ct_raw)) if pd.notna(_ct_raw) else "—"
                    _tm_html = (
                        f'<div style="margin-top:8px;font-size:0.72rem;color:#94a3b8">'
                        f'{_mv_str} · {_ct_str} · '
                        f'<span style="color:{_fe_col};font-weight:600">{_fe_raw}</span>'
                        f'</div>'
                    )
                with _hdr_cols[_ci]:
                    st.markdown(
                        f'<div style="background:#1e293b;border-radius:10px;padding:18px;'
                        f'border-top:4px solid {_pc};text-align:center">'
                        f'<div style="width:52px;height:52px;border-radius:50%;background:{_pc};'
                        f'display:flex;align-items:center;justify-content:center;'
                        f'font-size:1.3rem;font-weight:700;color:#fff;margin:0 auto 10px">'
                        f'{_pr_sc:.0f}</div>'
                        f'<div style="font-weight:700;color:#f1f5f9;font-size:0.92rem;'
                        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{_pn}</div>'
                        f'<div style="font-size:0.78rem;color:#64748b;margin-top:3px">'
                        f'{_pr_flag} {_pr["team_name"]} · Age {_pr_age}</div>'
                        f'<div style="margin-top:10px">'
                        f'<span style="background:{_rc}22;color:{_rc};border:1px solid {_rc}44;'
                        f'border-radius:20px;padding:3px 10px;font-size:0.74rem;font-weight:600">'
                        f'{_pr_role}</span></div>'
                        f'<div style="font-size:0.72rem;color:#94a3b8;margin-top:8px">'
                        f'{_pr_mins:,} mins · <span style="color:#64748b">#{_pr_rank} overall</span></div>'
                        f'{_tm_html}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            st.markdown("---")

            # ── Similarity helper ──
            _sim_metrics_cmp = list(dict.fromkeys(
                list(config.CHANCE_CREATION_METRICS) +
                [m for w in config.ROLE_WEIGHTS.values() for m in w]
            ))
            _sim_metrics_cmp = [m for m in _sim_metrics_cmp if f"{m}_pct" in compare_df.columns]

            def _get_vec(player_name):
                return [
                    float(v) if (v := compare_df.loc[compare_df["player_name"] == player_name, f"{m}_pct"].values[0] if len(compare_df.loc[compare_df["player_name"] == player_name]) else None) is not None and pd.notna(v) else 0.0
                    for m in _sim_metrics_cmp
                ]

            def _pairwise_sim(p1, p2):
                v1, v2 = _get_vec(p1), _get_vec(p2)
                n = len(v1) or 1
                return max(0.0, 100.0 - sum(abs(a - b) for a, b in zip(v1, v2)) / n)

            # ── Scout Brief ────────────────────────────────────────────────
            if len(selected_players) == 2:
                _sb_p1, _sb_p2 = selected_players
                _sb_r1 = compare_df[compare_df["player_name"] == _sb_p1].iloc[0].get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
                _sb_r2 = compare_df[compare_df["player_name"] == _sb_p2].iloc[0].get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
                _sb_sim = _pairwise_sim(_sb_p1, _sb_p2)
                if _sb_r1 == _sb_r2 and _sb_r1:
                    _sb_role_line = (
                        f'Both profile as <b style="color:{role_color(_sb_r1)}">{_sb_r1}s</b> — '
                        f"this comparison reveals how they execute the same tactical mandate through different skill-sets."
                    )
                elif _sb_r1 and _sb_r2:
                    _sb_role_line = (
                        f'<b style="color:{_cmp_colors[_sb_p1]}">{_sb_p1.split()[-1]}</b> operates as a '
                        f'<b style="color:{role_color(_sb_r1)}">{_sb_r1}</b> while '
                        f'<b style="color:{_cmp_colors[_sb_p2]}">{_sb_p2.split()[-1]}</b> is a '
                        f'<b style="color:{role_color(_sb_r2)}">{_sb_r2}</b> — two different routes to progressing the team.'
                    )
                else:
                    _sb_role_line = "Two profiles matched head-to-head."
                _sb_sim_note = (
                    "Their metrics sit remarkably close — nearly a drop-in tactical swap." if _sb_sim >= 80 else
                    "Strong stylistic overlap, though clear divergence on a handful of key metrics." if _sb_sim >= 70 else
                    "Partial overlap — useful in some systems, but these are clearly different players." if _sb_sim >= 55 else
                    "Contrasting archetypes that would complement rather than replace each other."
                )
                st.markdown(
                    f'<div style="background:#1e293b;border-radius:10px;padding:18px 22px;'
                    f'border-left:4px solid #334155;margin-bottom:4px">'
                    f'<p style="margin:0 0 4px;font-size:0.68rem;font-weight:600;color:#94a3b8;'
                    f'text-transform:uppercase;letter-spacing:0.8px">Scout Brief</p>'
                    f'<p style="margin:0;font-size:0.92rem;color:#cbd5e1;line-height:1.8">'
                    f'{_sb_role_line} {_sb_sim_note}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                _sb_roles_ranked = sorted(
                    selected_players,
                    key=lambda p: float(compare_df[compare_df["player_name"] == p].iloc[0].get(score_col, 0) or 0),
                    reverse=True,
                )
                _sb_ranked_html = " → ".join(
                    f'<b style="color:{_cmp_colors[p]}">{p.split()[-1]}</b>'
                    + (f' <span style="color:{role_color(compare_df[compare_df["player_name"]==p].iloc[0].get(config.PRIMARY_ROLE_COL,""))};font-size:0.76rem">({compare_df[compare_df["player_name"]==p].iloc[0].get(config.PRIMARY_ROLE_COL,"—")})</span>' if has_roles else "")
                    for p in _sb_roles_ranked
                )
                st.markdown(
                    f'<div style="background:#1e293b;border-radius:10px;padding:16px 22px;'
                    f'border-left:4px solid #334155;margin-bottom:4px">'
                    f'<p style="margin:0 0 4px;font-size:0.68rem;font-weight:600;color:#94a3b8;'
                    f'text-transform:uppercase;letter-spacing:0.8px">Scout Brief — ranked by overall score</p>'
                    f'<p style="margin:0;font-size:0.88rem;color:#cbd5e1;line-height:1.8">{_sb_ranked_html}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("---")

            # ── Tactical DNA ────────────────────────────────────────────
            st.markdown('<p class="section-title">Tactical DNA</p>', unsafe_allow_html=True)

            if len(selected_players) == 2:
                _p1, _p2 = selected_players
                _v1 = _get_vec(_p1)
                _v2 = _get_vec(_p2)
                _sim = _pairwise_sim(_p1, _p2)
                _sim_label = (
                    "very similar — nearly interchangeable tactically" if _sim >= 80 else
                    "similar — strong stylistic overlap"               if _sim >= 70 else
                    "partial overlap — clear stylistic differences"    if _sim >= 55 else
                    "contrasting archetypes"
                )
                _gaps = [(_sim_metrics_cmp[i], _v1[i] - _v2[i]) for i in range(len(_v1))]
                _p1_edge = max(_gaps, key=lambda x: x[1])
                _p2_edge = min(_gaps, key=lambda x: x[1])
                _c1, _c2 = _cmp_colors[_p1], _cmp_colors[_p2]
                _sim_color = "#22c55e" if _sim >= 80 else "#f59e0b" if _sim >= 70 else "#94a3b8"
                _r1_dna = compare_df[compare_df["player_name"] == _p1].iloc[0].get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
                _r2_dna = compare_df[compare_df["player_name"] == _p2].iloc[0].get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
                _sim_implication = (
                    "Signing either covers the same tactical need." if _sim >= 80 else
                    "Both fit a similar role, but different ceiling metrics may tip the decision." if _sim >= 70 else
                    "They serve different functions — this is a profile choice, not a like-for-like swap." if _sim >= 55 else
                    "Define the tactical need before choosing — these are fundamentally different players."
                )
                if _r1_dna == _r2_dna and _r1_dna:
                    _dna_role_ctx = f'Both are <b style="color:{role_color(_r1_dna)}">{_r1_dna}s</b> — a true within-archetype contest.'
                elif _r1_dna and _r2_dna:
                    _dna_role_ctx = (
                        f'The divergence reflects their different mandates: '
                        f'<b style="color:{role_color(_r1_dna)}">{_r1_dna}</b> vs '
                        f'<b style="color:{role_color(_r2_dna)}">{_r2_dna}</b>.'
                    )
                else:
                    _dna_role_ctx = ""
                st.markdown(
                    f'<div style="background:#1e293b;border-radius:10px;padding:20px 24px;'
                    f'border-left:4px solid {_sim_color}">'
                    f'<div style="display:flex;align-items:center;gap:18px;margin-bottom:12px">'
                    f'<span style="font-size:2.2rem;font-weight:800;color:{_sim_color}">{_sim:.0f}%</span>'
                    f'<span style="color:#94a3b8;font-size:0.88rem;line-height:1.4">{_sim_label}</span>'
                    f'</div>'
                    f'<div style="background:#0f172a;border-radius:4px;height:6px;margin-bottom:14px">'
                    f'<div style="background:linear-gradient(90deg,{_c1},{_c2});'
                    f'border-radius:4px;height:6px;width:{min(_sim,100):.0f}%"></div></div>'
                    f'<p style="margin:0;font-size:0.86rem;color:#cbd5e1;line-height:1.8">'
                    f'<b style="color:{_c1}">{_p1.split()[-1]}</b> leads on '
                    f'<b style="color:#f1f5f9">{label(_p1_edge[0])}</b> (+{_p1_edge[1]:.0f} pct pts). '
                    f'<b style="color:{_c2}">{_p2.split()[-1]}</b> leads on '
                    f'<b style="color:#f1f5f9">{label(_p2_edge[0])}</b> (+{abs(_p2_edge[1]):.0f} pct pts). '
                    f'{_dna_role_ctx}'
                    f'<br><span style="color:#64748b;font-style:italic">{_sim_implication}</span></p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                _pairs_all = [
                    (a, b, _pairwise_sim(a, b))
                    for i, a in enumerate(selected_players)
                    for b in selected_players[i + 1:]
                ]
                _most_sim_pair  = max(_pairs_all, key=lambda x: x[2])
                _least_sim_pair = min(_pairs_all, key=lambda x: x[2])
                _matrix_html = (
                    f'<table style="width:100%;border-collapse:collapse;font-size:0.82rem">'
                    f'<tr><th style="padding:8px;color:#94a3b8;font-weight:400"></th>'
                )
                for _pn in selected_players:
                    _pc = _cmp_colors[_pn]
                    _matrix_html += (
                        f'<th style="padding:8px;text-align:center;color:{_pc};font-weight:700">'
                        f'{_pn.split()[-1]}</th>'
                    )
                _matrix_html += "</tr>"
                for _pa in selected_players:
                    _ca = _cmp_colors[_pa]
                    _matrix_html += f'<tr><td style="padding:8px;color:{_ca};font-weight:700">{_pa.split()[-1]}</td>'
                    for _pb in selected_players:
                        if _pa == _pb:
                            _matrix_html += '<td style="padding:8px;text-align:center;color:#64748b">—</td>'
                        else:
                            _s = _pairwise_sim(_pa, _pb)
                            _sc = "#22c55e" if _s >= 80 else "#f59e0b" if _s >= 70 else "#94a3b8"
                            _matrix_html += (
                                f'<td style="padding:8px;text-align:center;'
                                f'font-weight:700;color:{_sc}">{_s:.0f}%</td>'
                            )
                    _matrix_html += "</tr>"
                _matrix_html += "</table>"
                _c_ms1 = _cmp_colors[_most_sim_pair[0]]
                _c_ms2 = _cmp_colors[_most_sim_pair[1]]
                _c_ls1 = _cmp_colors[_least_sim_pair[0]]
                _c_ls2 = _cmp_colors[_least_sim_pair[1]]
                st.markdown(
                    f'<div style="background:#1e293b;border-radius:10px;padding:18px 22px">'
                    f'<p style="margin:0 0 12px;font-size:0.60rem;font-weight:600;color:#94a3b8;'
                    f'text-transform:uppercase;letter-spacing:0.8px">Pairwise Similarity</p>'
                    f'{_matrix_html}'
                    f'<p style="margin:12px 0 0;font-size:0.78rem;color:#64748b;line-height:1.7">'
                    f'Most similar: <b style="color:{_c_ms1}">{_most_sim_pair[0].split()[-1]}</b> &amp; '
                    f'<b style="color:{_c_ms2}">{_most_sim_pair[1].split()[-1]}</b> ({_most_sim_pair[2]:.0f}%). '
                    f'Most contrasting: <b style="color:{_c_ls1}">{_least_sim_pair[0].split()[-1]}</b> &amp; '
                    f'<b style="color:{_c_ls2}">{_least_sim_pair[1].split()[-1]}</b> ({_least_sim_pair[2]:.0f}%).'
                    f'</p>'
                    f'<p style="margin:4px 0 0;font-size:0.72rem;color:#64748b;font-style:italic">'
                    f'Green = highly interchangeable · Amber = stylistic overlap · Grey = distinct archetypes'
                    f'</p></div>',
                    unsafe_allow_html=True,
                )

            st.markdown("---")

            # ── Radar overlay ──────────────────────────────────────────────
            st.markdown('<p class="section-title">Tactical Fingerprint</p>', unsafe_allow_html=True)
            _pct_lbl = "within-league" if league_mode else "cross-league"
            st.caption(
                f"Percentile ranks ({_pct_lbl}) across 8 creation metrics. "
                "Overlapping fills show shared strengths. Gaps between traces reveal where one player "
                "covers ground the other doesn't."
            )
            fig_radar_cmp = create_comparison_radar(
                [state.player_view_dict(r) for _, r in compare_df.iterrows()],
                compare_df["player_name"].tolist(),
                metrics=core_metrics,
            )
            st.plotly_chart(fig_radar_cmp, use_container_width=True)

            # ── Spike callout ──
            if core_metrics:
                _spike_parts = []
                for _spn in selected_players:
                    _spc = _cmp_colors[_spn]
                    _spv = state.player_view_dict(compare_df[compare_df["player_name"] == _spn].iloc[0])
                    _sp_best_m = max(core_metrics, key=lambda m: float(_spv.get(m, 0) or 0))
                    _sp_best_v = float(_spv.get(_sp_best_m, 0) or 0)
                    _spike_parts.append(
                        f'<b style="color:{_spc}">{_spn.split()[-1]}</b>: '
                        f'<b style="color:#f1f5f9">{label(_sp_best_m)}</b> ({_sp_best_v:.0f}th pct)'
                    )
                st.markdown(
                    f'<div style="background:#1e293b;border-radius:8px;padding:10px 16px;'
                    f'font-size:0.82rem;color:#64748b;line-height:1.9">'
                    f'<span style="color:#94a3b8;font-size:0.68rem;font-weight:600;'
                    f'text-transform:uppercase;letter-spacing:0.7px;margin-right:10px">Sharpest spikes</span>'
                    + " &nbsp;·&nbsp; ".join(_spike_parts)
                    + f'</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("---")

            # ── Role fit ──────────────────────────────────────────────────
            if has_roles and role_score_cols:
                st.markdown('<p class="section-title">Tactical Slot Fit</p>', unsafe_allow_html=True)
                st.caption(
                    "Score 0–100 on every tactical slot. ★ marks each player's primary role. "
                    "The slot you need to fill doesn't have to match their natural role — look for the highest score."
                )
                _role_short = {
                    "Creator": "Creator", "Ball Progressor": "Progressor",
                    "Box Threat": "Box Threat", "Deep Builder": "Deep Builder",
                }
                _shared_xlabels = [_role_short.get(r, r) for r in all_roles]

                if len(selected_players) <= 2:
                    fig_role_fit = go.Figure()
                    for _pn in selected_players:
                        _pr    = compare_df[compare_df["player_name"] == _pn].iloc[0]
                        _pc    = _cmp_colors[_pn]
                        _prim  = _pr.get(config.PRIMARY_ROLE_COL, "")
                        _yvals = [float(_pr.get(role_score_col(r), 0) or 0) for r in all_roles]
                        _is_prim = [r == _prim for r in all_roles]
                        fig_role_fit.add_trace(go.Bar(
                            name=_pn, x=_shared_xlabels, y=_yvals,
                            marker_color=_pc, opacity=0.85,
                            text=["★" if p else "" for p in _is_prim],
                            textposition="outside",
                            textfont=dict(size=12, color=_pc),
                            hovertemplate=f"<b>{_pn}</b><br>%{{x}}: %{{y:.1f}}<extra></extra>",
                        ))
                    fig_role_fit.update_layout(**dark_layout(
                        barmode="group", height=320,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                                    font=dict(size=11, color=D_TEXT), bgcolor="rgba(0,0,0,0)"),
                        xaxis=dict(tickfont=dict(size=11, color=D_TEXT)),
                        yaxis=dict(title="Role score", range=[0, 116], gridcolor=D_GRID, color=D_TICK, dtick=25),
                        margin=dict(l=10, r=10, t=50, b=10),
                    ))
                    st.plotly_chart(fig_role_fit, use_container_width=True)
                    # Role narrative for 2 players
                    if len(selected_players) == 2:
                        _rf_p1, _rf_p2 = selected_players
                        _rf_r1 = compare_df[compare_df["player_name"] == _rf_p1].iloc[0]
                        _rf_r2 = compare_df[compare_df["player_name"] == _rf_p2].iloc[0]
                        _rf_lines = []
                        for r in all_roles:
                            _s1 = float(_rf_r1.get(role_score_col(r), 0) or 0)
                            _s2 = float(_rf_r2.get(role_score_col(r), 0) or 0)
                            _gap = abs(_s1 - _s2)
                            if _gap > 8:
                                _rf_winner = _rf_p1 if _s1 > _s2 else _rf_p2
                                _rf_wc = _cmp_colors[_rf_winner]
                                _rf_rc = role_color(r)
                                _rf_lines.append(
                                    f'<b style="color:{_rf_wc}">{_rf_winner.split()[-1]}</b> scores higher as a '
                                    f'<b style="color:{_rf_rc}">{r}</b> (+{_gap:.0f})'
                                )
                        if _rf_lines:
                            st.markdown(
                                f'<div style="background:#1e293b;border-radius:8px;padding:10px 16px;'
                                f'font-size:0.82rem;color:#94a3b8;line-height:1.9">'
                                + " &nbsp;·&nbsp; ".join(_rf_lines)
                                + f'</div>',
                                unsafe_allow_html=True,
                            )
                else:
                    _hm_z, _hm_text = [], []
                    for _pn in selected_players:
                        _pr   = compare_df[compare_df["player_name"] == _pn].iloc[0]
                        _prim = _pr.get(config.PRIMARY_ROLE_COL, "")
                        _row_z, _row_t = [], []
                        for r in all_roles:
                            v = float(_pr.get(role_score_col(r), 0) or 0)
                            _row_z.append(v)
                            _row_t.append(f"{'★ ' if r == _prim else ''}{v:.0f}")
                        _hm_z.append(_row_z)
                        _hm_text.append(_row_t)

                    fig_role_fit = go.Figure(go.Heatmap(
                        z=_hm_z,
                        x=_shared_xlabels,
                        y=[p.split()[-1] for p in selected_players],
                        text=_hm_text,
                        texttemplate="%{text}",
                        textfont=dict(size=13, color="#f1f5f9"),
                        colorscale=[[0, "#0f172a"], [0.5, "#1e3a5f"], [1, "#0095FF"]],
                        showscale=False,
                        hovertemplate="%{y} · %{x}: %{z:.0f}<extra></extra>",
                    ))
                    fig_role_fit.update_layout(**dark_layout(
                        height=max(160, len(selected_players) * 60),
                        margin=dict(l=10, r=10, t=20, b=10),
                        xaxis=dict(tickfont=dict(size=11, color=D_TEXT), side="top"),
                        yaxis=dict(tickfont=dict(size=11, color=D_TEXT)),
                    ))
                    st.plotly_chart(fig_role_fit, use_container_width=True)

                # Role description cards
                if all_roles and ROLE_DESCRIPTIONS:
                    _rd_cols = st.columns(len(all_roles))
                    for _rdi, _rdn in enumerate(all_roles):
                        _rdc = role_color(_rdn)
                        _rd_desc = ROLE_DESCRIPTIONS.get(_rdn, "")
                        _rd_metrics = list(config.ROLE_WEIGHTS.get(_rdn, {}).keys())[:2]
                        _rd_metric_labels = ", ".join(label(m) for m in _rd_metrics)
                        with _rd_cols[_rdi]:
                            st.markdown(
                                f'<div style="background:#0f172a;border-radius:8px;padding:10px 12px;'
                                f'border-top:2px solid {_rdc}">'
                                f'<div style="color:{_rdc};font-weight:700;font-size:0.76rem;'
                                f'margin-bottom:5px">{_rdn}</div>'
                                f'<div style="color:#64748b;font-size:0.72rem;line-height:1.5;'
                                f'margin-bottom:5px">{_rd_desc}</div>'
                                f'<div style="color:#64748b;font-size:0.68rem">Key: {_rd_metric_labels}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

                st.markdown("---")

            # ── Where the Gap Opens ────────────────────────────────────────
            st.markdown('<p class="section-title">Where the Gap Opens</p>', unsafe_allow_html=True)

            _battle_metrics = list(dict.fromkeys(
                list(config.CHANCE_CREATION_METRICS) +
                [m for w in config.ROLE_WEIGHTS.values() for m in w]
            ))
            _battle_avail = [m for m in _battle_metrics if f"{m}{active_pct_suffix}" in compare_df.columns]
            _verdict_winner = None
            _battle_sorted_all: list = []

            if _battle_avail:
                def _metric_spread(m):
                    vals = [
                        float(compare_df.loc[compare_df["player_name"] == p, f"{m}{active_pct_suffix}"].values[0] or 0)
                        for p in selected_players
                    ]
                    return max(vals) - min(vals) if len(vals) > 1 else 0

                _battle_sorted_all = sorted(_battle_avail, key=_metric_spread, reverse=True)
                _show_all = st.toggle("Show all metrics", value=False)
                _battle_sorted = _battle_sorted_all if _show_all else _battle_sorted_all[:10]
                _battle_labels = [label(m) for m in _battle_sorted]

                st.caption(
                    f"Top {len(_battle_sorted)} metrics where these players diverge most — biggest gaps first. "
                    "A scout targeting a specific quality should focus here."
                    + (" Toggle above to see all." if not _show_all else "")
                )

                fig_battle = go.Figure()
                for _pn in selected_players:
                    _pc = _cmp_colors[_pn]
                    _pcts = [
                        float(compare_df.loc[compare_df["player_name"] == _pn, f"{m}{active_pct_suffix}"].values[0] or 0)
                        if f"{m}{active_pct_suffix}" in compare_df.columns else 0
                        for m in _battle_sorted
                    ]
                    _raws = [
                        float(compare_df.loc[compare_df["player_name"] == _pn, m].values[0] or 0)
                        if m in compare_df.columns else 0
                        for m in _battle_sorted
                    ]
                    fig_battle.add_trace(go.Bar(
                        name=_pn, y=_battle_labels, x=_pcts, orientation="h",
                        marker_color=_pc, opacity=0.85,
                        hovertemplate=f"<b>{_pn}</b><br>%{{y}}: %{{x:.0f}}th pct · %{{customdata:.2f}} / 90<extra></extra>",
                        customdata=_raws,
                    ))

                _wins = {p: 0 for p in selected_players}
                for m in _battle_sorted:
                    _col = f"{m}{active_pct_suffix}"
                    _scores = {p: float(compare_df.loc[compare_df["player_name"] == p, _col].values[0] or 0)
                               for p in selected_players if _col in compare_df.columns}
                    if _scores:
                        _winner = max(_scores, key=_scores.get)
                        _wins[_winner] += 1
                _verdict_winner = max(_wins, key=_wins.get)
                _verdict_color  = _cmp_colors[_verdict_winner]
                _verdict_sorted = sorted(_wins.items(), key=lambda x: -x[1])

                _vw_best_m, _vw_best_gap = None, -1.0
                for _bm in _battle_sorted_all[:5]:
                    _bcol = f"{_bm}{active_pct_suffix}"
                    if _bcol not in compare_df.columns:
                        continue
                    _bwv = float(compare_df.loc[compare_df["player_name"] == _verdict_winner, _bcol].values[0] or 0)
                    _bov = [
                        float(compare_df.loc[compare_df["player_name"] == p, _bcol].values[0] or 0)
                        for p in selected_players if p != _verdict_winner and _bcol in compare_df.columns
                    ]
                    if _bov and (_bwv - max(_bov)) > _vw_best_gap:
                        _vw_best_gap = _bwv - max(_bov)
                        _vw_best_m = _bm

                _role_metric_map = {r: set(config.ROLE_WEIGHTS.get(r, {}).keys()) for r in all_roles}
                _player_role_wins: dict[str, dict[str, int]] = {p: {r: 0 for r in all_roles} for p in selected_players}
                for _bm in _battle_sorted:
                    _bcol = f"{_bm}{active_pct_suffix}"
                    _bscores = {p: float(compare_df.loc[compare_df["player_name"] == p, _bcol].values[0] or 0)
                                for p in selected_players if _bcol in compare_df.columns}
                    if not _bscores:
                        continue
                    _bwinner = max(_bscores, key=_bscores.get)
                    for r, mset in _role_metric_map.items():
                        if _bm in mset:
                            _player_role_wins[_bwinner][r] += 1

                _vw_name = _verdict_winner.split()[-1]
                _vw_wins_n, _vw_total = _verdict_sorted[0][1], len(_battle_sorted)
                _verdict_narrative = (
                    f'<b style="color:{_verdict_color}">{_vw_name}</b> wins '
                    f'<b style="color:#f1f5f9">{_vw_wins_n}/{_vw_total}</b> tracked metrics'
                )
                if _vw_best_m and _vw_best_gap > 0:
                    _verdict_narrative += (
                        f', with the sharpest edge in <b style="color:#f1f5f9">{label(_vw_best_m)}</b>'
                        f' (+{_vw_best_gap:.0f} pct pts ahead).'
                    )
                else:
                    _verdict_narrative += "."

                _vw_top_roles = sorted(
                    [(r, _player_role_wins[_verdict_winner][r]) for r in all_roles if _player_role_wins[_verdict_winner][r] > 0],
                    key=lambda x: -x[1],
                )
                if _vw_top_roles:
                    _top_r, _top_r_n = _vw_top_roles[0]
                    _verdict_narrative += (
                        f' Leads the <b style="color:{role_color(_top_r)}">{_top_r}</b> dimension '
                        f'({_top_r_n} metric{"s" if _top_r_n != 1 else ""}).'
                    )

                _verdict_counts_html = " &nbsp;·&nbsp; ".join(
                    f'<b style="color:{_cmp_colors[p]}">{p.split()[-1]}</b> {w}/{_vw_total}'
                    for p, w in _verdict_sorted
                )

                fig_battle.update_layout(**dark_layout(
                    barmode="group",
                    height=max(280, len(_battle_sorted) * 28),
                    xaxis=dict(title="Percentile rank", range=[0, 110], gridcolor=D_GRID, color=D_TICK, ticksuffix="th"),
                    yaxis=dict(tickfont=dict(size=10, color=D_TEXT), autorange="reversed"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                                font=dict(size=11, color=D_TEXT), bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=10, r=10, t=50, b=10),
                ))
                st.plotly_chart(fig_battle, use_container_width=True)

                st.markdown(
                    f'<div style="background:#1e293b;border-radius:8px;padding:14px 18px;'
                    f'border-left:4px solid {_verdict_color}">'
                    f'<p style="margin:0 0 5px;font-size:0.68rem;font-weight:600;color:#94a3b8;'
                    f'text-transform:uppercase;letter-spacing:0.7px">Battleground verdict</p>'
                    f'<p style="margin:0 0 6px;font-size:0.86rem;color:#cbd5e1">{_verdict_narrative}</p>'
                    f'<p style="margin:0;font-size:0.78rem;color:#64748b">{_verdict_counts_html}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # ── Scout Summary (2-player only) ──────────────────────────────
            if len(selected_players) == 2:
                st.markdown("---")
                st.markdown('<p class="section-title">Scout Summary</p>', unsafe_allow_html=True)
                _ss_p1, _ss_p2 = selected_players
                _ss_r1 = compare_df[compare_df["player_name"] == _ss_p1].iloc[0]
                _ss_r2 = compare_df[compare_df["player_name"] == _ss_p2].iloc[0]
                _ss_c1, _ss_c2 = _cmp_colors[_ss_p1], _cmp_colors[_ss_p2]
                _ss_role1 = _ss_r1.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
                _ss_role2 = _ss_r2.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
                _ss_score1 = float(_ss_r1.get(role_score_col(_ss_role1), 0) or 0) if _ss_role1 else 0.0
                _ss_score2 = float(_ss_r2.get(role_score_col(_ss_role2), 0) or 0) if _ss_role2 else 0.0
                _ss_age1 = int(_ss_r1["age"]) if "age" in _ss_r1 and pd.notna(_ss_r1["age"]) else None
                _ss_age2 = int(_ss_r2["age"]) if "age" in _ss_r2 and pd.notna(_ss_r2["age"]) else None
                _ss_mins1 = int(_ss_r1.get("minutes_played", 0) or 0)
                _ss_mins2 = int(_ss_r2.get("minutes_played", 0) or 0)
                _ss_sim_val = _pairwise_sim(_ss_p1, _ss_p2)
                _ss_sim_lbl = (
                    "very similar profiles" if _ss_sim_val >= 80 else
                    "similar profiles" if _ss_sim_val >= 70 else
                    "partially overlapping profiles" if _ss_sim_val >= 55 else
                    "contrasting profiles"
                )

                _ss_narrative_intros = {
                    "Creator":         "unlocks defences through dangerous deliveries — key passes, through balls, and crosses",
                    "Ball Progressor": "drives the team forward through direct carrying and dribbling",
                    "Box Threat":      "generates constant threat through high box-touch volume and direct shooting",
                    "Deep Builder":    "controls tempo from deep with accurate, forward-oriented passing",
                }

                _ss_lines = []
                _ss_n1 = _ss_p1.split()[-1]
                _ss_n2 = _ss_p2.split()[-1]
                _ss_flag1 = LEAGUE_FLAGS.get(_ss_r1.get("league", ""), "") if has_league_col else ""
                _ss_flag2 = LEAGUE_FLAGS.get(_ss_r2.get("league", ""), "") if has_league_col else ""

                if _ss_role1 and _ss_role2:
                    if _ss_role1 == _ss_role2:
                        _ss_lines.append(
                            f'<b style="color:{_ss_c1}">{_ss_n1}</b> ({_ss_flag1} {_ss_r1["team_name"]}) and '
                            f'<b style="color:{_ss_c2}">{_ss_n2}</b> ({_ss_flag2} {_ss_r2["team_name"]}) '
                            f'share the same primary role — '
                            f'<b style="color:{role_color(_ss_role1)}">{_ss_role1}</b> — '
                            f'with {_ss_sim_lbl} ({_ss_sim_val:.0f}% match).'
                        )
                    else:
                        _ss_lines.append(
                            f'<b style="color:{_ss_c1}">{_ss_n1}</b> ({_ss_flag1} {_ss_r1["team_name"]}) is a '
                            f'<b style="color:{role_color(_ss_role1)}">{_ss_role1}</b> — '
                            f'{_ss_narrative_intros.get(_ss_role1, "contributes across the midfield")}. '
                            f'<b style="color:{_ss_c2}">{_ss_n2}</b> ({_ss_flag2} {_ss_r2["team_name"]}) is a '
                            f'<b style="color:{role_color(_ss_role2)}">{_ss_role2}</b> — '
                            f'{_ss_narrative_intros.get(_ss_role2, "contributes across the midfield")}. '
                            f'Overall {_ss_sim_lbl} ({_ss_sim_val:.0f}% match).'
                        )

                if _ss_role1 and _ss_role2 and _ss_role1 != _ss_role2:
                    _ss_stronger = _ss_p1 if _ss_score1 >= _ss_score2 else _ss_p2
                    _ss_stronger_role = _ss_role1 if _ss_stronger == _ss_p1 else _ss_role2
                    _ss_stronger_sc = max(_ss_score1, _ss_score2)
                    _ss_weaker_sc = min(_ss_score1, _ss_score2)
                    _ss_sc = _ss_c1 if _ss_stronger == _ss_p1 else _ss_c2
                    _ss_lines.append(
                        f'<b style="color:{_ss_sc}">{_ss_stronger.split()[-1]}</b> rates higher in their primary role '
                        f'(<b style="color:{role_color(_ss_stronger_role)}">{_ss_stronger_role}</b>: '
                        f'{_ss_stronger_sc:.0f} vs {_ss_weaker_sc:.0f}).'
                    )

                if _battle_avail and _battle_sorted_all:
                    _ss_top_m = _battle_sorted_all[0]
                    _ss_top_col = f"{_ss_top_m}{active_pct_suffix}"
                    if _ss_top_col in compare_df.columns:
                        _ss_v1 = float(compare_df.loc[compare_df["player_name"] == _ss_p1, _ss_top_col].values[0] or 0)
                        _ss_v2 = float(compare_df.loc[compare_df["player_name"] == _ss_p2, _ss_top_col].values[0] or 0)
                        _ss_top_leader = _ss_p1 if _ss_v1 >= _ss_v2 else _ss_p2
                        _ss_top_lc = _ss_c1 if _ss_top_leader == _ss_p1 else _ss_c2
                        _ss_top_lead_v, _ss_top_trail_v = ((_ss_v1, _ss_v2) if _ss_v1 >= _ss_v2 else (_ss_v2, _ss_v1))
                        _ss_lines.append(
                            f'The biggest gap is <b style="color:#f1f5f9">{label(_ss_top_m)}</b>: '
                            f'<b style="color:{_ss_top_lc}">{_ss_top_leader.split()[-1]}</b> leads '
                            f'({_ss_top_lead_v:.0f}th vs {_ss_top_trail_v:.0f}th pct).'
                        )

                if _ss_age1 and _ss_age2 and abs(_ss_age1 - _ss_age2) >= 3:
                    _ss_younger = _ss_p1 if _ss_age1 < _ss_age2 else _ss_p2
                    _ss_older   = _ss_p2 if _ss_younger == _ss_p1 else _ss_p1
                    _ss_yc = _ss_c1 if _ss_younger == _ss_p1 else _ss_c2
                    _ss_age_diff = abs(_ss_age1 - _ss_age2)
                    _ss_lines.append(
                        f'At {min(_ss_age1, _ss_age2)}, '
                        f'<b style="color:{_ss_yc}">{_ss_younger.split()[-1]}</b> is {_ss_age_diff} years younger — '
                        f'the longer-term development profile if your timeline extends beyond this window.'
                    )

                if _ss_mins1 and _ss_mins2:
                    _ss_higher_mins = _ss_p1 if _ss_mins1 >= _ss_mins2 else _ss_p2
                    _ss_hmc = _ss_c1 if _ss_higher_mins == _ss_p1 else _ss_c2
                    _ss_min_ratio = max(_ss_mins1, _ss_mins2) / max(min(_ss_mins1, _ss_mins2), 1)
                    if _ss_min_ratio >= 1.2:
                        _ss_lines.append(
                            f'<b style="color:{_ss_hmc}">{_ss_higher_mins.split()[-1]}</b> has accumulated '
                            f'significantly more minutes ({max(_ss_mins1, _ss_mins2):,} vs {min(_ss_mins1, _ss_mins2):,}) — '
                            f'a larger sample for this profile.'
                        )

                if has_tm_data:
                    _ss_mv1 = _ss_r1.get("market_value_eur")
                    _ss_mv2 = _ss_r2.get("market_value_eur")
                    _ss_fe1 = str(_ss_r1.get("transfer_feasibility", "Unknown") or "Unknown")
                    _ss_fe2 = str(_ss_r2.get("transfer_feasibility", "Unknown") or "Unknown")
                    _fe_palette = {"Expiring": "#22c55e", "Mid-term": "#f59e0b", "Locked": "#ef4444"}
                    _ss_fe1c = _fe_palette.get(_ss_fe1, "#64748b")
                    _ss_fe2c = _fe_palette.get(_ss_fe2, "#64748b")
                    if pd.notna(_ss_mv1) and pd.notna(_ss_mv2):
                        _mv_diff = abs(_ss_mv1 - _ss_mv2)
                        _cheaper = _ss_p1 if _ss_mv1 <= _ss_mv2 else _ss_p2
                        _cc = _ss_c1 if _cheaper == _ss_p1 else _ss_c2
                        _mv1_str = f"€{_ss_mv1/1e6:.1f}M" if _ss_mv1 >= 1e6 else f"€{_ss_mv1/1e3:.0f}K"
                        _mv2_str = f"€{_ss_mv2/1e6:.1f}M" if _ss_mv2 >= 1e6 else f"€{_ss_mv2/1e3:.0f}K"
                        _mv_line = (
                            f'Valuations: <b style="color:{_ss_c1}">{_ss_p1.split()[-1]}</b> {_mv1_str}'
                            f' · <b style="color:{_ss_c2}">{_ss_p2.split()[-1]}</b> {_mv2_str}. '
                        )
                        if _mv_diff > 5_000_000:
                            _mv_line += f'<b style="color:{_cc}">{_cheaper.split()[-1]}</b> represents the lower-cost option.'
                        _ss_lines.append(_mv_line)
                    fe_line_parts = []
                    for _p, _fe, _fec, _c in [
                        (_ss_p1, _ss_fe1, _ss_fe1c, _ss_c1), (_ss_p2, _ss_fe2, _ss_fe2c, _ss_c2)
                    ]:
                        if _fe != "Unknown":
                            fe_line_parts.append(
                                f'<b style="color:{_c}">{_p.split()[-1]}</b>: '
                                f'<span style="color:{_fec}">{_fe}</span>'
                            )
                    if fe_line_parts:
                        _ss_lines.append("Contract feasibility — " + " · ".join(fe_line_parts) + ".")

                _ss_lead_color = _ss_c1 if _verdict_winner == _ss_p1 else _ss_c2 if _battle_avail else "#334155"
                st.markdown(
                    f'<div class="narrative-card" style="border-left:4px solid {_ss_lead_color}">'
                    + "<br>".join(f'<p style="margin:0 0 8px 0">{ln}</p>' for ln in _ss_lines)
                    + f'</div>',
                    unsafe_allow_html=True,
                )
