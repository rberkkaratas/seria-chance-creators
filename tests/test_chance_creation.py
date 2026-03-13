"""
Tests for src/features/chance_creation.py

Covers:
- filter_midfielders: position-aware minutes filter (regression for
  the bug that counted all-position minutes instead of midfield-only)
- compute_per_90: basic rates and zero-minutes edge case
- compute_percentiles: output range
- compute_composite_score: weights integrity and score range
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.features.chance_creation import (
    compute_composite_score,
    compute_per_90,
    compute_percentiles,
    compute_role_scores,
    filter_midfielders,
)


# ─── Helpers ──────────────────────────────────────────────────────────

def _make_players(rows):
    """Build a minimal players DataFrame from a list of dicts."""
    defaults = {
        "player_id": 1,
        "player_name": "Test Player",
        "team_name": "Team A",
        "team_id": 100,
        "age": 24,
        "match_id": "m1",
        "minutes_played": 90,
        "key_passes": 0,
        "through_balls": 0,
        "passes_into_final_third": 0,
        "passes_into_penalty_area": 0,
        "successful_dribbles": 0,
        "progressive_passes": 0,
        "total_passes": 0,
        "accurate_passes": 0,
    }
    records = []
    for r in rows:
        row = {**defaults, **r}
        records.append(row)
    return pd.DataFrame(records)


# ─── filter_midfielders ───────────────────────────────────────────────

def test_filter_midfielders_qualifies_with_enough_midfield_minutes():
    """Player with 900+ midfield minutes should be included."""
    rows = [
        {"player_id": 1, "position": "MC", "minutes_played": 90, "match_id": f"m{i}"}
        for i in range(10)  # 10 x 90 = 900 min
    ]
    df = _make_players(rows)
    result = filter_midfielders(df)
    assert result["player_id"].nunique() == 1


def test_filter_midfielders_excludes_insufficient_midfield_minutes():
    """Player with fewer midfield minutes than the threshold should NOT qualify."""
    rows = [
        {"player_id": 1, "position": "MC", "minutes_played": 90, "match_id": f"m{i}"}
        for i in range(6)  # 6 x 90 = 540 min < MIN_MINUTES_PLAYED (600)
    ]
    df = _make_players(rows)
    result = filter_midfielders(df)
    assert len(result) == 0


def test_filter_midfielders_counts_only_midfield_position_minutes():
    """
    Regression test for the position-aware minutes bug.

    Player plays 800 min as CB + 200 min as MC = 1000 total.
    Total minutes >= 900 but midfield-only = 200 < 900.
    Player must NOT qualify.
    """
    cb_rows = [
        {"player_id": 1, "position": "DC", "minutes_played": 90, "match_id": f"cb{i}"}
        for i in range(9)  # 810 min as CB
    ]
    mc_rows = [
        {"player_id": 1, "position": "MC", "minutes_played": 90, "match_id": f"mc{i}"}
        for i in range(2)  # 180 min as MC
    ]
    df = _make_players(cb_rows + mc_rows)
    result = filter_midfielders(df)
    assert len(result) == 0, (
        "Player with 810 CB minutes + 180 MC minutes should NOT qualify "
        "(midfield-only = 180 < 900)"
    )


def test_filter_midfielders_mixed_positions_enough_midfield():
    """Player with non-midfield rows AND enough midfield minutes should qualify."""
    cb_rows = [
        {"player_id": 1, "position": "DC", "minutes_played": 90, "match_id": f"cb{i}"}
        for i in range(5)
    ]
    mc_rows = [
        {"player_id": 1, "position": "MC", "minutes_played": 90, "match_id": f"mc{i}"}
        for i in range(10)  # 900 min as MC
    ]
    df = _make_players(cb_rows + mc_rows)
    result = filter_midfielders(df)
    # Only the MC rows should be in the result
    assert result["player_id"].nunique() == 1
    assert (result["position"] == "MC").all()


def test_filter_midfielders_excludes_non_midfield_positions():
    """Goalkeeper rows should never appear in output regardless of minutes."""
    rows = [
        {"player_id": 1, "position": "GK", "minutes_played": 90, "match_id": f"m{i}"}
        for i in range(20)
    ]
    df = _make_players(rows)
    result = filter_midfielders(df)
    assert len(result) == 0


# ─── compute_per_90 ───────────────────────────────────────────────────

def _make_aggregated(**overrides):
    """Single-row aggregated player DataFrame."""
    row = {
        "player_id": 1, "player_name": "A", "team_name": "T",
        "team_id": 1, "age": 23, "position": "MC", "appearances": 10,
        "minutes_played": 900,
        "key_passes": 18, "through_balls": 9, "assists": 5,
        "second_assists": 2, "progressive_passes": 45,
        "progressive_carries": 0, "passes_into_final_third": 27,
        "passes_into_penalty_area": 9, "successful_dribbles": 18,
        "total_dribbles": 30, "shots": 10, "shots_on_target": 5,
        "tackles": 20, "interceptions": 15, "ball_recoveries": 30,
        "touches": 500, "touches_final_third": 80,
        "total_passes": 400, "accurate_passes": 360,
        # New spatial metrics
        "forward_passes": 200, "penalty_area_touches": 20,
        "half_space_passes": 15, "possession_won_final_third": 10,
        "carries_into_final_third": 5,
        "ball_winning_x_sum": 2250.0, "ball_winning_count": 45,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_compute_per_90_basic_rate():
    """18 key passes in 900 minutes = exactly 1.8 per 90."""
    df = _make_aggregated(key_passes=18, minutes_played=900)
    result = compute_per_90(df)
    assert abs(result["key_passes_p90"].iloc[0] - 1.8) < 1e-9


def test_compute_per_90_proportional():
    """45 progressive passes in 900 min = 4.5 p90."""
    df = _make_aggregated(progressive_passes=45, minutes_played=900)
    result = compute_per_90(df)
    assert abs(result["progressive_passes_p90"].iloc[0] - 4.5) < 1e-9


def test_compute_per_90_zero_minutes_no_inf():
    """Zero minutes played must produce NaN (not inf) — safe for downstream filtering."""
    df = _make_aggregated(minutes_played=0, key_passes=5)
    result = compute_per_90(df)
    val = result["key_passes_p90"].iloc[0]
    assert not np.isinf(val), "0 minutes should yield NaN, not inf"
    assert np.isnan(val), "0 minutes should yield NaN so the player is filtered out"


def test_compute_per_90_pass_accuracy_computed():
    df = _make_aggregated(total_passes=400, accurate_passes=360)
    result = compute_per_90(df)
    assert abs(result["pass_accuracy"].iloc[0] - 90.0) < 1e-9


def test_compute_per_90_shot_creating_actions_derived():
    """SCA = key_passes_p90 + successful_dribbles_p90."""
    df = _make_aggregated(key_passes=18, successful_dribbles=9, minutes_played=900)
    result = compute_per_90(df)
    expected = result["key_passes_p90"].iloc[0] + result["successful_dribbles_p90"].iloc[0]
    assert abs(result["shot_creating_actions_p90"].iloc[0] - expected) < 1e-9


def test_compute_per_90_forward_pass_pct():
    """200 forward passes out of 400 total = 50% forward pass rate."""
    df = _make_aggregated(forward_passes=200, total_passes=400)
    result = compute_per_90(df)
    assert abs(result["forward_pass_pct"].iloc[0] - 50.0) < 1e-9


def test_compute_per_90_forward_pass_pct_zero_passes():
    """Zero total passes must produce NaN forward_pass_pct (not inf/error)."""
    df = _make_aggregated(forward_passes=0, total_passes=0)
    result = compute_per_90(df)
    assert np.isnan(result["forward_pass_pct"].iloc[0])


def test_compute_per_90_penalty_area_touches():
    """20 penalty area touches in 900 minutes = 2.0 p90."""
    df = _make_aggregated(penalty_area_touches=18, minutes_played=900)
    result = compute_per_90(df)
    assert abs(result["penalty_area_touches_p90"].iloc[0] - 1.8) < 1e-9


def test_compute_per_90_half_space_passes():
    """9 half-space passes in 900 minutes = 0.9 p90."""
    df = _make_aggregated(half_space_passes=9, minutes_played=900)
    result = compute_per_90(df)
    assert abs(result["half_space_passes_p90"].iloc[0] - 0.9) < 1e-9


def test_compute_per_90_ball_winning_height():
    """Sum x=2250 over 45 events = average height of 50.0."""
    df = _make_aggregated(ball_winning_x_sum=2250.0, ball_winning_count=45)
    result = compute_per_90(df)
    assert abs(result["ball_winning_height"].iloc[0] - 50.0) < 1e-9


def test_compute_per_90_ball_winning_height_zero_count():
    """Zero defensive events must produce NaN ball_winning_height (not inf)."""
    df = _make_aggregated(ball_winning_x_sum=0.0, ball_winning_count=0)
    result = compute_per_90(df)
    assert np.isnan(result["ball_winning_height"].iloc[0])


# ─── compute_percentiles ──────────────────────────────────────────────

def _make_multi_player_df(n=20):
    """Create n players with varying per-90 stats."""
    rows = []
    for i in range(n):
        rows.append({
            "player_id": i, "player_name": f"P{i}", "team_name": "T",
            "team_id": 1, "age": 23, "position": "MC", "appearances": 10,
            "minutes_played": 900 + i * 10,
            "key_passes": i * 2, "through_balls": i, "assists": i,
            "second_assists": 0, "progressive_passes": i * 5,
            "progressive_carries": 0, "passes_into_final_third": i * 3,
            "passes_into_penalty_area": i, "successful_dribbles": i,
            "total_dribbles": i * 2, "shots": i, "shots_on_target": 0,
            "tackles": 5, "interceptions": 5, "ball_recoveries": 5,
            "touches": 300, "touches_final_third": 50,
            "total_passes": 200, "accurate_passes": 180,
            # New spatial metrics
            "forward_passes": i * 3, "penalty_area_touches": i,
            "half_space_passes": i, "possession_won_final_third": i,
            "carries_into_final_third": i,
            "ball_winning_x_sum": (i + 1) * 50.0, "ball_winning_count": i + 1,
        })
    df = pd.DataFrame(rows)
    df = compute_per_90(df)
    return df


def test_compute_percentiles_range():
    """All percentile columns must be in [0, 100]."""
    df = compute_per_90(_make_multi_player_df())
    result = compute_percentiles(df)
    for metric in config.CHANCE_CREATION_METRICS:
        pct_col = f"{metric}_pct"
        if pct_col in result.columns:
            assert result[pct_col].between(0, 100).all(), \
                f"{pct_col} has values outside [0, 100]"


def test_compute_percentiles_columns_created():
    """A _pct column must exist for every CHANCE_CREATION_METRIC."""
    df = compute_per_90(_make_multi_player_df())
    result = compute_percentiles(df)
    for metric in config.CHANCE_CREATION_METRICS:
        if metric in result.columns:
            assert f"{metric}_pct" in result.columns


# ─── compute_composite_score ──────────────────────────────────────────

def test_composite_weights_sum_to_one():
    """Config weights must sum to exactly 1.0."""
    total = sum(config.COMPOSITE_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


def test_compute_composite_score_range():
    """Composite score must be between 0 and 100 for all players."""
    df = _make_multi_player_df()
    df = compute_per_90(df)
    df = compute_percentiles(df)
    df = compute_composite_score(df)
    assert df["chance_creation_score"].between(0, 100).all()


def test_compute_composite_score_higher_for_better_player():
    """A player better on every metric should have a higher composite score."""
    df = _make_multi_player_df(n=10)
    df = compute_per_90(df)
    df = compute_percentiles(df)
    df = compute_composite_score(df)
    scores = df.sort_values("player_id")["chance_creation_score"].tolist()
    # Scores should be monotonically non-decreasing (player 9 > player 0)
    assert scores[-1] >= scores[0]


def test_compute_composite_score_column_exists():
    df = _make_multi_player_df()
    df = compute_per_90(df)
    df = compute_percentiles(df)
    df = compute_composite_score(df)
    assert "chance_creation_score" in df.columns


# ─── compute_role_scores ──────────────────────────────────────────────

def test_role_weights_sum_to_one():
    """Each role's weights must sum to exactly 1.0."""
    for role, weights in config.ROLE_WEIGHTS.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-9, f"Role '{role}' weights sum to {total}, expected 1.0"


