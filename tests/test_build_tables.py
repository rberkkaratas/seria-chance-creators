"""
Tests for src/processing/build_tables.py

Covers:
- has_qualifier / parse_qualifiers
- enrich_events qualifier flags (including regression tests for
  the displayName casing bugs that caused all-zero columns)
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.processing.build_tables import (
    enrich_events,
    has_qualifier,
    parse_qualifiers,
)


# ─── parse_qualifiers ─────────────────────────────────────────────────

def test_parse_qualifiers_valid_list():
    qual_str = "[{'type': {'displayName': 'KeyPass', 'value': 1}, 'value': 'true'}]"
    result = parse_qualifiers(qual_str)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["type"]["displayName"] == "KeyPass"


def test_parse_qualifiers_empty_string():
    assert parse_qualifiers("[]") == []


def test_parse_qualifiers_nan():
    assert parse_qualifiers(float("nan")) == []


def test_parse_qualifiers_invalid_returns_empty():
    assert parse_qualifiers("not valid python") == []


# ─── has_qualifier ────────────────────────────────────────────────────

def _make_quals(*names):
    return [{"type": {"displayName": n}, "value": "true"} for n in names]


def test_has_qualifier_found():
    quals = _make_quals("KeyPass", "Zone")
    assert has_qualifier(quals, "KeyPass") is True


def test_has_qualifier_not_found():
    quals = _make_quals("Zone")
    assert has_qualifier(quals, "KeyPass") is False


def test_has_qualifier_empty_list():
    assert has_qualifier([], "KeyPass") is False


def test_has_qualifier_case_sensitive_throughball():
    """Regression: WhoScored uses 'Throughball', NOT 'ThroughBall'."""
    quals = _make_quals("Throughball")
    assert has_qualifier(quals, "Throughball") is True
    assert has_qualifier(quals, "ThroughBall") is False   # old wrong casing


def test_has_qualifier_case_sensitive_longball():
    """Regression: WhoScored uses 'Longball', NOT 'LongBall'."""
    quals = _make_quals("Longball")
    assert has_qualifier(quals, "Longball") is True
    assert has_qualifier(quals, "LongBall") is False


def test_has_qualifier_case_sensitive_assist():
    """Regression: WhoScored uses 'IntentionalAssist', NOT 'IntentionalGoalAssist'."""
    quals = _make_quals("IntentionalAssist")
    assert has_qualifier(quals, "IntentionalAssist") is True
    assert has_qualifier(quals, "IntentionalGoalAssist") is False


# ─── enrich_events ────────────────────────────────────────────────────

def _base_event(**overrides):
    """Minimal event row dict."""
    row = {
        "type": "Pass",
        "outcomeType": "Successful",
        "qualifiers": "[]",
        "playerId": 1,
        "teamId": 10,
    }
    row.update(overrides)
    return row


def _df(*rows):
    return pd.DataFrame(list(rows))


def test_enrich_events_key_pass_flag():
    quals = str(_make_quals("KeyPass"))
    df = _df(_base_event(qualifiers=quals))
    out = enrich_events(df)
    assert out["is_key_pass"].iloc[0]


def test_enrich_events_non_key_pass():
    df = _df(_base_event())
    out = enrich_events(df)
    assert not out["is_key_pass"].iloc[0]


def test_enrich_events_throughball_correct_name():
    """Throughball (correct casing) must set is_through_ball=True."""
    quals = str(_make_quals("Throughball"))
    df = _df(_base_event(qualifiers=quals))
    out = enrich_events(df)
    assert out["is_through_ball"].iloc[0]


def test_enrich_events_throughball_wrong_name_no_flag():
    """ThroughBall (wrong casing) must NOT set is_through_ball — regression guard."""
    quals = str(_make_quals("ThroughBall"))
    df = _df(_base_event(qualifiers=quals))
    out = enrich_events(df)
    assert not out["is_through_ball"].iloc[0]


def test_enrich_events_intentional_assist_flag():
    quals = str(_make_quals("IntentionalAssist"))
    df = _df(_base_event(qualifiers=quals))
    out = enrich_events(df)
    assert out["is_assist"].iloc[0]


def test_enrich_events_pass_type_flag():
    df = _df(_base_event(type="Pass"))
    out = enrich_events(df)
    assert out["is_pass"].iloc[0]


def test_enrich_events_takeon_and_successful_is_sca():
    df = _df(_base_event(type="TakeOn", outcomeType="Successful"))
    out = enrich_events(df)
    assert out["is_shot_creating_action"].iloc[0]


def test_enrich_events_failed_takeon_not_sca():
    df = _df(_base_event(type="TakeOn", outcomeType="Unsuccessful"))
    out = enrich_events(df)
    assert not out["is_shot_creating_action"].iloc[0]


def test_enrich_events_progressive_pass_with_coords():
    """Pass that moves ball from x=20 to endX=70 — 0.75*(100-20)=60, (100-70)=30 <= 60."""
    row = _base_event(type="Pass", outcomeType="Successful", x=20, endX=70, y=50, endY=50)
    out = enrich_events(_df(row))
    assert out["is_progressive_pass"].iloc[0]


def test_enrich_events_non_progressive_pass():
    """Pass that barely moves forward — x=50 to endX=55."""
    row = _base_event(type="Pass", outcomeType="Successful", x=50, endX=55, y=50, endY=50)
    out = enrich_events(_df(row))
    # (100-55)=45, 0.75*(100-50)=37.5 → 45 > 37.5 → NOT progressive
    assert not out["is_progressive_pass"].iloc[0]


def test_enrich_events_pass_into_final_third():
    """Pass from x=60 ending at endX=70 crosses the 66.7 line."""
    row = _base_event(type="Pass", outcomeType="Successful", x=60, endX=70, y=50, endY=50)
    out = enrich_events(_df(row))
    assert out["is_pass_into_final_third"].iloc[0]


def test_enrich_events_pass_into_penalty_area():
    row = _base_event(type="Pass", outcomeType="Successful", x=70, endX=90, y=50, endY=50)
    out = enrich_events(_df(row))
    assert out["is_pass_into_penalty_area"].iloc[0]
