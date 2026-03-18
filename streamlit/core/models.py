"""Dataclasses for filter state and application state."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class FilterState:
    min_mins: int
    age_range: tuple
    selected_positions: list
    selected_leagues: list
    selected_teams: list
    selected_roles: list
    percentile_mode: str
    selected_feasibility: list
    market_value_range: tuple


@dataclass
class AppState:
    df: pd.DataFrame
    filtered: pd.DataFrame
    raw_players_df: pd.DataFrame
    matches_df: pd.DataFrame
    # feature flags
    has_archetypes: bool
    has_tm_data: bool
    has_roles: bool
    has_league_col: bool
    has_league_scores: bool
    # collections
    all_roles: list
    role_score_cols: list
    role_score_cols_league: list
    core_metrics: list
    pct_cols: list
    pct_cols_league: list
    all_leagues: list
    score_col: str
    # active percentile state
    league_mode: bool
    active_pct_suffix: str
    active_role_score_cols: list
    active_primary_role_col: str
    rename_map: dict

    def player_view_dict(self, row: pd.Series) -> dict:
        """Returns player dict with {m}_pct remapped to the correct percentile column."""
        d = row.to_dict()
        pct_suffix = self.active_pct_suffix
        if pct_suffix != "_pct":
            for m in self.core_metrics:
                key = f"{m}{pct_suffix}"
                if key in d:
                    d[f"{m}_pct"] = d[key]
        return d