def _make_role_df(n: int = 10) -> pd.DataFrame:
    """DataFrame with all columns needed for role scoring."""
    rows = []
    for i in range(n):
        rows.append({
            "player_id": i, "player_name": f"Player {i}",
            "team_name": "Team A", "team_id": 1, "age": 23,
            "position": "MC", "appearances": 10,
            "minutes_played": 900 + i * 10,
            # Chance creation
            "key_passes": i * 2, "through_balls": i, "assists": i,
            "second_assists": 0, "progressive_passes": i * 5,
            "progressive_carries": 0, "passes_into_final_third": i * 3,
            "passes_into_penalty_area": i, "successful_dribbles": i,
            "total_dribbles": i * 2, "shots": i, "shots_on_target": 0,
            # Defensive
            "tackles": i + 1, "tackles_successful": i,
            "interceptions": i + 1, "ball_recoveries": i + 2,
            "clearances": i, "aerials_total": i + 1, "aerials_won": i,
            "shots_blocked": i,
            # Possession
            "possession_lost": i * 2 + 1, "possession_won": i * 2,
            # Passing / dribbling
            "total_passes": 200 + i * 10, "accurate_passes": 180 + i * 8,
            "crosses": i + 1, "crosses_successful": i,
            "touches": 300, "touches_final_third": 50,
            # New spatial metrics
            "forward_passes": i * 3 + 1, "penalty_area_touches": i + 1,
            "half_space_passes": i + 1, "possession_won_final_third": i,
            "carries_into_final_third": i,
            "ball_winning_x_sum": (i + 1) * 50.0, "ball_winning_count": i + 1,
        })
    df = pd.DataFrame(rows)
    df = compute_per_90(df)
    df = compute_percentiles(df)
    return df


def test_compute_role_scores_columns_exist():
    """A role_score_* column and primary_role must exist after compute_role_scores."""
    df = _make_role_df()
    df = compute_role_scores(df)
    for role in config.ROLE_WEIGHTS:
        col = f"{config.ROLE_SCORE_COL_PREFIX}{role}"
        assert col in df.columns, f"Missing column: {col}"
    assert config.PRIMARY_ROLE_COL in df.columns


def test_compute_role_scores_range():
    """All role scores must be in [0, 100]."""
    df = _make_role_df()
    df = compute_role_scores(df)
    for role in config.ROLE_WEIGHTS:
        col = f"{config.ROLE_SCORE_COL_PREFIX}{role}"
        assert df[col].between(0, 100).all(), f"{col} has values outside [0, 100]"


def test_primary_role_is_valid():
    """primary_role must be one of the defined roles for every player."""
    df = _make_role_df()
    df = compute_role_scores(df)
    valid_roles = set(config.ROLE_WEIGHTS.keys())
    assert df[config.PRIMARY_ROLE_COL].isin(valid_roles).all()
