"""Dataclasses for filter state and application state."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class FilterState:
    position_group: str
    min_mins: int
    age_range: tuple
    selected_positions: list
    selected_leagues: list
    selected_teams: list
    selected_roles: list
    selected_feasibility: list
    market_value_range: tuple


@dataclass
class AppState:
    df: pd.DataFrame
    filtered: pd.DataFrame
    group_df: pd.DataFrame
    raw_players_df: pd.DataFrame
    matches_df: pd.DataFrame
    position_group: str
    group_cfg: dict
    # feature flags
    has_archetypes: bool
    has_tm_data: bool
    has_roles: bool
    has_league_col: bool
    # collections
    all_roles: list
    role_score_cols: list
    core_metrics: list
    pct_cols: list
    all_leagues: list
    score_col: str
    rename_map: dict
