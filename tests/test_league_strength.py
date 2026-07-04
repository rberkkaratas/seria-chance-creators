"""Tests for src/enrichment/league_strength.py."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.enrichment.league_strength import (
    compute_club_elos,
    compute_league_mean_elos,
    compute_offsets,
)


def test_compute_offsets_symmetric_pair():
    offsets = compute_offsets({"A": 2000.0, "B": 1730.0}, elo_per_sigma=270.0)
    assert offsets["A"] == pytest.approx(0.5)
    assert offsets["B"] == pytest.approx(-0.5)
    assert sum(offsets.values()) == pytest.approx(0.0)


def test_compute_offsets_single_league_is_zero():
    assert compute_offsets({"A": 1850.0}, elo_per_sigma=270.0) == {"A": 0.0}


def _clubelo_frame():
    rows = [
        ("Arsenal", "ENG", 1, 2000.0),
        ("Man City", "ENG", 1, 1960.0),
        ("Leeds", "ENG", 2, 1700.0),
        ("Coventry", "ENG", 2, 1660.0),
        ("Ajax", "NED", 1, 1750.0),
    ]
    return pd.DataFrame(rows, columns=["Club", "Country", "Level", "Elo"])


def test_compute_league_mean_elos_filters_country_and_level():
    result = compute_league_mean_elos(
        _clubelo_frame(),
        league_clubelo={
            "Premier_League": ("ENG", 1),
            "Championship": ("ENG", 2),
            "Eredivisie": ("NED", 1),
        },
    ).set_index("league")

    assert result.loc["Premier_League", "mean_elo"] == pytest.approx(1980.0)
    assert result.loc["Championship", "mean_elo"] == pytest.approx(1680.0)
    assert result.loc["Premier_League", "n_clubs"] == 2
    assert result.loc["Eredivisie", "n_clubs"] == 1


def test_compute_league_mean_elos_raises_on_zero_clubs():
    with pytest.raises(RuntimeError, match="Super_Lig"):
        compute_league_mean_elos(
            _clubelo_frame(),
            league_clubelo={"Super_Lig": ("TUR", 1)},
        )


def _clubelo_frame_with_unconfigured():
    rows = [
        ("Arsenal", "ENG", 1, 2000.0),
        ("Man City", "ENG", 1, 1960.0),
        ("Leeds", "ENG", 2, 1700.0),
        ("Coventry", "ENG", 2, 1660.0),
        ("Ajax", "NED", 1, 1750.0),
        # Unconfigured (country, level) pair — should be filtered out.
        ("Bayern", "GER", 1, 2100.0),
    ]
    return pd.DataFrame(rows, columns=["Club", "Country", "Level", "Elo"])


def test_compute_club_elos_columns_and_league_filter():
    league_clubelo = {
        "Premier_League": ("ENG", 1),
        "Championship": ("ENG", 2),
        "Eredivisie": ("NED", 1),
    }
    result = compute_club_elos(
        _clubelo_frame_with_unconfigured(),
        league_clubelo=league_clubelo,
    )

    assert set(result.columns) == {"league", "club", "country_code", "level", "elo"}

    # Only configured leagues are present — Bundesliga (GER, 1) is excluded.
    assert set(result["league"]) == {"Premier_League", "Championship", "Eredivisie"}
    assert "Bayern" not in set(result["club"])

    # Correct league-key mapping: ENG level 2 -> Championship.
    championship = result[result["league"] == "Championship"]
    assert set(championship["club"]) == {"Leeds", "Coventry"}
    assert (championship["country_code"] == "ENG").all()
    assert (championship["level"] == 2).all()

    arsenal = result[result["club"] == "Arsenal"].iloc[0]
    assert arsenal["league"] == "Premier_League"
    assert arsenal["elo"] == pytest.approx(2000.0)


def test_compute_club_elos_missing_league_raises():
    with pytest.raises(RuntimeError, match="Super_Lig"):
        compute_club_elos(
            _clubelo_frame(),
            league_clubelo={"Super_Lig": ("TUR", 1)},
        )
