"""Header rendering component."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd

import config
from core.models import AppState
from core.constants import league_badge, role_color, LEAGUE_FLAGS, LEAGUE_DISPLAY


def render_header(placeholder, state: AppState) -> None:
    """Fill the header placeholder with KPIs and title block."""
    filtered = state.filtered
    has_league_col = state.has_league_col
    has_roles = state.has_roles
    score_col = state.score_col

    n_leagues_shown = filtered["league"].nunique() if has_league_col and len(filtered) else 1
    _league_label   = "Top 5 Leagues" if n_leagues_shown > 1 else (
        league_badge(filtered["league"].iloc[0]) if has_league_col and len(filtered) else "Serie A"
    )

    _hdr_n_teams     = filtered["team_name"].nunique() if len(filtered) else 0
    _hdr_top_row     = filtered.nlargest(1, score_col) if len(filtered) else filtered
    _hdr_top_player  = _hdr_top_row["player_name"].values[0] if len(_hdr_top_row) else "—"
    _hdr_top_score   = float(_hdr_top_row[score_col].values[0]) if len(_hdr_top_row) else 0.0
    _hdr_top_role    = _hdr_top_row[config.PRIMARY_ROLE_COL].values[0] if has_roles and len(_hdr_top_row) else ""
    _hdr_top_rc      = role_color(_hdr_top_role) if _hdr_top_role else "#0095FF"

    if has_roles and len(filtered) and config.PRIMARY_ROLE_COL in filtered.columns:
        _hdr_mode_role = filtered[config.PRIMARY_ROLE_COL].mode()
        _hdr_common_role = _hdr_mode_role[0] if len(_hdr_mode_role) else "—"
    else:
        _hdr_common_role = "—"
    _hdr_common_rc = role_color(_hdr_common_role) if _hdr_common_role != "—" else "#94a3b8"

    placeholder.markdown(
        # Title block
        f'<div style="padding:12px 0 28px">'
        f'<div style="font-size:0.75rem;font-weight:600;color:#0095FF;letter-spacing:2px;'
        f'text-transform:uppercase;margin-bottom:12px">Midfielder Scout</div>'
        f'<div style="font-size:2.8rem;font-weight:800;color:#f1f5f9;letter-spacing:-1px;'
        f'line-height:1.1;margin-bottom:12px">{_league_label} · 2025/26</div>'
        f'<div style="font-size:0.95rem;color:#64748b;line-height:1.7;max-width:600px;margin-bottom:28px">'
        f'A data-driven scouting tool profiling qualified midfielders across four tactical roles — '
        f'Creator, Ball Progressor, Box Threat, and Deep Builder — using WhoScored match event data.'
        f'</div>'
        # KPI row
        f'<div style="display:flex;gap:36px;flex-wrap:wrap;padding-top:20px;'
        f'border-top:1px solid #1e293b">'

        f'<div>'
        f'<div style="font-size:2rem;font-weight:800;color:#f1f5f9;line-height:1">{len(filtered)}</div>'
        f'<div style="font-size:0.75rem;color:#94a3b8;margin-top:4px">Players</div>'
        f'</div>'

        f'<div style="width:1px;background:#1e293b;align-self:stretch"></div>'

        f'<div>'
        f'<div style="font-size:2rem;font-weight:800;color:#f1f5f9;line-height:1">{_hdr_n_teams}</div>'
        f'<div style="font-size:0.75rem;color:#94a3b8;margin-top:4px">Teams</div>'
        f'</div>'

        f'<div style="width:1px;background:#1e293b;align-self:stretch"></div>'

        f'<div>'
        f'<div style="font-size:1.3rem;font-weight:700;color:{_hdr_common_rc};line-height:1.2">{_hdr_common_role}</div>'
        f'<div style="font-size:0.75rem;color:#94a3b8;margin-top:4px">Most common role</div>'
        f'</div>'

        f'<div style="width:1px;background:#1e293b;align-self:stretch"></div>'

        f'<div>'
        f'<div style="font-size:1.3rem;font-weight:700;color:{_hdr_top_rc};line-height:1.2">{_hdr_top_player}</div>'
        f'<div style="font-size:0.75rem;color:#94a3b8;margin-top:4px">Top ranked &nbsp;·&nbsp; {_hdr_top_score:.0f}</div>'
        f'</div>'

        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
