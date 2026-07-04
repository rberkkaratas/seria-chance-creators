"""Tests for competition phase metadata, manifests, and fixture audit."""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.features.team_features import filter_to_table_scope
from src.processing.build_tables import process_match_csv
from src.processing.fixture_audit import build_fixture_audit
from src.scraper.fixture_scraper import merge_into_manifest
from src.scraper.whoscored_extractor import _normalize_manifest as extractor_normalize_manifest


def test_manifest_merge_backfills_old_schema_and_preserves_scraped():
    existing = pd.DataFrame([
        {"match_id": "1", "scraped": True},
    ])
    records = {
        "2": {
            "source_stage_id": "25287",
            "source_url": config.LEAGUES["Belgium_Pro_League"]["extra_fixture_urls"][0],
        }
    }

    result = merge_into_manifest(
        existing,
        ["1", "2"],
        "Belgium_Pro_League",
        records,
    )

    old = result[result["match_id"] == "1"].iloc[0]
    new = result[result["match_id"] == "2"].iloc[0]
    assert list(result.columns) == config.MANIFEST_COLUMNS
    assert bool(old["scraped"]) is True
    assert old["competition_key"] == "Belgium_Pro_League"
    assert new["competition_phase"] == config.PHASE_CHAMPIONSHIP_PLAYOFF
    assert new["competition_type"] == config.COMPETITION_TYPE_DOMESTIC


def test_manifest_merge_scrubs_nan_after_csv_round_trip(tmp_path):
    # A CSV round-trip turns empty cells into float NaN. The old backfill
    # stringified those to the literal "nan" (NaN is truthy, so `nan or ""`
    # kept the NaN) and crashed assigning strings into all-NaN float64
    # columns. Regression: normalize must yield clean empty strings.
    path = tmp_path / "manifest.csv"
    pd.DataFrame([{
        "match_id": "1", "scraped": True,
        "competition_key": "Premier_League",
        "competition_type": config.COMPETITION_TYPE_DOMESTIC,
        "source_stage_id": "", "competition_phase": config.PHASE_REGULAR_SEASON,
        "source_url": "", "validation_status": config.VALIDATION_PENDING,
        "validated_home_team": "", "validated_away_team": "",
    }]).to_csv(path, index=False)
    round_tripped = pd.read_csv(path)  # empty cells become float NaN

    result = merge_into_manifest(round_tripped, ["1", "2"], "Premier_League")

    string_cols = [c for c in config.MANIFEST_COLUMNS if c != "scraped"]
    assert not result[string_cols].isin(["nan"]).any().any()
    old = result[result["match_id"] == "1"].iloc[0]
    assert old["source_stage_id"] == ""
    assert old["source_url"] == ""
    assert bool(old["scraped"]) is True


def test_extractor_normalize_manifest_preserves_numeric_stage_ids():
    # Stage ids read without dtype=str become floats; "24580.0" must not
    # leak into stage_phases lookups or be written back to the manifest.
    df = pd.DataFrame({
        "match_id": ["1", "2"],
        "scraped": [True, False],
        "source_stage_id": [24580.0, float("nan")],
    })

    result = extractor_normalize_manifest(df, "Championship")

    assert result.loc[result["match_id"] == "1", "source_stage_id"].iloc[0] == "24580"
    string_cols = [c for c in config.MANIFEST_COLUMNS if c != "scraped"]
    assert not result[string_cols].isin(["nan"]).any().any()


def test_build_tables_reads_match_metadata(tmp_path):
    event_dir = tmp_path / "events"
    metadata_dir = event_dir / "metadata"
    metadata_dir.mkdir(parents=True)
    events_path = event_dir / "01012026_999.csv"
    pd.DataFrame([
        {
            "eventId": 1,
            "teamId": 10,
            "teamName": "Alpha",
            "playerId": 100,
            "playerName": "A",
            "type": "Pass",
            "outcomeType": "Successful",
            "qualifiers": "[]",
        },
        {
            "eventId": 2,
            "teamId": 20,
            "teamName": "Beta",
            "playerId": 200,
            "playerName": "B",
            "type": "Goal",
            "outcomeType": "Successful",
            "qualifiers": "[]",
        },
    ]).to_csv(events_path, index=False)
    (metadata_dir / "01012026_999_metadata.json").write_text(json.dumps({
        "match_id": "999",
        "competition_key": "Belgium_Pro_League",
        "competition_type": config.COMPETITION_TYPE_DOMESTIC,
        "competition_phase": config.PHASE_RELEGATION_PLAYOFF,
        "phase_table_scope": config.TABLE_SCOPE_PLAYOFF,
        "source_stage_id": "25289",
        "validation_status": config.VALIDATION_OK,
        "home_team_id": 10,
        "home_team_name": "Alpha",
        "away_team_id": 20,
        "away_team_name": "Beta",
        "home_score": 3,
        "away_score": 2,
    }))

    match_info, player_stats, team_stats = process_match_csv(events_path)

    assert match_info["competition_phase"] == config.PHASE_RELEGATION_PLAYOFF
    assert match_info["phase_table_scope"] == config.TABLE_SCOPE_PLAYOFF
    assert match_info["home_score"] == 3
    assert set(player_stats["competition_phase"]) == {config.PHASE_RELEGATION_PLAYOFF}
    assert {row["phase_table_scope"] for row in team_stats} == {config.TABLE_SCOPE_PLAYOFF}


