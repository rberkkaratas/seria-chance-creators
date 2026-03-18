"""Filter widgets rendering."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

import config
from core.models import FilterState
from core.constants import league_badge


def render_filters(
    df: pd.DataFrame,
    has_league_col: bool,
    has_tm_data: bool,
    all_roles: list,
    all_leagues: list,
    cfg,
) -> FilterState:
    """Render inline filter widgets and return a FilterState."""
    _fc1, _fc2, _fc3, _fc4 = st.columns(4)

    with _fc1:
        st.caption("Playing Time")
        min_mins = st.slider(
            "Min. minutes played",
            min_value=0,
            max_value=int(df["minutes_played"].max()) if "minutes_played" in df.columns else 2000,
            value=cfg.MIN_MINUTES_PLAYED,
            step=90,
            label_visibility="collapsed",
        )
        st.caption(f"Min. **{min_mins}** min")

        if "age" in df.columns:
            st.caption("Age Range")
            age_min = int(df["age"].min())
            age_max = int(df["age"].max())
            age_range = st.slider(
                "Age range", age_min, age_max, (age_min, int(cfg.MAX_AGE)),
                label_visibility="collapsed",
            )
            st.caption(f"**{age_range[0]} – {age_range[1]}** yrs")
        else:
            age_range = (0, 99)

        if has_tm_data and "market_value_eur" in df.columns:
            _mv_vals = df["market_value_eur"].dropna()
            _mv_min  = int(_mv_vals.min() / 1_000_000)
            _mv_max  = int(_mv_vals.max() / 1_000_000) + 1
            st.caption("Market Value (€M)")
            market_value_range = st.slider(
                "Market value range", _mv_min, _mv_max, (_mv_min, _mv_max),
                step=1,
                label_visibility="collapsed",
            )
            st.caption(f"**€{market_value_range[0]}M – €{market_value_range[1]}M**")
        else:
            market_value_range = (0, 9999)

    with _fc2:
        if "position" in df.columns:
            st.caption("Positions")
            all_positions = sorted(df["position"].dropna().unique().tolist())
            selected_positions = st.multiselect(
                "Positions", options=all_positions, default=all_positions,
                label_visibility="collapsed",
            )
        else:
            selected_positions = []

        st.caption("Role")
        selected_roles = st.multiselect(
            "Midfielder role", options=all_roles, default=all_roles,
            label_visibility="collapsed",
        )

    with _fc3:
        if has_league_col:
            st.caption("Leagues")
            selected_leagues = st.multiselect(
                "Leagues", options=all_leagues, default=all_leagues,
                label_visibility="collapsed",
                format_func=league_badge,
            )
        else:
            selected_leagues = []

        st.caption("Teams")
        _league_mask_teams = (
            df["league"].isin(selected_leagues) if has_league_col and selected_leagues else pd.Series(True, index=df.index)
        )
        all_teams = sorted(df.loc[_league_mask_teams, "team_name"].dropna().unique().tolist())
        selected_teams = st.multiselect(
            "Teams", options=all_teams, default=[],
            label_visibility="collapsed",
            placeholder="All teams",
        )

    with _fc4:
        if has_league_col and len(all_leagues) > 1:
            st.caption("Percentile Mode")
            percentile_mode = st.radio(
                "Percentile mode",
                options=["All leagues", "Within league"],
                index=0,
                label_visibility="collapsed",
                help="Controls how role scores and radar percentiles are computed.",
            )
        else:
            percentile_mode = "All leagues"

        if has_tm_data:
            st.caption("Transfer Feasibility")
            all_feasibility = ["Expiring", "Mid-term", "Locked", "Unknown"]
            selected_feasibility = st.multiselect(
                "Transfer feasibility", options=all_feasibility, default=all_feasibility,
                label_visibility="collapsed",
            )
        else:
            selected_feasibility = ["Expiring", "Mid-term", "Locked", "Unknown"]

    return FilterState(
        min_mins=min_mins,
        age_range=age_range,
        selected_positions=selected_positions,
        selected_leagues=selected_leagues,
        selected_teams=selected_teams,
        selected_roles=selected_roles,
        percentile_mode=percentile_mode,
        selected_feasibility=selected_feasibility,
        market_value_range=market_value_range,
    )
