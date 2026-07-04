"""Tests for src/features/team_features.py."""

import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.features import team_features
from src.features.team_features import (
    _load_enriched_players,
    compute_results_table,
    compute_squad_profile,
    compute_style_metrics,
    compute_team_ratings,
    filter_processed_to_scored_team_pool,
    run_team_features,
)


def _matches_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "league": "L1",
            "match_id": 1,
            "home_team_id": 1,
            "home_team_name": "Alpha",
            "away_team_id": 2,
            "away_team_name": "Beta",
            "home_score": 2,
            "away_score": 1,
        },
        {
            "league": "L1",
            "match_id": 2,
            "home_team_id": 2,
            "home_team_name": "Beta",
            "away_team_id": 1,
            "away_team_name": "Alpha",
            "home_score": 0,
            "away_score": 0,
        },
    ])


def _teams_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "league": "L1",
            "match_id": 1,
            "team_id": 1,
            "team_name": "Alpha",
            "total_passes": 60,
            "accurate_passes": 54,
            "total_shots": 4,
            "goals": 2,
            "key_passes": 2,
            "tackles": 5,
            "interceptions": 1,
        },
        {
            "league": "L1",
            "match_id": 1,
            "team_id": 2,
            "team_name": "Beta",
            "total_passes": 40,
            "accurate_passes": 30,
            "total_shots": 2,
            "goals": 1,
            "key_passes": 1,
            "tackles": 4,
            "interceptions": 2,
        },
        # Same match_id in another league guards against cross-league opponent joins.
        {
            "league": "L2",
            "match_id": 1,
            "team_id": 10,
            "team_name": "Gamma",
            "total_passes": 1000,
            "accurate_passes": 900,
            "total_shots": 20,
            "goals": 5,
            "key_passes": 10,
            "tackles": 1,
            "interceptions": 1,
        },
        {
            "league": "L2",
            "match_id": 1,
            "team_id": 11,
            "team_name": "Delta",
            "total_passes": 500,
            "accurate_passes": 450,
            "total_shots": 10,
            "goals": 2,
            "key_passes": 5,
            "tackles": 1,
            "interceptions": 1,
        },
    ])


def _players_frame() -> pd.DataFrame:
    base = {
        "total_passes": 10,
        "forward_passes": 4,
        "long_balls": 1,
        "aerials_total": 4,
        "aerials_won": 2,
        "ball_winning_x_sum": 60,
        "ball_winning_count": 2,
        "progressive_passes": 3,
        "passes_into_final_third": 2,
        "crosses": 1,
        "successful_dribbles": 1,
        "ball_recoveries": 5,
        "possession_won_final_third": 1,
        "touches_final_third": 8,
        "penalty_area_touches": 2,
        "minutes_played": 90,
        "position": "DC",
    }
    return pd.DataFrame([
        {"league": "L1", "match_id": 1, "team_id": 1, "player_id": 101, **base},
        {"league": "L1", "match_id": 1, "team_id": 2, "player_id": 201, **base},
        {"league": "L2", "match_id": 1, "team_id": 10, "player_id": 301, **base},
        {"league": "L2", "match_id": 1, "team_id": 11, "player_id": 401, **base},
    ])


def test_results_table_points_and_rank_order():
    result = compute_results_table(_matches_frame())

    alpha = result[result["team_name"] == "Alpha"].iloc[0]
    beta = result[result["team_name"] == "Beta"].iloc[0]

    assert alpha["matches_played"] == 2
    assert alpha["wins"] == 1
    assert alpha["draws"] == 1
    assert alpha["points"] == 4
    assert alpha["goals_for"] == 2
    assert alpha["goals_against"] == 1
    assert alpha["league_rank_points"] == 1
    assert beta["league_rank_points"] == 2


def test_style_metrics_use_same_league_opponent_rows():
    style = compute_style_metrics(_teams_frame(), _players_frame(), _matches_frame())

    alpha = style[(style["league"] == "L1") & (style["team_id"] == 1)].iloc[0]

    assert alpha["possession_share"] == pytest.approx(0.60)
    assert alpha["pass_accuracy"] == pytest.approx(0.90)
    assert alpha["shots_per_match"] == pytest.approx(4.0)
    assert alpha["shots_conceded_per_match"] == pytest.approx(2.0)
    assert alpha["ppda_proxy"] == pytest.approx(40 / 6)


