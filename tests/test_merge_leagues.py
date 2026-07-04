"""Tests for src/features/merge_leagues.py (league-anchored global percentiles)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.features.merge_leagues import (
    compute_global_percentiles,
    compute_global_role_scores,
)


def _pct_frame(rows):
    """Build a minimal merge-input frame for one metric (tackles_p90)."""
    df = pd.DataFrame(rows)
    df["tackles_p90_pct"] = 0.0
    if "tackles_p90" not in df.columns:
        # Raw values deliberately absent/arbitrary — the rerank must not use them.
        df["tackles_p90"] = 0.0
    return df


def test_global_percentiles_follow_league_pct_not_raw_values():
    # Raw values are wildly inverted vs the within-league percentiles: the
    # league-anchored rerank must follow _league_pct and ignore raws.
    df = _pct_frame([
        {config.POSITION_GROUP_COL: "DEF", "league": "L1", "player_name": "D1",
         "tackles_p90": 999.0, "tackles_p90_league_pct": 25.0},
        {config.POSITION_GROUP_COL: "DEF", "league": "L1", "player_name": "D2",
         "tackles_p90": 1.0, "tackles_p90_league_pct": 75.0},
        {config.POSITION_GROUP_COL: "MID", "league": "L2", "player_name": "M1",
         "tackles_p90": 500.0, "tackles_p90_league_pct": 25.0},
        {config.POSITION_GROUP_COL: "MID", "league": "L2", "player_name": "M2",
         "tackles_p90": 2.0, "tackles_p90_league_pct": 75.0},
    ])
    result = compute_global_percentiles(df, offsets={"L1": 0.0, "L2": 0.0})

    d2 = result.loc[result["player_name"] == "D2", "tackles_p90_pct"].iloc[0]
    d1 = result.loc[result["player_name"] == "D1", "tackles_p90_pct"].iloc[0]
    m2 = result.loc[result["player_name"] == "M2", "tackles_p90_pct"].iloc[0]
    assert d2 == 100.0
    assert d1 == 50.0
    # Ranked within position group, not across the whole pool.
    assert m2 == 100.0


def test_stronger_league_lifts_equal_league_percentile():
    df = _pct_frame([
        {config.POSITION_GROUP_COL: "MID", "league": "A", "player_name": f"A{i}",
         "tackles_p90_league_pct": p}
        for i, p in enumerate([20.0, 50.0, 80.0])
    ] + [
        {config.POSITION_GROUP_COL: "MID", "league": "B", "player_name": f"B{i}",
         "tackles_p90_league_pct": p}
        for i, p in enumerate([20.0, 50.0, 80.0])
    ])
    result = compute_global_percentiles(df, offsets={"A": 0.5, "B": -0.5})

    pct = lambda name: result.loc[result["player_name"] == name, "tackles_p90_pct"].iloc[0]
    # Every A player outranks the B player with the same within-league pct.
    for i in range(3):
        assert pct(f"A{i}") > pct(f"B{i}")
    # With a 1.0 SD gap, A's median even beats B's 80th percentile.
    assert pct("A1") > pct("B2")


def test_within_league_ordering_preserved():
    df = _pct_frame([
        {config.POSITION_GROUP_COL: "MID", "league": lg, "player_name": f"{lg}{i}",
         "tackles_p90_league_pct": p}
        for lg, off in [("A", 0), ("B", 0)]
        for i, p in enumerate([10.0, 50.0, 90.0])
    ])
    result = compute_global_percentiles(df, offsets={"A": 0.8, "B": -0.3})

    for lg in ["A", "B"]:
        league_rows = result[result["league"] == lg].sort_values("tackles_p90_league_pct")
        assert league_rows["tackles_p90_pct"].is_monotonic_increasing


def test_extreme_percentiles_clipped_and_nan_preserved():
    df = _pct_frame([
        {config.POSITION_GROUP_COL: "MID", "league": "A", "player_name": "P0",
         "tackles_p90_league_pct": 0.0},
        {config.POSITION_GROUP_COL: "MID", "league": "A", "player_name": "P100",
         "tackles_p90_league_pct": 100.0},
        {config.POSITION_GROUP_COL: "MID", "league": "A", "player_name": "PNaN",
         "tackles_p90_league_pct": np.nan},
    ])
    result = compute_global_percentiles(df, offsets={"A": 0.0})

    p0 = result.loc[result["player_name"] == "P0", "tackles_p90_pct"].iloc[0]
    p100 = result.loc[result["player_name"] == "P100", "tackles_p90_pct"].iloc[0]
    pnan = result.loc[result["player_name"] == "PNaN", "tackles_p90_pct"].iloc[0]
    assert np.isfinite(p0) and np.isfinite(p100)
    assert p100 > p0
    assert pd.isna(pnan)


def test_missing_offset_raises_with_league_name():
    df = _pct_frame([
        {config.POSITION_GROUP_COL: "MID", "league": "C", "player_name": "P",
         "tackles_p90_league_pct": 50.0},
    ])
    with pytest.raises(KeyError, match="C"):
        compute_global_percentiles(df, offsets={"A": 0.0, "B": 0.0})


def test_global_role_scores_drop_league_copies():
    group = "MID"
    roles = config.POSITION_GROUPS[group]["roles"]
    metrics = sorted({m for weights in roles.values() for m in weights})

    rng = np.random.default_rng(7)
    n = 8
    df = pd.DataFrame({
        config.POSITION_GROUP_COL: [group] * n,
        "league": ["A"] * (n // 2) + ["B"] * (n // 2),
        "player_name": [f"P{i}" for i in range(n)],
        "position": ["MC"] * n,
    })
    for m in metrics:
        df[f"{m}_pct"] = rng.uniform(0, 100, n)
    # Simulate per-league CSV input: role scores / primary_role already present.
    stale_role_col = f"{config.ROLE_SCORE_COL_PREFIX}{list(roles)[0]}"
    df[stale_role_col] = -1.0
    df[config.PRIMARY_ROLE_COL] = "Stale"

    result = compute_global_role_scores(df)

    league_leftovers = [
        c for c in result.columns
        if c.endswith("_league") or c == "primary_role_league"
    ]
    assert league_leftovers == []
    # Recomputed in place, not carried over.
    assert (result[stale_role_col] != -1.0).all()
    assert (result[config.PRIMARY_ROLE_COL] != "Stale").all()
    assert result[config.OVERALL_SCORE_COL].between(0, 100).all()