def test_filter_to_table_scope_excludes_playoffs_and_wrong_competition():
    matches = pd.DataFrame([
        {
            "league": "L1",
            "match_id": "1",
            "phase_table_scope": config.TABLE_SCOPE_REGULAR,
            "validation_status": config.VALIDATION_PENDING,
        },
        {
            "league": "L1",
            "match_id": "2",
            "phase_table_scope": config.TABLE_SCOPE_PLAYOFF,
            "validation_status": config.VALIDATION_PENDING,
        },
        {
            "league": "L1",
            "match_id": "3",
            "phase_table_scope": config.TABLE_SCOPE_REGULAR,
            "validation_status": config.VALIDATION_WRONG_COMPETITION,
        },
    ])
    teams = pd.DataFrame([
        {"league": "L1", "match_id": "1", "team_id": 1},
        {"league": "L1", "match_id": "2", "team_id": 2},
        {"league": "L1", "match_id": "3", "team_id": 3},
    ])
    players = pd.DataFrame([
        {"league": "L1", "match_id": "1", "player_id": 10},
        {"league": "L1", "match_id": "2", "player_id": 20},
        {"league": "L1", "match_id": "3", "player_id": 30},
    ])

    scoped_matches, scoped_teams, scoped_players = filter_to_table_scope(
        matches, teams, players, config.TABLE_SCOPE_REGULAR
    )

    assert scoped_matches["match_id"].tolist() == ["1"]
    assert scoped_teams["team_id"].tolist() == [1]
    assert scoped_players["player_id"].tolist() == [10]


def test_fixture_audit_reports_pending_and_wrong_competition(monkeypatch):
    manifest = pd.DataFrame([
        {
            "match_id": "1",
            "scraped": True,
            "competition_phase": config.PHASE_REGULAR_SEASON,
        },
        {
            "match_id": "2",
            "scraped": False,
            "competition_phase": config.PHASE_REGULAR_SEASON,
        },
    ])
    matches = pd.DataFrame([
        {
            "league": "Premier_League",
            "match_id": "1",
            "competition_phase": config.PHASE_REGULAR_SEASON,
            "phase_table_scope": config.TABLE_SCOPE_REGULAR,
            "home_team_id": 1,
            "home_team_name": "Alpha",
            "away_team_id": 2,
            "away_team_name": "Beta",
            "home_score": 1,
            "away_score": 0,
            "validation_status": config.VALIDATION_PENDING,
        },
        {
            "league": "Premier_League",
            "match_id": "3",
            "competition_phase": config.PHASE_REGULAR_SEASON,
            "phase_table_scope": config.TABLE_SCOPE_REGULAR,
            "home_team_id": 99,
            "home_team_name": "Stray",
            "away_team_id": 100,
            "away_team_name": "Other",
            "home_score": 0,
            "away_score": 0,
            "validation_status": config.VALIDATION_PENDING,
        },
    ])

    monkeypatch.setattr("src.processing.fixture_audit._load_manifest", lambda competition, season: manifest)
    monkeypatch.setattr("src.processing.fixture_audit._load_matches", lambda competition, season: matches)
    monkeypatch.setattr(
        "src.processing.fixture_audit._load_scored_team_keys",
        lambda season: {"Premier_League||1", "Premier_League||2"},
    )

    result = build_fixture_audit(season="2099-2100", competitions=["Premier_League"])
    regular = result[result["competition_phase"] == config.PHASE_REGULAR_SEASON].iloc[0]

    assert regular["pending_count"] == 1
    assert regular["pending_ids"] == "2"
    assert regular["wrong_competition_count"] == 1
    assert regular["wrong_competition_ids"] == "3"
    assert regular["completeness_status"] == "invalid_matches"
