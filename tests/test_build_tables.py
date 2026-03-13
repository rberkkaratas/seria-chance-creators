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
    """Without satisfiedEventsTypes column, fallback uses IntentionalAssist qualifier."""
    quals = str(_make_quals("IntentionalAssist"))
    df = _df(_base_event(type="Pass", qualifiers=quals))
    # No satisfiedEventsTypes column → qualifier-based fallback applies
    assert "satisfiedEventsTypes" not in df.columns
    out = enrich_events(df)
    assert out["is_assist"].iloc[0]


def test_enrich_events_assist_via_satisfied_events_type_92():
    """
    Primary path: Pass event with 92 in satisfiedEventsTypes = real assist.
    WhoScored event-type 92 is present only on pass events that led directly to a goal.
    """
    row = _base_event(type="Pass", outcomeType="Successful")
    row["satisfiedEventsTypes"] = str([91, 92, 100, 119])
    df = _df(row)
    out = enrich_events(df)
    assert out["is_assist"].iloc[0], "Pass with 92 in satisfiedEventsTypes must be an assist"


def test_enrich_events_key_pass_no_goal_not_assist():
    """
    Regression: IntentionalAssist qualifier ≈ KeyPass in WhoScored — it appears on
    ALL passes leading to shots, not just goals. A pass with IntentionalAssist but
    without 92 in satisfiedEventsTypes must NOT be counted as an assist.
    """
    quals = str(_make_quals("IntentionalAssist"))
    row = _base_event(type="Pass", qualifiers=quals)
    row["satisfiedEventsTypes"] = str([91, 119, 117, 123])  # no 92
    df = _df(row)
    out = enrich_events(df)
    assert not out["is_assist"].iloc[0], (
        "Pass with IntentionalAssist but no 92 in satisfiedEventsTypes is a key pass, not an assist"
    )


def test_enrich_events_goal_with_92_not_assist():
    """
    Regression: WhoScored also puts 92 in satisfiedEventsTypes of the GOAL event itself.
    The goal event must NOT be counted as an assist — only the preceding pass counts.
    """
    row = _base_event(type="Goal", outcomeType="Successful")
    row["satisfiedEventsTypes"] = str([91, 92, 24, 9])
    df = _df(row)
    out = enrich_events(df)
    assert not out["is_assist"].iloc[0], (
        "Goal event with 92 in satisfiedEventsTypes must not be counted as an assist"
    )


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


def test_enrich_events_forward_pass():
    """Pass from x=30 to endX=60 is a forward pass (endX > x)."""
    row = _base_event(type="Pass", outcomeType="Successful", x=30, endX=60, y=50, endY=50)
    out = enrich_events(_df(row))
    assert out["is_forward_pass"].iloc[0]


def test_enrich_events_backward_pass_not_forward():
    """Pass from x=60 to endX=40 is NOT a forward pass."""
    row = _base_event(type="Pass", outcomeType="Successful", x=60, endX=40, y=50, endY=50)
    out = enrich_events(_df(row))
    assert not out["is_forward_pass"].iloc[0]


def test_enrich_events_failed_pass_not_forward():
    """Unsuccessful pass must not be counted as forward pass."""
    row = _base_event(type="Pass", outcomeType="Unsuccessful", x=30, endX=60, y=50, endY=50)
    out = enrich_events(_df(row))
    assert not out["is_forward_pass"].iloc[0]


def test_enrich_events_penalty_area_touch():
    """Event at x=90, y=50 is inside the penalty area."""
    row = _base_event(type="Pass", outcomeType="Successful", x=90, y=50, endX=95, endY=50)
    out = enrich_events(_df(row))
    assert out["is_penalty_area_touch"].iloc[0]


def test_enrich_events_outside_penalty_area_not_flagged():
    """Event at x=70 should not be a penalty area touch."""
    row = _base_event(type="Pass", outcomeType="Successful", x=70, y=50, endX=75, endY=50)
    out = enrich_events(_df(row))
    assert not out["is_penalty_area_touch"].iloc[0]


def test_enrich_events_half_space_pass_left():
    """Pass ending at endX=70, endY=30 lands in the left half-space."""
    row = _base_event(type="Pass", outcomeType="Successful", x=50, endX=70, y=50, endY=30)
    out = enrich_events(_df(row))
    assert out["is_half_space_pass"].iloc[0]


def test_enrich_events_half_space_pass_right():
    """Pass ending at endX=70, endY=70 lands in the right half-space."""
    row = _base_event(type="Pass", outcomeType="Successful", x=50, endX=70, y=50, endY=70)
    out = enrich_events(_df(row))
    assert out["is_half_space_pass"].iloc[0]


