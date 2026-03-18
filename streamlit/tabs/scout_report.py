"""Scout Report tab — individual player profile."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from src.visualization.radar import create_radar_chart, PLAYER_COLORS
from tabs import TabRenderer
from core.models import AppState
from core.constants import (
    label, role_color, archetype_color, LEAGUE_FLAGS, LEAGUE_DISPLAY,
    role_score_col, METRIC_LABELS,
)
from core.theme import D_TEXT, D_GRID, D_TICK, D_BG, dark_layout
from core.data_loader import DataLoader


class ScoutReportTab(TabRenderer):
    def render(self, state: AppState) -> None:
        filtered = state.filtered
        df = state.df
        has_roles = state.has_roles
        has_archetypes = state.has_archetypes
        has_tm_data = state.has_tm_data
        has_league_col = state.has_league_col
        score_col = state.score_col
        role_score_cols = state.role_score_cols
        core_metrics = state.core_metrics
        pct_cols = state.pct_cols
        active_pct_suffix = state.active_pct_suffix
        league_mode = state.league_mode
        raw_players_df = state.raw_players_df
        matches_df = state.matches_df

        st.markdown('<p class="section-title">Scout Report</p>', unsafe_allow_html=True)

        player_options = (
            filtered.sort_values(score_col, ascending=False)["player_name"].tolist()
            if len(filtered) else []
        )
        profile_default = st.session_state.get("profile_player")
        default_idx = (
            player_options.index(profile_default)
            if profile_default in player_options
            else 0
        )
        selected_player = st.selectbox(
            "Select a player", options=player_options,
            index=default_idx,
            help="Players sorted by CC score",
        )
        st.caption("Radar shows percentile ranks within the filtered midfielder group.")

        if selected_player:
            row       = filtered[filtered["player_name"] == selected_player].iloc[0]
            score_val = float(row.get(score_col, 0) or 0)
            arch      = row.get("archetype", "") if has_archetypes else ""
            prim_role = row.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
            bar_col   = role_color(prim_role) if prim_role else (archetype_color(arch) if arch else "#0095FF")

            # League and global ranks
            _global_all = df.sort_values(score_col, ascending=False).reset_index(drop=True)
            global_rank = _global_all[_global_all["player_name"] == selected_player].index[0] + 1 \
                          if selected_player in _global_all["player_name"].values else "—"
            global_total = len(_global_all)
            if has_league_col and "league" in row and pd.notna(row["league"]):
                _league_all = df[df["league"] == row["league"]].sort_values(score_col, ascending=False).reset_index(drop=True)
                league_rank = _league_all[_league_all["player_name"] == selected_player].index[0] + 1 \
                              if selected_player in _league_all["player_name"].values else "—"
                league_total = len(_league_all)
                player_league = row["league"]
            else:
                league_rank = None
                league_total = None
                player_league = None

            age_str  = f"{int(row['age'])}"      if "age"      in row and pd.notna(row["age"])      else "—"
            pos_str  = str(row["position"])      if "position" in row and pd.notna(row["position"]) else "—"
            mins_val = int(row["minutes_played"]) if "minutes_played" in row and pd.notna(row["minutes_played"]) else 0
            apps_val = int(row["appearances"])    if "appearances"    in row and pd.notna(row["appearances"])    else 0

            # ── Header banner ──
            if has_tm_data:
                mv_raw  = row.get("market_value_eur")
                ct_raw  = row.get("contract_expires")
                feasib  = row.get("transfer_feasibility", "Unknown")
                mv_str  = (
                    f"€{mv_raw / 1_000_000:.1f}M" if pd.notna(mv_raw) and mv_raw >= 1_000_000
                    else f"€{mv_raw / 1_000:.0f}K" if pd.notna(mv_raw) and mv_raw >= 1_000
                    else "—"
                )
                ct_str  = str(int(ct_raw)) if pd.notna(ct_raw) else "—"
                feasib_colors = {
                    "Expiring": "#22c55e", "Mid-term": "#f59e0b",
                    "Locked": "#ef4444",   "Unknown": "#64748b",
                }
                fc = feasib_colors.get(feasib, "#64748b")
                tm_html = (
                    f'<p style="margin:8px 0 0;font-size:0.82rem;display:flex;align-items:center;gap:10px">'
                    f'<span style="color:#64748b">Market Value</span>'
                    f'<span style="color:#f1f5f9;font-weight:600">{mv_str}</span>'
                    f'<span style="color:#64748b">·</span>'
                    f'<span style="color:#64748b">Contract Until</span>'
                    f'<span style="color:#f1f5f9;font-weight:600">{ct_str}</span>'
                    f'<span style="color:#64748b">·</span>'
                    f'<span style="background:{fc}22;color:{fc};border:1px solid {fc}55;'
                    f'border-radius:4px;padding:1px 8px;font-size:0.76rem;font-weight:600">'
                    f'{feasib}</span>'
                    f'</p>'
                )
            else:
                tm_html = ""

            _league_badge_str = (
                f'{LEAGUE_FLAGS.get(player_league,"")} {LEAGUE_DISPLAY.get(player_league, player_league.replace("_"," "))}'
                if player_league else ""
            )
            _role_arch_str = "&nbsp;·&nbsp;<em>" + (prim_role or arch) + "</em>" if (prim_role or arch) else ""
            _league_str    = "&nbsp;·&nbsp;" + _league_badge_str if _league_badge_str else ""

            _league_rank_html = ""
            if league_rank and league_rank != "—":
                _league_rank_html = (
                    f'<div style="text-align:center">'
                    f'<div style="background:#1e3a5f;color:#93c5fd;border-radius:8px;'
                    f'padding:6px 14px;font-size:1.1rem;font-weight:bold">'
                    f'#{league_rank}<span style="font-size:0.75rem;color:#64748b"> / {league_total}</span>'
                    f'</div>'
                    f'<p style="margin:4px 0 0;color:#64748b;font-size:0.72rem">League Rank</p>'
                    f'</div>'
                )
            _global_rank_html = (
                f'<div style="text-align:center">'
                f'<div style="background:#1a2535;color:#94a3b8;border-radius:8px;'
                f'padding:6px 14px;font-size:1.1rem;font-weight:bold">'
                f'#{global_rank}<span style="font-size:0.75rem;color:#64748b"> / {global_total}</span>'
                f'</div>'
                f'<p style="margin:4px 0 0;color:#64748b;font-size:0.72rem">Global Rank</p>'
                f'</div>'
            )

            st.markdown(
                f'<div style="background:#1e293b;border-radius:10px;padding:18px 24px;'
                f'border-left:5px solid {bar_col};margin-bottom:16px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">'
                f'<div>'
                f'<h2 style="margin:0;color:#f1f5f9">{selected_player}</h2>'
                f'<p style="margin:4px 0 0;color:#94a3b8;font-size:0.95rem">'
                f'{row["team_name"]} &nbsp;·&nbsp; {pos_str} &nbsp;·&nbsp; Age {age_str}'
                f'{_role_arch_str}{_league_str}'
                f'</p>'
                f'<p style="margin:6px 0 0;color:#64748b;font-size:0.82rem">'
                f'{mins_val:,} minutes played &nbsp;·&nbsp; {apps_val} appearances'
                f'</p>'
                f'{tm_html}'
                f'</div>'
                f'<div style="display:flex;gap:16px;align-items:center">'
                f'{_league_rank_html}'
                f'{_global_rank_html}'
                f'<div style="text-align:center">'
                f'<div style="background:{bar_col};color:white;border-radius:50%;'
                f'width:68px;height:68px;display:flex;align-items:center;'
                f'justify-content:center;font-size:1.5rem;font-weight:bold">'
                f'{score_val:.0f}'
                f'</div>'
                f'<p style="margin:4px 0 0;color:#64748b;font-size:0.75rem">Overall Score</p>'
                f'</div>'
                f'</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── Build narrative & strength data ──────────────────────
            _narrative_intros = {
                "Creator":         "unlocks defences through dangerous deliveries into the box — whether centrally through key passes and through balls or from wide through crosses",
                "Ball Progressor": "drives the team forward through direct carrying and dribbling, turning possession into penetration",
                "Box Threat":      "constantly arrives in the penalty area, combining relentless box presence with a direct shooting threat",
                "Deep Builder":    "controls the tempo from deep with high-volume, accurate, forward-oriented passing",
            }
            _role_score_val = float(row.get(f"{config.ROLE_SCORE_COL_PREFIX}{prim_role}", 0) or 0) if prim_role else 0.0
            _surname = selected_player.split()[-1]

            _role_met_list = list(config.ROLE_WEIGHTS.get(prim_role, {}).keys()) if prim_role else []
            _role_mpcts = sorted(
                [(label(m), float(row.get(f"{m}{active_pct_suffix}", 0) or 0))
                 for m in _role_met_list if f"{m}{active_pct_suffix}" in row.index],
                key=lambda x: x[1], reverse=True,
            )
            _narrative = ""
            if prim_role:
                _intro = _narrative_intros.get(prim_role, "contributes across the midfield")
                _narrative = f"Rated **{_role_score_val:.0f}/100** as a **{prim_role}**, {_surname} {_intro}."
                if len(_role_mpcts) >= 2:
                    _narrative += (
                        f" Standout metrics: **{_role_mpcts[0][0]}** ({_role_mpcts[0][1]:.0f}th pct) "
                        f"and **{_role_mpcts[1][0]}** ({_role_mpcts[1][1]:.0f}th pct)."
                    )
                elif _role_mpcts:
                    _narrative += f" Standout metric: **{_role_mpcts[0][0]}** ({_role_mpcts[0][1]:.0f}th pct)."
                if _role_mpcts and _role_mpcts[-1][1] < 35:
                    _narrative += f" Development area: **{_role_mpcts[-1][0]}** ({_role_mpcts[-1][1]:.0f}th pct)."
            _narr_html = re.sub(r'\*\*(.+?)\*\*', r'<b style="color:#f1f5f9">\1</b>', _narrative)

            _all_mpcts: list[tuple[str, float, str]] = []
            _seen_m: set[str] = set()
            for _m in list({m2 for w in config.ROLE_WEIGHTS.values() for m2 in w} | set(config.CHANCE_CREATION_METRICS)):
                _pc = f"{_m}{active_pct_suffix}"
                if _pc in row.index and pd.notna(row[_pc]) and _m not in _seen_m:
                    _all_mpcts.append((label(_m), float(row[_pc]), _m))
                    _seen_m.add(_m)
            _all_mpcts.sort(key=lambda x: x[1], reverse=True)
            _strengths = _all_mpcts[:3]
            _concerns  = _all_mpcts[-3:]

            # ── Two-column layout: Radar | Right panel ─────────────────────
            col_radar, col_right = st.columns([5, 4])

            with col_radar:
                if pct_cols:
                    _pct_label = "Within league" if league_mode else "All leagues"
                    st.caption(f"Radar percentiles: {_pct_label}")
                    fig_radar = create_radar_chart(
                        state.player_view_dict(row),
                        metrics=core_metrics, title="",
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)

            with col_right:
                # ── Role scores — compact HTML bars ────────────────────────
                if has_roles and role_score_cols:
                    def _hex_to_rgba(hex_color: str, alpha: float) -> str:
                        h = hex_color.lstrip("#")
                        rv, gv, bv = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                        return f"rgba({rv},{gv},{bv},{alpha})"

                    _role_bars_html = ""
                    for _rc in role_score_cols:
                        _rn  = _rc.replace(config.ROLE_SCORE_COL_PREFIX, "")
                        _rv  = float(row.get(_rc, 0) or 0)
                        _rc2 = role_color(_rn)
                        _is_prim = (_rn == prim_role)
                        _bar_c = _rc2 if _is_prim else _hex_to_rgba(_rc2, 0.35)
                        _label_c = "#f1f5f9" if _is_prim else "#64748b"
                        _star = ' <span style="color:#f59e0b;font-size:0.65rem">★ primary</span>' if _is_prim else ""
                        _role_bars_html += (
                            f'<div style="margin-bottom:10px">'
                            f'<div style="display:flex;justify-content:space-between;'
                            f'align-items:center;margin-bottom:4px">'
                            f'<span style="font-size:0.75rem;font-weight:{"700" if _is_prim else "400"};'
                            f'color:{_label_c}">{_rn}{_star}</span>'
                            f'<span style="font-size:0.78rem;font-weight:700;color:{_bar_c}">{_rv:.0f}</span>'
                            f'</div>'
                            f'<div style="background:#0f172a;border-radius:3px;height:6px">'
                            f'<div style="background:{_bar_c};border-radius:3px;height:6px;'
                            f'width:{_rv:.0f}%"></div>'
                            f'</div>'
                            f'</div>'
                        )

                    # Peer rank
                    _peer_rank_html = ""
                    if prim_role:
                        _role_col = f"{config.ROLE_SCORE_COL_PREFIX}{prim_role}"
                        if _role_col in filtered.columns:
                            _sorted_peers = filtered.sort_values(_role_col, ascending=False).reset_index(drop=True)
                            _peer_match   = _sorted_peers[_sorted_peers["player_name"] == selected_player]
                            if len(_peer_match) > 0:
                                _peer_rank    = int(_peer_match.index[0]) + 1
                                _peer_total   = len(_sorted_peers)
                                _peer_top_pct = int((_peer_rank / _peer_total) * 100)
                                _peer_rank_html = (
                                    f'<div style="margin-top:4px;padding:8px 0;border-top:1px solid #1e293b;'
                                    f'font-size:0.72rem;color:#64748b">'
                                    f'Ranked <b style="color:{bar_col}">#{_peer_rank}</b> of {_peer_total} '
                                    f'{prim_role}s · top {_peer_top_pct}%'
                                    f'</div>'
                                )

                    st.markdown(
                        f'<div style="background:#1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px">'
                        f'<p style="margin:0 0 12px;font-size:0.72rem;font-weight:600;color:#64748b;'
                        f'text-transform:uppercase;letter-spacing:0.8px">Role Ratings</p>'
                        f'{_role_bars_html}'
                        f'{_peer_rank_html}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                # ── Narrative + Strengths/Development ──────────────────────
                _str_pills = " ".join(
                    f'<span class="strength-pill">↑ {lbl}</span>' for lbl, _, _ in _strengths
                )
                _con_pills = " ".join(
                    f'<span class="concern-pill">↓ {lbl}</span>' for lbl, _, _ in _concerns
                )
                st.markdown(
                    f'<div style="background:#1e293b;border-radius:10px;padding:16px 18px;'
                    f'border-left:4px solid {bar_col}">'
                    f'<p style="margin:0 0 8px;font-size:0.72rem;font-weight:600;color:#64748b;'
                    f'text-transform:uppercase;letter-spacing:0.8px">Scouting Narrative</p>'
                    f'<p style="margin:0 0 14px;color:#cbd5e1;font-size:0.88rem;line-height:1.6">'
                    f'{_narr_html}</p>'
                    f'<p style="margin:0 0 6px;font-size:0.68rem;font-weight:600;color:#64748b;'
                    f'text-transform:uppercase;letter-spacing:0.7px">Strengths</p>'
                    f'<div style="margin-bottom:12px">{_str_pills}</div>'
                    f'<p style="margin:0 0 6px;font-size:0.68rem;font-weight:600;color:#64748b;'
                    f'text-transform:uppercase;letter-spacing:0.7px">Development Areas</p>'
                    f'<div>{_con_pills}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("---")

            # ── Season totals — styled cards ──
            st.markdown('<p class="section-title">Season Totals</p>', unsafe_allow_html=True)

            TOTAL_META = [
                ("key_passes",               "Key Passes",           "key_passes_p90"),
                ("assists",                  "Assists",              "assists_p90"),
                ("passes_into_penalty_area", "Passes into Box",      "passes_into_penalty_area_p90"),
                ("through_balls",            "Through Balls",        "through_balls_p90"),
                ("crosses",                  "Crosses",              "crosses_p90"),
                ("progressive_passes",       "Progressive Passes",   "progressive_passes_p90"),
                ("carries_into_final_third", "Carries F3",           "carries_into_final_third_p90"),
                ("successful_dribbles",      "Dribbles Won",         "successful_dribbles_p90"),
                ("shots",                    "Shots",                "shots_p90"),
                ("penalty_area_touches",     "Box Touches",          "penalty_area_touches_p90"),
                ("half_space_passes",        "Half-Space Passes",    "half_space_passes_p90"),
            ]

            totals = [
                (lbl, col, p90c)
                for col, lbl, p90c in TOTAL_META
                if col in row and pd.notna(row.get(col))
            ]

            if totals and apps_val > 0:
                cols_per_row = 6
                for chunk_start in range(0, len(totals), cols_per_row):
                    chunk = totals[chunk_start: chunk_start + cols_per_row]
                    card_cols = st.columns(len(chunk))
                    for ci, (lbl, col, p90c) in enumerate(chunk):
                        total_val = int(row[col])
                        p90_val   = row.get(p90c)
                        p90_str   = f"{float(p90_val):.2f}" if p90_val is not None and pd.notna(p90_val) else "—"
                        pct_col = f"{p90c}_pct"
                        pct_val = row.get(pct_col)
                        if (pct_val is None or pd.isna(pct_val)) and p90c in df.columns:
                            _col_series = df[p90c].dropna()
                            if len(_col_series) > 0:
                                _player_p90 = row.get(p90c)
                                if _player_p90 is not None and pd.notna(_player_p90):
                                    pct_val = (_col_series < float(_player_p90)).sum() / len(_col_series) * 100
                        pct = float(pct_val) if pct_val is not None and pd.notna(pct_val) else None
                        pct_str   = f"{pct:.0f}th" if pct is not None else ""
                        bar_pct_w = f"{pct:.0f}%" if pct is not None else "0%"
                        bar_pct_c = (
                            "#22c55e" if pct is not None and pct >= 75 else
                            "#f59e0b" if pct is not None and pct >= 50 else
                            "#ef4444" if pct is not None else "#334155"
                        )
                        with card_cols[ci]:
                            st.markdown(
                                f'<div style="background:#1e293b;border-radius:8px;padding:12px 10px;'
                                f'border-top:3px solid {bar_pct_c}">'
                                f'<div style="font-size:0.60rem;font-weight:600;color:#64748b;'
                                f'text-transform:uppercase;letter-spacing:0.7px;margin-bottom:4px">'
                                f'{lbl}</div>'
                                f'<div style="font-size:1.5rem;font-weight:800;color:#f1f5f9;'
                                f'line-height:1.1">{p90_str}</div>'
                                f'<div style="font-size:0.62rem;color:#64748b;margin-bottom:8px">per 90</div>'
                                f'<div style="background:#0f172a;border-radius:3px;height:4px;margin-bottom:6px">'
                                f'<div style="background:{bar_pct_c};border-radius:3px;height:4px;'
                                f'width:{bar_pct_w}"></div></div>'
                                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                                f'<span style="font-size:0.62rem;color:#94a3b8">{total_val} total</span>'
                                f'<span style="font-size:0.65rem;font-weight:700;color:{bar_pct_c}">'
                                f'{pct_str}</span>'
                                f'</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                    st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

            # ── Similar Players ────────────────────────────────────────────
            st.markdown("---")
            st.markdown('<p class="section-title">Similar Players</p>', unsafe_allow_html=True)
            st.caption(
                "Ranked by profile similarity across all creation metrics. "
                "Method: equal-weight mean absolute difference in percentile ranks — "
                "same approach as FBRef. Age shown relative to selected player."
            )

            _SIM_SUFFIX = "_pct"
            _all_sim_metrics = list(dict.fromkeys(
                m for _rw in config.ROLE_WEIGHTS.values() for m in _rw
            ))
            _sim_metrics_sr = [m for m in _all_sim_metrics if f"{m}{_SIM_SUFFIX}" in df.columns]
            _n_sim          = len(_sim_metrics_sr) or 1

            def _safe_pct(r, m):
                v = r.get(f"{m}{_SIM_SUFFIX}")
                return float(v) if v is not None and pd.notna(v) else 0.0

            _ref_age_val = row.get("age")
            _ref_age     = int(_ref_age_val) if pd.notna(_ref_age_val) else None

            if _sim_metrics_sr and len(df) > 1:
                _ref_vec = [_safe_pct(row, m) for m in _sim_metrics_sr]

                _sim_scores: list[tuple] = []
                for _, _other_row in df.iterrows():
                    if _other_row["player_name"] == selected_player:
                        continue
                    _ov  = [_safe_pct(_other_row, m) for m in _sim_metrics_sr]
                    _mad = sum(abs(a - b) for a, b in zip(_ref_vec, _ov)) / _n_sim
                    _sim_scores.append((_other_row, max(0.0, 100.0 - _mad), _ov))

                _sim_scores.sort(key=lambda x: x[1], reverse=True)
                _top_similar = _sim_scores[:5]

                _sim_cols = st.columns(len(_top_similar))
                for _si, (_srow, _ssim, _sov) in enumerate(_top_similar):
                    _sname     = _srow["player_name"]
                    _steam     = _srow.get("team_name", "")
                    _srole     = _srow.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
                    _src       = role_color(_srole) if _srole else "#334155"
                    _sscore    = float(_srow.get(score_col, 0) or 0)
                    _sage_raw  = _srow.get("age")
                    _sage      = int(_sage_raw) if pd.notna(_sage_raw) else None
                    _sflag     = LEAGUE_FLAGS.get(_srow.get("league", ""), "") if has_league_col else ""
                    _same_role = bool(_srole and _srole == prim_role)

                    if _ref_age and _sage:
                        _age_diff  = _sage - _ref_age
                        _age_col   = "#22c55e" if _age_diff < 0 else "#f59e0b" if _age_diff <= 2 else "#ef4444"
                        _age_str   = f"+{_age_diff}" if _age_diff > 0 else str(_age_diff)
                        _age_html  = (f'<span style="color:{_age_col};font-weight:600">'
                                      f'{_sage} yrs ({_age_str})</span>')
                    else:
                        _age_html  = f'<span style="color:#64748b">{_sage or "—"} yrs</span>'

                    if _same_role:
                        _header_right = (
                            f'<span style="background:{_src}22;color:{_src};'
                            f'border:1px solid {_src}44;border-radius:20px;'
                            f'padding:1px 7px;font-size:0.62rem;font-weight:700">Same role</span>'
                        )
                    else:
                        _header_right = '<span style="font-size:0.68rem;color:#94a3b8">match</span>'

                    _all_diffs = sorted(
                        [(m, ov - rv) for m, rv, ov in zip(_sim_metrics_sr, _ref_vec, _sov)],
                        key=lambda x: x[1], reverse=True,
                    )
                    _edges = [(m, d) for m, d in _all_diffs if d >= 6][:2]
                    _gaps  = [(m, d) for m, d in reversed(_all_diffs) if d <= -6][:2]

                    _delta_rows = ""
                    for _dm, _diff in _edges:
                        _delta_rows += (
                            f'<div style="display:flex;justify-content:space-between;'
                            f'align-items:center;padding:2px 0">'
                            f'<span style="font-size:0.65rem;color:#64748b;max-width:76%;'
                            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                            f'{label(_dm)}</span>'
                            f'<span style="font-size:0.67rem;font-weight:700;color:#22c55e">'
                            f'+{_diff:.0f}</span></div>'
                        )
                    for _dm, _diff in _gaps:
                        _delta_rows += (
                            f'<div style="display:flex;justify-content:space-between;'
                            f'align-items:center;padding:2px 0">'
                            f'<span style="font-size:0.65rem;color:#64748b;max-width:76%;'
                            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                            f'{label(_dm)}</span>'
                            f'<span style="font-size:0.67rem;font-weight:700;color:#ef4444">'
                            f'{_diff:.0f}</span></div>'
                        )
                    if not _delta_rows:
                        _delta_rows = '<div style="font-size:0.65rem;color:#94a3b8">Nearly identical profiles</div>'

                    _sim_color = (
                        "#22c55e" if _ssim >= 80 else
                        "#f59e0b" if _ssim >= 70 else
                        "#94a3b8"
                    )

                    with _sim_cols[_si]:
                        st.markdown(
                            f'<div style="background:#1e293b;border-radius:10px;padding:14px 12px;'
                            f'border-top:3px solid {_sim_color}">'
                            f'<div style="display:flex;align-items:center;'
                            f'justify-content:space-between;margin-bottom:6px">'
                            f'<span style="font-size:1.4rem;font-weight:800;color:{_sim_color}">'
                            f'{_ssim:.0f}%</span>'
                            f'{_header_right}'
                            f'</div>'
                            f'<div style="background:#0f172a;border-radius:4px;height:4px;margin-bottom:10px">'
                            f'<div style="background:{_sim_color};border-radius:4px;height:4px;'
                            f'width:{min(_ssim,100):.0f}%"></div>'
                            f'</div>'
                            f'<div style="font-weight:700;color:#f1f5f9;font-size:0.88rem;'
                            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:2px">'
                            f'{_sname}</div>'
                            f'<div style="font-size:0.70rem;color:#64748b;margin-bottom:8px">'
                            f'{_sflag} {_steam} · {_age_html}</div>'
                            f'<div style="margin-bottom:10px">'
                            f'<span style="background:{_src}22;color:{_src};border:1px solid {_src}44;'
                            f'border-radius:20px;padding:2px 8px;font-size:0.68rem;font-weight:600">'
                            f'{_srole}</span>'
                            f'<span style="float:right;font-size:0.70rem;color:#94a3b8;'
                            f'font-weight:600">{_sscore:.0f}</span>'
                            f'</div>'
                            f'<div style="border-top:1px solid #334155;padding-top:8px">'
                            f'<div style="font-size:0.60rem;color:#94a3b8;margin-bottom:4px;'
                            f'text-transform:uppercase;letter-spacing:0.6px">'
                            f'vs {selected_player.split()[-1]}</div>'
                            f'{_delta_rows}'
                            f'</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
            else:
                st.caption("Not enough players in the current filter to compute similarity. "
                           "Broaden the sidebar filters to include more players.")

            # ── Match Log ──────────────────────────────────────────────────
            st.markdown("---")
            st.markdown('<p class="section-title">Match Log</p>', unsafe_allow_html=True)
            st.caption("All fixtures this season. DNP = did not appear in the match.")

            player_id_val = row.get("player_id")
            team_id_val   = row.get("team_id")

            if (
                player_id_val is not None
                and team_id_val is not None
                and not matches_df.empty
                and not raw_players_df.empty
            ):
                match_log = DataLoader.build_match_log(
                    player_id  = float(player_id_val),
                    team_id    = int(team_id_val),
                    matches_df = matches_df,
                    raw_players_df = raw_players_df,
                )

                if not match_log.empty:
                    RESULT_COLORS = {"W": "#22c55e", "D": "#94a3b8", "L": "#ef4444", "?": "#64748b"}
                    DNP_COLOR = "#253347"

                    _played = match_log[match_log["status"] != "DNP"].copy().reset_index(drop=True)
                    _dnp_count   = (match_log["status"] == "DNP").sum()
                    _w = (match_log["result"] == "W").sum()
                    _d = (match_log["result"] == "D").sum()
                    _l = (match_log["result"] == "L").sum()
                    _avg_mins    = _played["minutes_played"].mean() if len(_played) else 0
                    _starts      = (_played["status"] == "Started").sum() if "status" in _played.columns else len(_played)
                    _subs        = len(_played) - _starts
                    _total_goals = int(_played["goals"].sum()) if "goals" in _played.columns else 0
                    _total_assts = int(_played["assists"].sum()) if "assists" in _played.columns else 0
                    _total_kp    = int(_played["key_passes"].sum()) if "key_passes" in _played.columns else 0

                    # ── Contributions badges ───────────────────────────────
                    _contrib_badges = (
                        f'<span style="background:#22c55e22;color:#22c55e;border:1px solid #22c55e44;'
                        f'border-radius:5px;padding:1px 7px;font-size:0.72rem;font-weight:700;margin-right:4px">'
                        f'⚽ {_total_goals}</span>'
                        f'<span style="background:#0095ff22;color:#60a5fa;border:1px solid #0095ff44;'
                        f'border-radius:5px;padding:1px 7px;font-size:0.72rem;font-weight:700;margin-right:4px">'
                        f'A {_total_assts}</span>'
                        f'<span style="background:#f59e0b22;color:#fbbf24;border:1px solid #f59e0b44;'
                        f'border-radius:5px;padding:1px 7px;font-size:0.72rem;font-weight:700">'
                        f'KP {_total_kp}</span>'
                    )

                    # ── Last-5 form strip + narrative ──────────────────────
                    _last5 = match_log[match_log["status"] != "DNP"].tail(5)
                    _form_metric_candidates = {
                        "Creator":         "key_passes",
                        "Ball Progressor": "successful_dribbles",
                        "Box Threat":      "shots",
                        "Deep Builder":    "progressive_passes",
                    }
                    _form_col = _form_metric_candidates.get(prim_role, "key_passes")
                    _form_col = _form_col if _form_col in _played.columns else (
                        "key_passes" if "key_passes" in _played.columns else None
                    )
                    _form_label = METRIC_LABELS.get(f"{_form_col}_p90", (_form_col or "").replace("_", " ").title())

                    _l5_html = ""
                    for _, _fr in _last5.iterrows():
                        _fc   = RESULT_COLORS.get(_fr["result"], "#334155")
                        _opp  = str(_fr["opponent"])[:7]
                        _scr  = str(_fr.get("score", ""))
                        _l5_html += (
                            f'<div style="text-align:center;flex:1">'
                            f'<div style="background:{_fc};border-radius:5px;height:28px;'
                            f'display:flex;align-items:center;justify-content:center;'
                            f'font-size:0.78rem;font-weight:800;color:#0f172a">{_fr["result"]}</div>'
                            f'<div style="font-size:0.58rem;color:#64748b;margin-top:3px;'
                            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{_opp}</div>'
                            f'<div style="font-size:0.56rem;color:#94a3b8">{_scr}</div>'
                            f'</div>'
                        )

                    _l5_wins = (_last5["result"] == "W").sum()
                    _form_phrase = (
                        "in excellent recent form" if _l5_wins >= 4 else
                        "in good recent form"      if _l5_wins >= 3 else
                        "in mixed form"            if _l5_wins >= 2 else
                        "in poor recent form"
                    )
                    _form_color = (
                        "#22c55e" if _l5_wins >= 4 else
                        "#22c55e" if _l5_wins >= 3 else
                        "#f59e0b" if _l5_wins >= 2 else
                        "#ef4444"
                    )
                    _starter_phrase = (
                        f"a regular starter — {_starts} starts"
                        if _starts >= len(_played) * 0.7
                        else f"mainly from the bench — {_starts} starts, {_subs} subs"
                    )

                    _narr_extra = ""
                    if _form_col and len(_played) > 0 and _form_col in _played.columns:
                        _best_idx   = _played[_form_col].idxmax()
                        _best_row   = _played.loc[_best_idx]
                        _best_val   = int(_best_row[_form_col])
                        _best_opp   = _best_row.get("opponent", "")
                        _season_avg = _played[_form_col].mean()
                        if _best_val > 0:
                            _narr_extra = (
                                f" Peak game: <b style='color:#f1f5f9'>{_best_val} {_form_label}</b>"
                                f" vs {_best_opp}."
                            )
                        _consistent_pct = (_played[_form_col] >= _season_avg).mean() * 100
                        if _consistent_pct >= 60:
                            _narr_extra += (
                                f" Hits season avg in <b style='color:#f1f5f9'>"
                                f"{_consistent_pct:.0f}%</b> of games."
                            )

                    _narrative_log = (
                        f'<b style="color:#f1f5f9">{_surname}</b> is {_starter_phrase}, '
                        f'averaging <b style="color:#f1f5f9">{_avg_mins:.0f} min</b> per appearance. '
                        f'Currently <b style="color:{_form_color}">{_form_phrase}</b> '
                        f'<span style="color:#64748b">({_l5_wins}W from last 5)</span>.'
                        f'{_narr_extra}'
                    )

                    _l5_label = "Last 5" if len(_last5) == 5 else f"Last {len(_last5)}"

                    _record_v = (
                        f'<span style="color:#22c55e;font-weight:700">{_w}W</span>'
                        f'<span style="color:#94a3b8"> · </span>'
                        f'<span style="color:#94a3b8;font-weight:700">{_d}D</span>'
                        f'<span style="color:#94a3b8"> · </span>'
                        f'<span style="color:#ef4444;font-weight:700">{_l}L</span>'
                    )

                    def _stat_row(lbl, value_html):
                        return (
                            f'<div style="display:flex;justify-content:space-between;'
                            f'align-items:center;padding:9px 0;border-bottom:1px solid #0f172a">'
                            f'<span style="font-size:0.78rem;color:#64748b">{lbl}</span>'
                            f'<span style="font-size:0.92rem;font-weight:700;color:#f1f5f9">{value_html}</span>'
                            f'</div>'
                        )

                    _stats_rows = (
                        _stat_row("Appearances", f"{len(_played)}")
                        + _stat_row("Usage", f"{_starts} starts · {_subs} sub")
                        + _stat_row("Avg Minutes", f"{_avg_mins:.0f}′")
                        + _stat_row("Record", _record_v)
                        + _stat_row("Contributions", _contrib_badges)
                        + (_stat_row("DNP", f'<span style="color:#94a3b8">{_dnp_count}</span>') if _dnp_count else "")
                    )

                    st.markdown(
                        f'<div style="display:flex;gap:12px;align-items:stretch;margin-bottom:14px">'
                        f'<div style="flex:2;background:#1e293b;border-radius:12px;'
                        f'border:1px solid #334155;padding:14px 18px">'
                        f'<p style="margin:0 0 4px;font-size:0.60rem;font-weight:600;color:#94a3b8;'
                        f'text-transform:uppercase;letter-spacing:0.8px">Season Stats</p>'
                        f'{_stats_rows}'
                        f'</div>'
                        f'<div style="flex:3;background:#1e293b;border-radius:12px;'
                        f'border:1px solid #334155;overflow:hidden;display:flex;flex-direction:column">'
                        f'<div style="padding:14px 18px;border-bottom:1px solid #334155">'
                        f'<p style="margin:0 0 10px;font-size:0.60rem;font-weight:600;color:#94a3b8;'
                        f'text-transform:uppercase;letter-spacing:0.8px">{_l5_label} Results</p>'
                        f'<div style="display:flex;gap:6px">{_l5_html}</div>'
                        f'</div>'
                        f'<div style="padding:14px 18px;border-left:4px solid {bar_col};flex:1">'
                        f'<p style="margin:0 0 6px;font-size:0.60rem;font-weight:600;color:#94a3b8;'
                        f'text-transform:uppercase;letter-spacing:0.8px">Season Narrative</p>'
                        f'<p style="margin:0;font-size:0.86rem;color:#cbd5e1;line-height:1.65">'
                        f'{_narrative_log}</p>'
                        f'</div>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # ── Timeline bar chart + creation overlay ──────────────
                    match_log["bar_color"] = match_log.apply(
                        lambda r: DNP_COLOR if r["status"] == "DNP"
                                  else RESULT_COLORS.get(r["result"], "#334155"),
                        axis=1,
                    )
                    match_log["x_label"] = match_log.apply(
                        lambda r: f"{r['venue']} {str(r['opponent'])[:10]}", axis=1
                    )
                    _seen_labels: dict[str, int] = {}
                    _unique_labels = []
                    for _xl in match_log["x_label"]:
                        _seen_labels[_xl] = _seen_labels.get(_xl, 0) + 1
                        _unique_labels.append(_xl if _seen_labels[_xl] == 1 else f"{_xl} ({_seen_labels[_xl]})")
                    match_log["x_label"] = _unique_labels

                    match_log["hover_text"] = match_log.apply(
                        lambda r: (
                            f"<b>{r['opponent']}</b> ({r['venue']})<br>"
                            f"{r['date'].strftime('%d %b')} · {r['score']} · {r['result']}<br>"
                            f"{r['status']} · {r['minutes_played']}'"
                            + (
                                f"<br>Goals: {int(r.get('goals',0))}  Assists: {int(r.get('assists',0))}"
                                f"  Key passes: {int(r.get('key_passes',0))}"
                                if r["status"] != "DNP" else ""
                            )
                        ),
                        axis=1,
                    )

                    def _bar_label(r):
                        if r["status"] == "DNP":
                            return ""
                        parts = []
                        if r.get("goals", 0) > 0:
                            parts.extend(["⚽"] * int(r["goals"]))
                        if r.get("assists", 0) > 0:
                            parts.extend(["🎯"] * int(r["assists"]))
                        return " ".join(parts)

                    match_log["bar_label"] = match_log.apply(_bar_label, axis=1)

                    fig_log = go.Figure()
                    fig_log.add_trace(go.Bar(
                        x=match_log["x_label"],
                        y=match_log["minutes_played"],
                        marker_color=match_log["bar_color"].tolist(),
                        marker_line_width=0,
                        text=match_log["bar_label"],
                        textposition="inside",
                        textfont=dict(size=11),
                        hovertext=match_log["hover_text"],
                        hoverinfo="text",
                        showlegend=False,
                    ))
                    for _rl, _rc in [("Win","#22c55e"),("Draw","#94a3b8"),("Loss","#ef4444"),("DNP",DNP_COLOR)]:
                        fig_log.add_trace(go.Bar(
                            x=[None], y=[None], marker_color=_rc,
                            marker_line_color="#334155", marker_line_width=1,
                            name=_rl, showlegend=True,
                        ))
                    fig_log.add_hline(y=90, line_dash="dot",
                                      line_color="rgba(255,255,255,0.12)", line_width=1)
                    fig_log.update_layout(**dark_layout(
                        height=240,
                        barmode="overlay",
                        xaxis=dict(
                            tickangle=-35, tickfont=dict(size=9, color=D_TICK),
                            showgrid=False, categoryorder="array",
                            categoryarray=match_log["x_label"].tolist(),
                        ),
                        yaxis=dict(title="Minutes", range=[0, 105], gridcolor=D_GRID, color=D_TICK, dtick=30),
                        legend=dict(
                            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                            font=dict(size=10, color=D_TEXT), bgcolor="rgba(0,0,0,0)",
                        ),
                        margin=dict(l=10, r=10, t=30, b=70),
                    ))
                    st.plotly_chart(fig_log, use_container_width=True)

                    # ── Chart 2: Per-match bars + 3-game avg lines ─────────
                    _form_col2_candidates = {
                        "Creator":         "assists",
                        "Ball Progressor": "progressive_passes",
                        "Box Threat":      "key_passes",
                        "Deep Builder":    "key_passes",
                    }
                    _form_col2 = _form_col2_candidates.get(prim_role, "assists")
                    _form_col2 = (
                        _form_col2
                        if (_form_col2 and _form_col2 in _played.columns and _form_col2 != _form_col)
                        else None
                    )
                    _form_label2 = METRIC_LABELS.get(
                        f"{_form_col2}_p90", (_form_col2 or "").replace("_", " ").title()
                    ) if _form_col2 else None

                    if _form_col and len(_played) >= 3:
                        _played_log = match_log[match_log["status"] != "DNP"].copy()
                        _x = _played_log["x_label"].tolist()

                        def _metric_chart(col, lbl, color):
                            _vals  = _played_log[col]
                            _roll  = _vals.rolling(3, min_periods=1).mean()
                            _fig   = go.Figure()
                            _fig.add_trace(go.Bar(
                                x=_x, y=_vals, name=lbl,
                                marker_color=color, opacity=0.45, marker_line_width=0,
                                hovertemplate="%{x}<br>" + lbl + ": %{y}<extra></extra>",
                            ))
                            _fig.add_trace(go.Scatter(
                                x=_x, y=_roll, name="3-game avg",
                                mode="lines+markers",
                                line=dict(color=color, width=2),
                                marker=dict(size=4, color=color),
                                hovertemplate="%{x}<br>3-game avg: %{y:.1f}<extra></extra>",
                                connectgaps=False,
                            ))
                            _fig.update_layout(**dark_layout(
                                height=200,
                                margin=dict(l=10, r=10, t=34, b=70),
                                xaxis=dict(
                                    tickangle=-35, tickfont=dict(size=9, color=D_TICK),
                                    showgrid=False, categoryorder="array", categoryarray=_x,
                                ),
                                yaxis=dict(gridcolor=D_GRID, color=D_TICK, rangemode="tozero", dtick=1),
                                legend=dict(
                                    orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                                    font=dict(size=10, color=D_TEXT), bgcolor="rgba(0,0,0,0)",
                                ),
                                title=dict(text=lbl, font=dict(size=11, color=D_TICK), x=0),
                            ))
                            return _fig

                        col_f1, col_f2 = st.columns(2)
                        with col_f1:
                            st.plotly_chart(
                                _metric_chart(_form_col, _form_label, bar_col),
                                use_container_width=True,
                            )
                        with col_f2:
                            if _form_col2:
                                st.plotly_chart(
                                    _metric_chart(_form_col2, _form_label2, "#f59e0b"),
                                    use_container_width=True,
                                )

                    # ── Per-match stats table ───────────────────────────────
                    tbl_cols = ["date", "venue", "opponent", "score", "result", "status",
                                "minutes_played", "goals", "assists", "key_passes",
                                "through_balls", "successful_dribbles", "crosses",
                                "progressive_passes", "shots"]
                    avail_tbl = [c for c in tbl_cols if c in match_log.columns]
                    tbl_log = match_log[avail_tbl].copy()
                    tbl_log["date"] = tbl_log["date"].dt.strftime("%d %b")

                    col_rename = {
                        "date": "Date", "venue": "H/A", "opponent": "Opponent",
                        "score": "Score", "result": "Result", "status": "Status",
                        "minutes_played": "Mins", "goals": "G", "assists": "A",
                        "key_passes": "KP", "through_balls": "TB",
                        "successful_dribbles": "Drb", "crosses": "Crs",
                        "progressive_passes": "PrgP", "shots": "Sh",
                    }
                    tbl_log.columns = [col_rename.get(c, c) for c in avail_tbl]

                    st.dataframe(
                        tbl_log,
                        use_container_width=True,
                        hide_index=True,
                        height=min(35 * len(tbl_log) + 38, 480),
                        column_config={
                            "Mins": st.column_config.ProgressColumn(
                                "Mins", min_value=0, max_value=95, format="%d'"
                            ),
                        },
                    )
                else:
                    st.caption("Match log unavailable — run the pipeline to generate processed data.")
            else:
                st.caption("Match log unavailable — processed data not found.")

        else:
            st.info("No players match the current filters.")
