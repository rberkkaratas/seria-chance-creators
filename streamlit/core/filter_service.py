"""Filter application and AppState construction."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd

import config
from core.models import FilterState, AppState
from core.constants import label, role_score_col


class FilterService:
    @staticmethod
    def apply(
        df: pd.DataFrame,
        state: FilterState,
        has_roles: bool,
        has_league_col: bool,
        has_tm_data: bool,
    ) -> pd.DataFrame:
        group_cfg = config.POSITION_GROUPS[state.position_group]
        all_roles = list(group_cfg["roles"].keys())
        all_leagues = sorted(df["league"].dropna().unique().tolist()) if has_league_col else []

        mask = pd.Series(True, index=df.index)
        if config.POSITION_GROUP_COL in df.columns:
            mask &= df[config.POSITION_GROUP_COL] == state.position_group

        mask &= df["minutes_played"] >= state.min_mins
        if "age" in df.columns:
            mask &= (df["age"] >= state.age_range[0]) & (df["age"] <= state.age_range[1])
        if state.selected_positions:
            mask &= df["position"].isin(state.selected_positions)
        if has_league_col and state.selected_leagues and len(state.selected_leagues) < len(all_leagues):
            mask &= df["league"].isin(state.selected_leagues)
        if state.selected_teams:
            mask &= df["team_name"].isin(state.selected_teams)
        role_filter_col = (
            "primary_role_league"
            if state.percentile_mode == "Within league" and "primary_role_league" in df.columns
            else config.PRIMARY_ROLE_COL
        )
        if has_roles and state.selected_roles and len(state.selected_roles) < len(all_roles):
            mask &= df[role_filter_col].isin(state.selected_roles)
        if has_tm_data and state.selected_feasibility:
            mask &= df["transfer_feasibility"].isin(state.selected_feasibility)
        if has_tm_data and "market_value_eur" in df.columns and hasattr(state, "market_value_range"):
            lo, hi = state.market_value_range[0] * 1_000_000, state.market_value_range[1] * 1_000_000
            _mv = df["market_value_eur"].fillna(0)
            mask &= (_mv >= lo) & (_mv <= hi)

        return df[mask].copy()

    @staticmethod
    def build_app_state(
        df: pd.DataFrame,
        filtered: pd.DataFrame,
        raw_players_df: pd.DataFrame,
        matches_df: pd.DataFrame,
        state: FilterState,
        cfg,
    ) -> AppState:
        group_cfg         = cfg.POSITION_GROUPS[state.position_group]
        group_df          = (
            df[df[cfg.POSITION_GROUP_COL] == state.position_group].copy()
            if cfg.POSITION_GROUP_COL in df.columns else df.copy()
        )
        has_archetypes    = "archetype" in df.columns
        has_tm_data       = "market_value_eur" in df.columns
        has_roles         = cfg.PRIMARY_ROLE_COL in df.columns
        has_league_col    = "league" in df.columns
        all_roles         = list(group_cfg["roles"].keys())
        rsc_cols          = [role_score_col(r) for r in all_roles if role_score_col(r) in df.columns]
        rsc_cols_league   = [
            f"{cfg.ROLE_SCORE_COL_PREFIX}{r}_league" for r in all_roles
            if f"{cfg.ROLE_SCORE_COL_PREFIX}{r}_league" in df.columns
        ]
        has_league_scores = bool(rsc_cols_league)
        core_metrics      = [m for m in group_cfg["radar_metrics"] if m in df.columns]
        pct_cols          = [f"{m}_pct" for m in core_metrics if f"{m}_pct" in df.columns]
        pct_cols_league   = [f"{m}_league_pct" for m in core_metrics if f"{m}_league_pct" in df.columns]
        score_col         = cfg.OVERALL_SCORE_COL
        all_leagues       = sorted(df["league"].dropna().unique().tolist()) if has_league_col else []

        _league_mode           = (state.percentile_mode == "Within league") and has_league_scores
        active_pct_suffix      = "_league_pct" if _league_mode else "_pct"
        active_role_score_cols = rsc_cols_league if _league_mode else rsc_cols
        active_primary_role_col = (
            "primary_role_league"
            if _league_mode and "primary_role_league" in df.columns
            else cfg.PRIMARY_ROLE_COL
        )

        rename_map = {
            "player_name": "Player", "team_name": "Team", "position": "Pos",
            "age": "Age", "minutes_played": "Mins",
            "appearances": "Apps", "starts": "Starts",
            "start_rate": "Start %", "minutes_per_appearance": "Mins/App",
            cfg.SCORE_CONFIDENCE_COL: "Score Confidence",
            cfg.SAMPLE_TIER_COL: "Sample",
            "league": "League",
            "archetype": "Archetype",
            cfg.PRIMARY_ROLE_COL: "Role",
            score_col: "Overall Score",
        }
        rename_map.update({m: label(m) for m in core_metrics})
        rename_map.update({role_score_col(r): r for r in all_roles})
        rename_map.update({f"{cfg.ROLE_SCORE_COL_PREFIX}{r}_league": r for r in all_roles})
        rename_map["primary_role_league"] = "Role"

        return AppState(
            df=df,
            filtered=filtered,
            group_df=group_df,
            raw_players_df=raw_players_df,
            matches_df=matches_df,
            position_group=state.position_group,
            group_cfg=group_cfg,
            has_archetypes=has_archetypes,
            has_tm_data=has_tm_data,
            has_roles=has_roles,
            has_league_col=has_league_col,
            has_league_scores=has_league_scores,
            all_roles=all_roles,
            role_score_cols=rsc_cols,
            role_score_cols_league=rsc_cols_league,
            core_metrics=core_metrics,
            pct_cols=pct_cols,
            pct_cols_league=pct_cols_league,
            all_leagues=all_leagues,
            score_col=score_col,
            league_mode=_league_mode,
            active_pct_suffix=active_pct_suffix,
            active_role_score_cols=active_role_score_cols,
            active_primary_role_col=active_primary_role_col,
            rename_map=rename_map,
        )
