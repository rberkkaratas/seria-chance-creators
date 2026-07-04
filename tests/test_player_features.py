"""Tests for src/features/player_features.py."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.features.player_features import (
    aggregate_per_player,
    compute_overall_score,
    compute_per_90,
    compute_percentiles,
    compute_role_scores,
    compute_sample_reliability,
    filter_position_group,
    group_metrics,
    resolve_substitute_positions,
    sample_adjusted_metric,
)


def _make_players(rows):
    defaults = {
        "league": "Test_League",
        "player_id": 1,
        "player_name": "Test Player",
        "team_name": "Team A",
        "team_id": 100,
        "age": 24,
        "match_id": "m1",
        "position": "MC",
        "minutes_played": 90,
        "isFirstEleven": True,
        "key_passes": 0,
        "through_balls": 0,
        "passes_into_final_third": 0,
        "passes_into_penalty_area": 0,
        "successful_dribbles": 0,
        "progressive_passes": 0,
        "total_passes": 0,
        "accurate_passes": 0,
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


def test_filter_position_group_qualifies_with_enough_group_minutes():
    rows = [
        {"player_id": 1, "position": "MC", "minutes_played": 90, "match_id": f"m{i}"}
        for i in range(10)
    ]
    result = filter_position_group(_make_players(rows), "MID")
    assert result["player_id"].nunique() == 1
    assert (result[config.POSITION_GROUP_COL] == "MID").all()


def test_filter_position_group_excludes_insufficient_group_minutes():
    rows = [
        {"player_id": 1, "position": "MC", "minutes_played": 90, "match_id": f"m{i}"}
        for i in range(1)
    ]
    assert filter_position_group(_make_players(rows), "MID").empty


def test_filter_position_group_counts_only_active_group_minutes():
    cb_rows = [
        {"player_id": 1, "position": "DC", "minutes_played": 90, "match_id": f"cb{i}"}
        for i in range(9)
    ]
    mc_rows = [
        {"player_id": 1, "position": "MC", "minutes_played": 90, "match_id": f"mc{i}"}
        for i in range(1)
    ]
    df = _make_players(cb_rows + mc_rows)
    assert filter_position_group(df, "MID").empty
    assert filter_position_group(df, "DEF")["position"].eq("DC").all()


def test_aggregate_per_player_counts_starts_usage():
    df = _make_players([
        {"player_id": 1, "match_id": "m1", "minutes_played": 90, "isFirstEleven": "True"},
        {"player_id": 1, "match_id": "m2", "minutes_played": 30, "isFirstEleven": "False"},
    ])
    result = aggregate_per_player(df)
    assert result["appearances"].iloc[0] == 2
    assert result["starts"].iloc[0] == 1


def test_resolve_substitute_positions_uses_primary_outfield_position():
    df = _make_players([
        {"player_id": 1, "match_id": "m1", "position": "DC", "minutes_played": 90, "isFirstEleven": True},
        {"player_id": 1, "match_id": "m2", "position": "MC", "minutes_played": 180, "isFirstEleven": True},
        {"player_id": 1, "match_id": "m3", "position": "Sub", "minutes_played": 30, "isFirstEleven": False},
        {"player_id": 2, "match_id": "m4", "position": "Sub", "minutes_played": 45, "isFirstEleven": False},
        {"player_id": 3, "match_id": "m5", "position": "GK", "minutes_played": 90, "isFirstEleven": True},
        {"player_id": 3, "match_id": "m6", "position": "Sub", "minutes_played": 15, "isFirstEleven": False},
    ])
    result = resolve_substitute_positions(df)

    p1_sub = result[(result["player_id"] == 1) & (result["match_id"] == "m3")].iloc[0]
    p2_sub = result[(result["player_id"] == 2) & (result["match_id"] == "m4")].iloc[0]
    p3_sub = result[(result["player_id"] == 3) & (result["match_id"] == "m6")].iloc[0]

    assert p1_sub["position"] == "MC"
    assert p2_sub["position"] == "Sub"
    assert p3_sub["position"] == "Sub"


def test_substitute_rows_make_appearances_exceed_starts_after_resolution():
    df = _make_players([
        {"player_id": 1, "match_id": "m1", "position": "MC", "minutes_played": 90, "isFirstEleven": True},
        {"player_id": 1, "match_id": "m2", "position": "MC", "minutes_played": 90, "isFirstEleven": True},
        {"player_id": 1, "match_id": "m3", "position": "Sub", "minutes_played": 30, "isFirstEleven": False},
    ])
    resolved = resolve_substitute_positions(df)
    filtered = filter_position_group(resolved, "MID")
    result = aggregate_per_player(filtered)

    assert result["appearances"].iloc[0] == 3
    assert result["starts"].iloc[0] == 2


def test_compute_sample_reliability_marks_limited_sample():
    df = pd.DataFrame({
        "minutes_played": [180],
        "appearances": [2],
        "starts": [2],
    })
    result = compute_sample_reliability(df)
    assert result[config.SCORE_CONFIDENCE_COL].iloc[0] < 25
    assert result[config.SAMPLE_TIER_COL].iloc[0] == "Limited sample"
    assert result["start_rate"].iloc[0] == 100.0


def test_sample_adjusted_metric_shrinks_low_confidence_to_median():
    df = pd.DataFrame({
        "metric": [100.0, 50.0, 0.0],
        config.SAMPLE_RELIABILITY_COL: [0.0, 1.0, 0.0],
    })
    result = sample_adjusted_metric(df, "metric")
    assert result.tolist() == [50.0, 50.0, 50.0]


def test_filter_position_group_mixed_positions_keeps_only_group_rows():
    cb_rows = [
        {"player_id": 1, "position": "DC", "minutes_played": 90, "match_id": f"cb{i}"}
        for i in range(5)
    ]
    mc_rows = [
        {"player_id": 1, "position": "MC", "minutes_played": 90, "match_id": f"mc{i}"}
        for i in range(10)
    ]
    result = filter_position_group(_make_players(cb_rows + mc_rows), "MID")
    assert result["player_id"].nunique() == 1
    assert result["position"].eq("MC").all()


@pytest.mark.parametrize("position", ["GK", "Sub"])
def test_filter_position_group_excludes_gk_and_sub_rows(position):
    rows = [
        {"player_id": 1, "position": position, "minutes_played": 90, "match_id": f"m{i}"}
        for i in range(20)
    ]
    df = _make_players(rows)
    for group in config.POSITION_GROUPS:
        assert filter_position_group(df, group).empty


def _make_aggregated(**overrides):
    row = {
        "player_id": 1,
        "player_name": "A",
        "team_name": "T",
        "team_id": 1,
        "age": 23,
        "position": "MC",
        "appearances": 10,
        "minutes_played": 900,
        "key_passes": 18,
        "through_balls": 9,
        "long_balls": 30,
        "assists": 5,
        "second_assists": 2,
        "shot_creating_actions": 20,
        "progressive_passes": 45,
        "passes_into_final_third": 27,
        "passes_into_penalty_area": 9,
        "successful_dribbles": 18,
        "total_dribbles": 30,
        "shots": 10,
        "shots_on_target": 5,
        "goals": 4,
        "tackles": 20,
        "tackles_successful": 12,
        "interceptions": 15,
        "ball_recoveries": 30,
        "clearances": 25,
        "aerials_won": 14,
        "aerials_total": 20,
        "shots_blocked": 6,
        "crosses": 16,
        "crosses_successful": 4,
        "possession_lost": 40,
        "touches": 500,
        "touches_final_third": 80,
        "total_passes": 400,
        "accurate_passes": 360,
        "forward_passes": 200,
        "penalty_area_touches": 20,
        "half_space_passes": 15,
        "possession_won_final_third": 10,
        "carries_into_final_third": 5,
        "ball_winning_x_sum": 2250.0,
        "ball_winning_count": 45,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_compute_per_90_basic_rate():
    result = compute_per_90(_make_aggregated(key_passes=18, minutes_played=900))
    assert abs(result["key_passes_p90"].iloc[0] - 1.8) < 1e-9


def test_compute_per_90_long_balls_goals_and_sca():
    result = compute_per_90(_make_aggregated(long_balls=30, goals=4, shot_creating_actions=20))
    assert abs(result["long_balls_p90"].iloc[0] - 3.0) < 1e-9
    assert abs(result["goals_p90"].iloc[0] - 0.4) < 1e-9
    assert abs(result["shot_creating_actions_p90"].iloc[0] - 2.0) < 1e-9


def test_compute_per_90_shot_creating_actions_fallback():
    df = _make_aggregated(key_passes=18, successful_dribbles=9).drop(columns=["shot_creating_actions"])
    result = compute_per_90(df)
    expected = result["key_passes_p90"].iloc[0] + result["successful_dribbles_p90"].iloc[0]
    assert abs(result["shot_creating_actions_p90"].iloc[0] - expected) < 1e-9


def test_compute_per_90_zero_minutes_no_inf():
    result = compute_per_90(_make_aggregated(minutes_played=0, key_passes=5))
    val = result["key_passes_p90"].iloc[0]
    assert not np.isinf(val)
    assert np.isnan(val)


def test_compute_per_90_rates_and_derived_metrics():
    result = compute_per_90(_make_aggregated())
    assert abs(result["pass_accuracy"].iloc[0] - 90.0) < 1e-9
    assert abs(result["forward_pass_pct"].iloc[0] - 50.0) < 1e-9
    assert abs(result["ball_winning_height"].iloc[0] - 50.0) < 1e-9
    assert abs(result["def_actions_p90"].iloc[0] - 3.5) < 1e-9


def test_compute_per_90_all_config_metrics_are_producible():
    result = compute_per_90(_make_aggregated())
    required = set()
    for group in config.POSITION_GROUPS:
        required.update(group_metrics(group))
    missing = sorted(metric for metric in required if metric not in result.columns)
    assert missing == []


def _make_role_df(group: str, n: int = 12) -> pd.DataFrame:
    rows = []
    position = config.POSITION_GROUPS[group]["positions"][0]
    for i in range(n):
        row = _make_aggregated(
            player_id=i,
            player_name=f"Player {i}",
            position=position,
            minutes_played=900 + i * 10,
            key_passes=i + 1,
            through_balls=i,
            long_balls=i * 2 + 1,
            assists=i // 2,
            shot_creating_actions=i * 2 + 3,
            progressive_passes=i * 4 + 1,
            passes_into_final_third=i * 3 + 1,
            passes_into_penalty_area=i + 1,
            successful_dribbles=i + 1,
            total_dribbles=i + 2,
            shots=i + 1,
            goals=i // 3,
            tackles=i + 2,
            tackles_successful=i + 1,
            interceptions=i + 1,
            ball_recoveries=i + 2,
            clearances=i + 1,
            aerials_total=i + 3,
            aerials_won=i + 1,
            shots_blocked=i,
            crosses=i + 1,
            touches_final_third=i * 4 + 10,
            penalty_area_touches=i + 2,
            possession_won_final_third=i,
            carries_into_final_third=i + 1,
            ball_winning_x_sum=(i + 1) * 50.0,
            ball_winning_count=i + 1,
        ).iloc[0].to_dict()
        row[config.POSITION_GROUP_COL] = group
        rows.append(row)
    df = pd.DataFrame(rows)
    df = compute_per_90(df)
    df = compute_percentiles(df, group)
    return df


@pytest.mark.parametrize("group", list(config.POSITION_GROUPS.keys()))
def test_compute_percentiles_range(group):
    result = _make_role_df(group)
    for metric in group_metrics(group):
        pct_col = f"{metric}_pct"
        if pct_col in result.columns:
            assert result[pct_col].dropna().between(0, 100).all()


@pytest.mark.parametrize("group", list(config.POSITION_GROUPS.keys()))
def test_compute_role_scores_columns_range_and_primary_role(group):
    df = _make_role_df(group)
    df = compute_role_scores(df, group)
    valid_roles = set(config.POSITION_GROUPS[group]["roles"])
    for role in valid_roles:
        col = f"{config.ROLE_SCORE_COL_PREFIX}{role}"
        assert col in df.columns
        assert df[col].between(0, 100).all()
    assert df[config.PRIMARY_ROLE_COL].isin(valid_roles).all()


def test_compute_role_scores_shrink_low_confidence_scores_toward_neutral():
    role = "Creator"
    metrics = config.POSITION_GROUPS["MID"]["roles"][role]
    df = pd.DataFrame({
        "player_id": [1, 2],
        config.SAMPLE_RELIABILITY_COL: [1.0, 0.2],
    })
    for metric in metrics:
        df[f"{metric}_pct"] = 100.0

    result = compute_role_scores(df, "MID")
    col = f"{config.ROLE_SCORE_COL_PREFIX}{role}"

    assert result[col].iloc[0] == 100.0
    assert result[col].iloc[1] == 60.0


@pytest.mark.parametrize("group", list(config.POSITION_GROUPS.keys()))
def test_compute_overall_score_range(group):
    df = _make_role_df(group)
    df = compute_role_scores(df, group)
    df = compute_overall_score(df, group)
    assert config.OVERALL_SCORE_COL in df.columns
    assert df[config.OVERALL_SCORE_COL].between(0, 100).all()


def test_position_groups_split_central_wide_and_forward_positions():
    assert config.POSITION_GROUPS["DEF"]["positions"] == ["DC"]
    assert {"DL", "DR", "DML", "DMR"}.issubset(config.POSITION_GROUPS["FB"]["positions"])
    assert {"ML", "MR", "AML", "AMR", "FWL", "FWR"}.issubset(
        config.POSITION_GROUPS["WING"]["positions"]
    )
    assert config.POSITION_GROUPS["FW"]["positions"] == ["FW"]
    assert config.POSITION_TO_GROUP["DL"] == "FB"
    assert config.POSITION_TO_GROUP["FWL"] == "WING"


def test_compute_overall_score_uses_split_group_weights():
    prefix = config.ROLE_SCORE_COL_PREFIX
    defender = pd.DataFrame({
        "position": ["DC"],
        f"{prefix}Stopper": [100.0],
        f"{prefix}Aerial Dominator": [80.0],
        f"{prefix}Ball-Playing Defender": [60.0],
    })
    fullback = pd.DataFrame({
        "position": ["DL"],
        f"{prefix}Attacking Fullback": [100.0],
        f"{prefix}Defensive Fullback": [80.0],
        f"{prefix}Inverted Fullback": [60.0],
        f"{prefix}Crossing Fullback": [20.0],
    })

    defender_result = compute_overall_score(defender, "DEF")
    fullback_result = compute_overall_score(fullback, "FB")

    assert defender_result[config.OVERALL_SCORE_COL].tolist() == [80.0]
    assert fullback_result[config.OVERALL_SCORE_COL].tolist() == [69.0]


def test_role_names_are_globally_unique():
    roles = [
        role
        for group_cfg in config.POSITION_GROUPS.values()
        for role in group_cfg["roles"]
    ]
    assert len(roles) == len(set(roles))


def test_sample_adjusted_metric_shrinks_rate_by_contest_count():
    from src.features.player_features import sample_adjusted_metric

    df = pd.DataFrame({
        "aerials_won": [2, 60, 30],
        "aerials_total": [2, 60, 60],
        "aerial_win_rate": [100.0, 100.0, 50.0],
    })
    shrunk = sample_adjusted_metric(df, "aerial_win_rate")

    # Same raw 100% rate, but 2 contests must rank below 60 contests.
    assert shrunk.iloc[0] < shrunk.iloc[1]
    # High-volume rates stay close to their raw value.
    assert shrunk.iloc[1] > 85.0
    assert abs(shrunk.iloc[2] - 50.0) < 15.0


def test_sample_adjusted_metric_possession_adjusts_def_volume():
    from src.features.player_features import sample_adjusted_metric

    df = pd.DataFrame({
        "tackles_successful_p90": [2.0, 2.0],
        config.PADJ_OPPONENT_SHARE_COL: [0.35, 0.50],
        config.SAMPLE_RELIABILITY_COL: [1.0, 1.0],
    })

    adjusted = sample_adjusted_metric(df, "tackles_successful_p90", group="DEF")
    # Defender on a 65%-possession side gets scaled up to the 50% baseline.
    assert adjusted.iloc[0] == pytest.approx(2.0 * 0.5 / 0.35, rel=1e-6)
    assert adjusted.iloc[1] == pytest.approx(2.0)

    # No group context (or a group without PAdj) leaves values unadjusted.
    unadjusted = sample_adjusted_metric(df, "tackles_successful_p90")
    assert (unadjusted == 2.0).all()
    wing = sample_adjusted_metric(df, "tackles_successful_p90", group="WING")
    assert (wing == 2.0).all()


def test_compute_overall_score_is_rank_based_for_real_pools():
    prefix = config.ROLE_SCORE_COL_PREFIX
    n = 10
    df = pd.DataFrame({
        "position": ["DC"] * n,
        f"{prefix}Stopper": [40.0 + i for i in range(n)],
        f"{prefix}Aerial Dominator": [45.0 + i for i in range(n)],
        f"{prefix}Ball-Playing Defender": [50.0 + i for i in range(n)],
    })
    result = compute_overall_score(df, "DEF")
    scores = result[config.OVERALL_SCORE_COL]

    # Percentile-ranked output: best player hits 100, full scale is used.
    assert scores.max() == 100.0
    assert scores.min() == pytest.approx(100.0 / n, abs=0.1)
    # Monotone in the underlying role scores.
    assert scores.is_monotonic_increasing


def test_role_and_overall_weights_sum_to_one():
    for group_key, group_cfg in config.POSITION_GROUPS.items():
        for role, weights in group_cfg["roles"].items():
            assert abs(sum(weights.values()) - 1.0) < 1e-9, f"{group_key}/{role}"
        assert abs(sum(group_cfg["composite_weights"].values()) - 1.0) < 1e-9, group_key
        for position, weights in group_cfg.get("position_composite_weights", {}).items():
            assert abs(sum(weights.values()) - 1.0) < 1e-9, f"{group_key}/{position}"