def test_wrong_league_fixture_rows_without_scored_teams_are_dropped():
    matches = pd.DataFrame([
        {
            "league": "L1",
            "match_id": 1,
            "home_team_id": 1,
            "home_team_name": "Alpha",
            "away_team_id": 2,
            "away_team_name": "Beta",
        },
        {
            "league": "L1",
            "match_id": 2,
            "home_team_id": 99,
            "home_team_name": "Stray A",
            "away_team_id": 100,
            "away_team_name": "Stray B",
        },
    ])
    teams = pd.DataFrame([
        {"league": "L1", "match_id": 1, "team_id": 1},
        {"league": "L1", "match_id": 1, "team_id": 2},
        {"league": "L1", "match_id": 2, "team_id": 99},
        {"league": "L1", "match_id": 2, "team_id": 100},
    ])
    players = pd.DataFrame([
        {"league": "L1", "match_id": 1, "team_id": 1, "player_id": 10},
        {"league": "L1", "match_id": 1, "team_id": 2, "player_id": 20},
        {"league": "L1", "match_id": 2, "team_id": 99, "player_id": 30},
        {"league": "L1", "match_id": 2, "team_id": 100, "player_id": 40},
    ])
    enriched = pd.DataFrame([
        {"league": "L1", "team_id": 1, "player_id": 10},
        {"league": "L1", "team_id": 2, "player_id": 20},
    ])

    m_out, t_out, p_out = filter_processed_to_scored_team_pool(
        matches, teams, players, enriched
    )

    assert m_out["match_id"].tolist() == [1]
    assert set(t_out["team_id"]) == {1, 2}
    assert set(p_out["player_id"]) == {10, 20}


def test_squad_profile_dedupes_multigroup_players_for_value_and_size():
    enriched = pd.DataFrame([
        {
            "league": "L1",
            "team_id": 1,
            "player_id": 10,
            "minutes_played": 60,
            "age": 20,
            "market_value_eur": 10_000_000,
        },
        {
            "league": "L1",
            "team_id": 1,
            "player_id": 10,
            "minutes_played": 40,
            "age": 20,
            "market_value_eur": 10_000_000,
        },
        {
            "league": "L1",
            "team_id": 1,
            "player_id": 11,
            "minutes_played": 50,
            "age": 30,
            "market_value_eur": 5_000_000,
        },
    ])

    result = compute_squad_profile(enriched).iloc[0]

    assert result["squad_size"] == 2
    assert result["market_value_total_eur"] == 15_000_000
    assert result["age_weighted"] == pytest.approx(((20 * 100) + (30 * 50)) / 150)


def test_team_ratings_clip_scores_weight_minutes_and_count_unique_players(monkeypatch):
    monkeypatch.setattr(config, "TEAM_MIN_GROUP_MINUTES", 100)
    monkeypatch.setattr(config, "TEAM_MIN_COVERAGE", 0.60)
    monkeypatch.setattr(config, "TEAM_MIN_QUALIFIED_PLAYERS", 1)

    enriched = pd.DataFrame([
        {
            "league": "L1",
            "team_id": 1,
            "player_id": 10,
            config.POSITION_GROUP_COL: "DEF",
            config.OVERALL_SCORE_COL: 100,
            "minutes_played": 90,
        },
        {
            "league": "L1",
            "team_id": 1,
            "player_id": 10,
            config.POSITION_GROUP_COL: "MID",
            config.OVERALL_SCORE_COL: 50,
            "minutes_played": 90,
        },
        {
            "league": "L1",
            "team_id": 2,
            "player_id": 20,
            config.POSITION_GROUP_COL: "DEF",
            config.OVERALL_SCORE_COL: 0,
            "minutes_played": 180,
        },
    ])
    players = pd.DataFrame([
        {"league": "L1", "team_id": 1, "player_id": 10, "position": "DC", "minutes_played": 180},
        {"league": "L1", "team_id": 2, "player_id": 20, "position": "DC", "minutes_played": 180},
    ])

    result = compute_team_ratings(enriched, players)
    alpha = result[result["team_id"] == 1].iloc[0]
    beta = result[result["team_id"] == 2].iloc[0]

    z_hi = NormalDist().inv_cdf(config.PCT_CLIP[1] / 100)
    z_lo = NormalDist().inv_cdf(config.PCT_CLIP[0] / 100)
    assert alpha[config.TEAM_STRENGTH_Z_COL] == pytest.approx(z_hi / 2)
    assert beta[config.TEAM_STRENGTH_Z_COL] == pytest.approx(z_lo)
    assert alpha[config.TEAM_RATING_COL] > beta[config.TEAM_RATING_COL]
    assert alpha["qualified_players"] == 1
    assert pd.isna(alpha["rating_DEF"])
    assert beta["rating_DEF"] == pytest.approx(0.0)
    assert bool(alpha["low_coverage"]) is False