def test_enrich_events_central_pass_not_half_space():
    """Pass ending centrally (endY=50) must NOT be a half-space pass."""
    row = _base_event(type="Pass", outcomeType="Successful", x=50, endX=70, y=50, endY=50)
    out = enrich_events(_df(row))
    assert not out["is_half_space_pass"].iloc[0]


def test_enrich_events_possession_won_final_third():
    """Ball recovery at x=70 is in the final third."""
    row = _base_event(type="BallRecovery", outcomeType="Successful", x=70, y=50, endX=70, endY=50)
    out = enrich_events(_df(row))
    assert out["is_possession_won_final_third"].iloc[0]


def test_enrich_events_possession_won_own_half_not_final_third():
    """Ball recovery at x=40 is NOT in the final third."""
    row = _base_event(type="BallRecovery", outcomeType="Successful", x=40, y=50, endX=40, endY=50)
    out = enrich_events(_df(row))
    assert not out["is_possession_won_final_third"].iloc[0]


def test_enrich_events_ball_winning_height_accumulator():
    """Interception at x=55 should contribute x=55 to ball_winning_x_contrib."""
    row = _base_event(type="Interception", outcomeType="Successful", x=55, y=50, endX=55, endY=50)
    out = enrich_events(_df(row))
    assert out["ball_winning_count"].iloc[0] == 1
    assert abs(out["ball_winning_x_contrib"].iloc[0] - 55.0) < 1e-9


def test_enrich_events_non_defensive_event_no_ball_winning_contrib():
    """A pass should not contribute to ball_winning accumulators."""
    row = _base_event(type="Pass", outcomeType="Successful", x=55, y=50, endX=65, endY=50)
    out = enrich_events(_df(row))
    assert out["ball_winning_count"].iloc[0] == 0
    assert out["ball_winning_x_contrib"].iloc[0] == 0.0


# ─── carry_into_final_third (sequential inference) ────────────────────

def _seq_df(*rows):
    """Build a multi-row DataFrame for sequential carry tests."""
    base = {"qualifiers": "[]", "teamId": 10, "period": 1, "minute": 10, "second": 0}
    out = []
    for i, row in enumerate(rows):
        r = {**base, "second": i * 10}
        r.update(row)
        out.append(r)
    return pd.DataFrame(out)


def test_carry_into_final_third_after_ball_recovery():
    """
    Player wins ball at x=60 (BallRecovery), next event at x=70 with gap=10 ≤ 30
    → flagged as carry into the final third.
    """
    rows = _seq_df(
        {"playerId": 1, "type": "BallRecovery", "outcomeType": "Successful",
         "x": 60, "y": 50, "endX": None, "endY": None},
        {"playerId": 1, "type": "Pass", "outcomeType": "Successful",
         "x": 70, "y": 50, "endX": 80, "endY": 50},
    )
    out = enrich_events(rows)
    assert out["is_carry_into_final_third"].iloc[1] is True or out["is_carry_into_final_third"].iloc[1] == True


def test_carry_into_final_third_after_successful_pass_not_flagged():
    """
    After a successful pass (player gave ball away), next event in final third
    is a new ball reception — NOT a carry.
    """
    rows = _seq_df(
        {"playerId": 1, "type": "Pass", "outcomeType": "Successful",
         "x": 55, "y": 50, "endX": 60, "endY": 50},
        {"playerId": 1, "type": "Pass", "outcomeType": "Successful",
         "x": 70, "y": 50, "endX": 80, "endY": 50},
    )
    out = enrich_events(rows)
    assert not out["is_carry_into_final_third"].iloc[1]


def test_carry_into_final_third_large_gap_not_flagged():
    """
    Gap of 45 units (x=20 → x=65) exceeds the 30-unit threshold — likely a long
    pass reception, not a carry.
    """
    rows = _seq_df(
        {"playerId": 1, "type": "BallRecovery", "outcomeType": "Successful",
         "x": 20, "y": 50, "endX": None, "endY": None},
        {"playerId": 1, "type": "Pass", "outcomeType": "Successful",
         "x": 70, "y": 50, "endX": 80, "endY": 50},
    )
    out = enrich_events(rows)
    assert not out["is_carry_into_final_third"].iloc[1]


def test_carry_into_final_third_already_inside_not_flagged():
    """
    Previous event also inside the final third (x=70) → no crossing of the line.
    """
    rows = _seq_df(
        {"playerId": 1, "type": "BallRecovery", "outcomeType": "Successful",
         "x": 70, "y": 50, "endX": None, "endY": None},
        {"playerId": 1, "type": "Pass", "outcomeType": "Successful",
         "x": 75, "y": 50, "endX": 85, "endY": 50},
    )
    out = enrich_events(rows)
    assert not out["is_carry_into_final_third"].iloc[1]
