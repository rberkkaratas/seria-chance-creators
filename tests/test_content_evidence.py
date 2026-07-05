"""Tests for src/features/content_evidence.py (isolated content layer)."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.features import content_evidence
from src.features.content_evidence import (
    CONTENT_CLAIM,
    REQUIRED_COLUMNS,
    RISK_NOTE,
    ContentEvidenceValidationError,
    build_fullback_content_summary,
    load_fullback_observations,
    render_content_pack_markdown,
    run_content_evidence,
    select_top_fullback_evidence,
    validate_fullback_observations,
)

SAMPLE_CSV = (
    Path(__file__).parent.parent
    / "data" / "content_evidence" / "world_cup_2026"
    / "fullback_observations.sample.csv"
)


def _base_row(**overrides) -> dict:
    row = {
        "observation_id": "OBS",
        "match_id": "M1",
        "match_date": "2026-06-12",
        "competition": "World_Cup_2026",
        "stage": "group_stage",
        "team": "Blue",
        "opponent": "Red",
        "player_name": "Player A",
        "player_id_optional": "",
        "side": "right",
        "minute": "10",
        "phase": "progression",
        "game_state": "level",
        "x": "50.0",
        "y": "80.0",
        "end_x": "60.0",
        "end_y": "70.0",
        "possession_context": "in_possession",
        "fullback_lane": "half_space",
        "fullback_behavior": "inverted_support",
        "support_role": "midfield_support",
        "transition_role": "none",
        "action_type": "pass",
        "outcome": "positive",
        "evidence_strength": "3",
        "clip_ref": "clip_1",
        "freeze_frame_note": "note",
        "content_note": "note",
    }
    row.update(overrides)
    return row


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


# ─── Validation ──────────────────────────────────────────────────────

def test_missing_required_column_raises():
    df = _frame([_base_row()]).drop(columns=["fullback_behavior"])
    with pytest.raises(ContentEvidenceValidationError, match="missing required"):
        validate_fullback_observations(df)


def test_enum_violation_raises():
    df = _frame([_base_row(fullback_behavior="teleport")])
    with pytest.raises(ContentEvidenceValidationError, match="teleport"):
        validate_fullback_observations(df)


def test_empty_frame_raises():
    df = _frame([])
    with pytest.raises(ContentEvidenceValidationError, match="no rows"):
        validate_fullback_observations(df)


def test_valid_frame_passes():
    df = _frame([_base_row()])
    assert validate_fullback_observations(df) is df


# ─── Share computation ───────────────────────────────────────────────

def test_central_or_halfspace_share_computation():
    rows = [
        _base_row(observation_id="A", fullback_lane="half_space"),
        _base_row(observation_id="B", fullback_lane="central"),
        _base_row(observation_id="C", fullback_lane="touchline"),
        _base_row(observation_id="D", fullback_lane="touchline"),
    ]
    summary = build_fullback_content_summary(_frame(rows))
    assert len(summary) == 1
    # 2 of 4 rows central/half_space → 0.5
    assert summary.iloc[0]["central_or_halfspace_share"] == 0.5


# ─── Role classification ─────────────────────────────────────────────

def test_inverted_context_classification():
    rows = [
        _base_row(observation_id=f"I{i}", fullback_behavior="inverted_support",
                  fullback_lane="half_space")
        for i in range(4)
    ]
    summary = build_fullback_content_summary(_frame(rows))
    assert summary.iloc[0]["primary_content_role"] == "inverted_fullback_context"


def test_attacking_context_classification():
    rows = [
        _base_row(observation_id="A1", fullback_behavior="overlap",
                  fullback_lane="touchline", phase="final_third"),
        _base_row(observation_id="A2", fullback_behavior="underlap",
                  fullback_lane="touchline", phase="final_third"),
        _base_row(observation_id="A3", fullback_behavior="crossing_action",
                  fullback_lane="touchline", phase="final_third"),
        _base_row(observation_id="A4", fullback_behavior="width_holding",
                  fullback_lane="touchline", phase="progression"),
    ]
    summary = build_fullback_content_summary(_frame(rows))
    assert summary.iloc[0]["primary_content_role"] == "attacking_fullback_context"


def test_rest_defense_context_classification():
    rows = [
        _base_row(observation_id="R1", fullback_behavior="rest_defense_cover",
                  fullback_lane="central", transition_role="rest_defense",
                  phase="rest_defense"),
        _base_row(observation_id="R2", fullback_behavior="recovery_run",
                  fullback_lane="back_line", transition_role="first_pressure",
                  phase="defensive_transition"),
        _base_row(observation_id="R3", fullback_behavior="width_holding",
                  fullback_lane="back_line", transition_role="cover_shadow",
                  phase="settled_defense"),
        _base_row(observation_id="R4", fullback_behavior="width_holding",
                  fullback_lane="touchline", transition_role="recovery",
                  phase="settled_defense"),
    ]
    summary = build_fullback_content_summary(_frame(rows))
    assert summary.iloc[0]["primary_content_role"] == "rest_defense_fullback_context"


# ─── Evidence selection ──────────────────────────────────────────────

def test_select_top_evidence_respects_min_strength():
    rows = [
        _base_row(observation_id="S1", evidence_strength="1"),
        _base_row(observation_id="S2", evidence_strength="2"),
        _base_row(observation_id="S3", evidence_strength="3"),
    ]
    top = select_top_fullback_evidence(_frame(rows), min_strength=2)
    ids = list(top["observation_id"])
    assert ids == ["S3", "S2"]  # strength-1 dropped, sorted desc


def test_select_top_evidence_filters():
    rows = [
        _base_row(observation_id="P1", player_name="A"),
        _base_row(observation_id="P2", player_name="B"),
    ]
    top = select_top_fullback_evidence(_frame(rows), player_name="A")
    assert list(top["observation_id"]) == ["P1"]


# ─── Markdown export ─────────────────────────────────────────────────

def test_markdown_has_claim_scenes_and_risk_note():
    df = load_fullback_observations(SAMPLE_CSV)
    validate_fullback_observations(df)
    summary = build_fullback_content_summary(df)
    evidence = select_top_fullback_evidence(df, min_strength=2)
    md = render_content_pack_markdown(
        summary, evidence, "World_Cup_2026", "tüm gözlemler (filtre yok)"
    )
    assert CONTENT_CLAIM in md
    assert RISK_NOTE in md
    # Exactly three hero scene headers present.
    assert md.count("### Sahne ") == 3
    assert "## İçerik iddiası" in md
    assert "## Video için üç sayı" in md


# ─── End-to-end ──────────────────────────────────────────────────────

def test_run_content_evidence_writes_files(tmp_path):
    out = tmp_path / "packs" / "fullback_content_pack.md"
    result = run_content_evidence(
        input_path=SAMPLE_CSV, output_path=out, competition="World_Cup_2026"
    )
    assert result.exists()
    assert (out.parent / "fullback_content_summary.csv").exists()
    text = result.read_text(encoding="utf-8")
    assert CONTENT_CLAIM in text
    assert RISK_NOTE in text


def test_sample_csv_matches_schema():
    df = load_fullback_observations(SAMPLE_CSV)
    assert list(df.columns) == REQUIRED_COLUMNS
    validate_fullback_observations(df)  # sample must be enum-clean