def test_low_coverage_flag_does_not_drop_team(monkeypatch):
    monkeypatch.setattr(config, "TEAM_MIN_COVERAGE", 0.75)
    monkeypatch.setattr(config, "TEAM_MIN_QUALIFIED_PLAYERS", 1)

    enriched = pd.DataFrame([
        {
            "league": "L1",
            "team_id": 1,
            "player_id": 10,
            config.POSITION_GROUP_COL: "DEF",
            config.OVERALL_SCORE_COL: 80,
            "minutes_played": 45,
        },
    ])
    players = pd.DataFrame([
        {"league": "L1", "team_id": 1, "player_id": 10, "position": "DC", "minutes_played": 90},
    ])

    result = compute_team_ratings(enriched, players)

    assert len(result) == 1
    assert result["rating_coverage"].iloc[0] == pytest.approx(0.5)
    assert bool(result["low_coverage"].iloc[0]) is True


def test_run_team_features_writes_output_and_perf_delta_sign(monkeypatch, tmp_path):
    matches = pd.DataFrame([
        {
            "league": "L1",
            "match_id": 1,
            "home_team_id": 1,
            "home_team_name": "Alpha",
            "away_team_id": 2,
            "away_team_name": "Beta",
            "home_score": 1,
            "away_score": 0,
        },
    ])
    teams = pd.DataFrame([
        {
            "league": "L1",
            "match_id": 1,
            "team_id": 1,
            "team_name": "Alpha",
            "total_passes": 60,
            "accurate_passes": 50,
            "total_shots": 4,
            "goals": 1,
            "key_passes": 2,
            "tackles": 5,
            "interceptions": 1,
        },
        {
            "league": "L1",
            "match_id": 1,
            "team_id": 2,
            "team_name": "Beta",
            "total_passes": 40,
            "accurate_passes": 30,
            "total_shots": 2,
            "goals": 0,
            "key_passes": 1,
            "tackles": 4,
            "interceptions": 2,
        },
    ])
    players = pd.DataFrame([
        {
            "league": "L1",
            "match_id": 1,
            "team_id": 1,
            "player_id": 101,
            "team_name": "Alpha",
            "position": "DC",
            "minutes_played": 90,
        },
        {
            "league": "L1",
            "match_id": 1,
            "team_id": 2,
            "player_id": 201,
            "team_name": "Beta",
            "position": "DC",
            "minutes_played": 90,
        },
    ])
    enriched = pd.DataFrame([
        {
            "league": "L1",
            "team_id": 1,
            "team_name": "Alpha",
            "player_id": 101,
            config.POSITION_GROUP_COL: "DEF",
            config.OVERALL_SCORE_COL: 20,
            "minutes_played": 90,
        },
        {
            "league": "L1",
            "team_id": 2,
            "team_name": "Beta",
            "player_id": 201,
            config.POSITION_GROUP_COL: "DEF",
            config.OVERALL_SCORE_COL: 80,
            "minutes_played": 90,
        },
    ])

    monkeypatch.setattr(team_features, "load_processed", lambda leagues, season: (matches, teams, players))
    monkeypatch.setattr(team_features, "_load_enriched_players", lambda season: (enriched, False))
    monkeypatch.setattr(team_features, "attach_club_elo", lambda df: df)
    monkeypatch.setattr(config, "DATA_FINAL", tmp_path)
    monkeypatch.setattr(config, "TEAM_MIN_COVERAGE", 0.60)
    monkeypatch.setattr(config, "TEAM_MIN_QUALIFIED_PLAYERS", 1)

    result = run_team_features(season="2099-2100", leagues=["L1"])

    alpha = result[result["team_name"] == "Alpha"].iloc[0]
    beta = result[result["team_name"] == "Beta"].iloc[0]
    assert alpha["league_rank_points"] == 1
    assert alpha["league_rank_rating"] == 2
    assert alpha["perf_delta_rank"] == -1
    assert beta["perf_delta_rank"] == 1
    assert (tmp_path / "teams_2099-2100.csv").exists()


def test_load_enriched_players_missing_merged_file_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_FINAL", tmp_path)

    with pytest.raises(FileNotFoundError, match="Merged player file not found"):
        _load_enriched_players("2099-2100")
