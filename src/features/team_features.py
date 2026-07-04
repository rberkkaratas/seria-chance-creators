"""
Team Features — SquadLens Team Analytics
----------------------------------------
Aggregates per-match team/player data and the merged player scores into a
single committed CSV, one row per team, for the ten configured leagues.

Inputs (all per-league, 2025/26):
  data/processed/{league}/{season}/matches.csv   — one row per match
  data/processed/{league}/{season}/teams.csv     — two rows per match
  data/processed/{league}/{season}/players.csv    — one row per player per match
  data/final/all_leagues_{season}_enriched.csv    — merged player scores
    (fallback: all_leagues_{season}.csv — no market values)

The output has one row per (league, team_id, team_name) with four blocks:

  results  — W/D/L, points, goals, home/away splits, league table rank
  style    — possession, pass/shot/press proxies, per-match action volumes
  squad    — squad size, age, market value (present-but-NaN on the fallback)
  rating   — minutes-weighted latent-z squad strength, group sub-ratings,
             coverage flag, and a performance-vs-quality rank delta

Team ratings reuse the merge-step idiom: each qualified (player, group) row's
overall_score (a 0-100 within-group cross-league percentile) is mapped to a
latent z (inverse normal CDF of the clipped percentile), then minutes-weighted
into a team mean and percentile-ranked across all teams to 0-100. Minutes are
group-scoped, so a player qualifying in two groups is weighted by the sum of
their group minutes and never double-counted.

Output: data/final/teams_{season}.csv

Usage:
    python -m src.features.team_features --season 2025-2026
    python -m src.features.team_features --season 2025-2026 --league Serie_A
    python -m src.features.team_features --season 2025-2026 --league all
"""

import argparse
import unicodedata
from datetime import date
from statistics import NormalDist

import numpy as np
import pandas as pd

import config

try:  # optional dependency — the club Elo cache is built by a parallel task
    from src.enrichment.league_strength import load_club_elos as _load_club_elos
except Exception:  # pragma: no cover - loader unavailable during early rollout
    _load_club_elos = None


# ─── CLI ─────────────────────────────────────────────────────────────

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Aggregate per-match data into one team-analytics row per team"
    )
    parser.add_argument(
        "--season", default=config.SEASON,
        help="Season string, e.g. 2025-2026 (default: %(default)s)"
    )
    parser.add_argument(
        "--league", action="append", default=None,
        help=(
            "League key to include (repeatable). Use '--league all' or omit "
            "to process every configured league."
        ),
    )
    parser.add_argument(
        "--table-scope",
        default=config.TABLE_SCOPE_REGULAR,
        help=(
            "Competition table scope to aggregate. Default regular_season keeps "
            "domestic league tables separate from playoffs/continental matches."
        ),
    )
    return parser.parse_args()


def _resolve_leagues(leagues: list[str] | None) -> list[str]:
    """Normalize the --league argument into a concrete list of league keys."""
    if not leagues or "all" in leagues:
        return list(config.LEAGUES.keys())
    return leagues


# ─── Load ─────────────────────────────────────────────────────────────

def load_processed(
    leagues: list[str], season: str
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load and concat per-league processed frames, deduped on match_id.

    Returns (matches, teams, players). matches is deduped to one row per
    match_id (like DataLoader.load_raw); teams/players are restricted to the
    surviving match_ids so downstream joins stay consistent. A missing
    per-league processed directory is a printed warning + skip, not an error.
    """
    matches_frames: list[pd.DataFrame] = []
    teams_frames: list[pd.DataFrame] = []
    players_frames: list[pd.DataFrame] = []

    for league in leagues:
        base = config.get_processed_path(league, season)
        m_path = base / "matches.csv"
        t_path = base / "teams.csv"
        p_path = base / "players.csv"
        if not (m_path.exists() and t_path.exists() and p_path.exists()):
            print(f"  [!] processed data incomplete for {league} at {base} — skipping.")
            continue

        matches = pd.read_csv(m_path)
        teams = pd.read_csv(t_path)
        players = pd.read_csv(p_path)
        for frame in (matches, teams, players):
            frame["league"] = league

        # Dedupe matches on match_id (repeat scrapes append rows).
        matches = matches.drop_duplicates(subset="match_id")
        valid_ids = set(matches["match_id"])
        teams = teams[teams["match_id"].isin(valid_ids)].copy()
        players = players[players["match_id"].isin(valid_ids)].copy()

        matches_frames.append(matches)
        teams_frames.append(teams)
        players_frames.append(players)
        print(
            f"  Loaded {league}: {len(matches)} matches, "
            f"{teams['team_id'].nunique()} teams, {len(players)} player-matches"
        )

    if not matches_frames:
        raise FileNotFoundError(
            "No processed data found for any requested league. Run "
            "build_tables.py first."
        )

    matches = pd.concat(matches_frames, ignore_index=True)
    teams = pd.concat(teams_frames, ignore_index=True)
    players = pd.concat(players_frames, ignore_index=True)
    return matches, teams, players


def _load_enriched_players(season: str) -> tuple[pd.DataFrame, bool]:
    """
    Load the merged per-(player, group) scores. Prefer the enriched file
    (has market values); fall back to the plain merged file (no market
    values → squad-value columns are NaN). Missing BOTH is a hard error.

    Returns (frame, has_market_values).
    """
    enriched_path = config.DATA_FINAL / f"all_leagues_{season}_enriched.csv"
    plain_path = config.DATA_FINAL / f"all_leagues_{season}.csv"

    if enriched_path.exists():
        print(f"  Loaded merged player scores: {enriched_path.name}")
        return pd.read_csv(enriched_path), True
    if plain_path.exists():
        print(
            f"  [!] {enriched_path.name} not found — using {plain_path.name} "
            f"(no market values; squad-value columns will be NaN)."
        )
        return pd.read_csv(plain_path), False

    raise FileNotFoundError(
        f"Merged player file not found. Expected one of:\n"
        f"  {enriched_path}\n  {plain_path}\n"
        f"Run: python -m src.features.merge_leagues --season {season}"
    )


def _team_key_series(df: pd.DataFrame, team_col: str) -> pd.Series:
    """Stable league/team-id key; handles CSVs that read ids as int or float."""
    team_ids = pd.to_numeric(df[team_col], errors="coerce").astype("Int64").astype(str)
    return df["league"].astype(str) + "||" + team_ids


def filter_processed_to_scored_team_pool(
    matches: pd.DataFrame,
    teams: pd.DataFrame,
    players: pd.DataFrame,
    enriched: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Drop processed fixture leakage for teams that do not exist in the merged
    scored-player pool for that league.

    This guards against occasional wrong-league fixture rows in processed CSVs
    (for example a one-off Bundesliga match landing under Premier_League).
    Real teams remain present because the current scored pool covers every
    configured league team; low rating coverage is still flagged later rather
    than used as a drop condition.
    """
    required = {"league", "team_id"}
    if not required.issubset(enriched.columns) or enriched.empty:
        return matches, teams, players

    valid_keys = set(_team_key_series(enriched.drop_duplicates(["league", "team_id"]), "team_id"))
    if not valid_keys:
        return matches, teams, players

    home_valid = _team_key_series(matches, "home_team_id").isin(valid_keys)
    away_valid = _team_key_series(matches, "away_team_id").isin(valid_keys)
    valid_match_mask = home_valid & away_valid
    dropped_matches = int((~valid_match_mask).sum())

    if dropped_matches:
        leaked = matches.loc[~valid_match_mask, [
            "league", "match_id", "home_team_name", "away_team_name",
        ]]
        summary = "; ".join(
            f"{r.league} {r.match_id}: {r.home_team_name} vs {r.away_team_name}"
            for r in leaked.itertuples(index=False)
        )
        print(f"  [!] Dropped {dropped_matches} wrong-league fixture row(s): {summary}")

    filtered_matches = matches[valid_match_mask].copy()
    valid_match_ids = set(filtered_matches["match_id"])

    team_valid = _team_key_series(teams, "team_id").isin(valid_keys)
    filtered_teams = teams[team_valid & teams["match_id"].isin(valid_match_ids)].copy()

    player_valid = _team_key_series(players, "team_id").isin(valid_keys)
    filtered_players = players[
        player_valid & players["match_id"].isin(valid_match_ids)
    ].copy()

    return filtered_matches, filtered_teams, filtered_players


def ensure_competition_columns(
    matches: pd.DataFrame,
    teams: pd.DataFrame,
    players: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Backfill competition columns for processed data built before phase metadata."""
    defaults = {
        "competition_key": "",
        "competition_type": config.COMPETITION_TYPE_DOMESTIC,
        "competition_phase": config.PHASE_REGULAR_SEASON,
        "phase_table_scope": config.TABLE_SCOPE_REGULAR,
        "source_stage_id": "",
        "validation_status": config.VALIDATION_PENDING,
    }
    frames = []
    for frame in (matches.copy(), teams.copy(), players.copy()):
        for col, value in defaults.items():
            if col not in frame.columns:
                frame[col] = value
            else:
                frame[col] = frame[col].replace("", np.nan).fillna(value)
        if "league" in frame.columns:
            frame["competition_key"] = np.where(
                frame["competition_key"].astype(str).str.len() > 0,
                frame["competition_key"],
                frame["league"],
            )
        frames.append(frame)
    return frames[0], frames[1], frames[2]


def filter_to_table_scope(
    matches: pd.DataFrame,
    teams: pd.DataFrame,
    players: pd.DataFrame,
    table_scope: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Restrict processed frames to the requested competition table scope."""
    matches, teams, players = ensure_competition_columns(matches, teams, players)
    valid_status = matches["validation_status"] != config.VALIDATION_WRONG_COMPETITION
    scope_mask = matches["phase_table_scope"] == table_scope
    scoped_matches = matches[valid_status & scope_mask].copy()
    valid_ids = set(scoped_matches["match_id"].astype(str))

    scoped_teams = teams[teams["match_id"].astype(str).isin(valid_ids)].copy()
    scoped_players = players[players["match_id"].astype(str).isin(valid_ids)].copy()

    return scoped_matches, scoped_teams, scoped_players


# ─── Results Table ────────────────────────────────────────────────────

def compute_results_table(matches: pd.DataFrame) -> pd.DataFrame:
    """
    Per-team season results from the matches table.

    Produces matches_played, wins/draws/losses, goals_for/against, goal_diff,
    points (3/1/0), points_per_match, and home/away splits, plus
    league_rank_points (rank within league by Pts desc, then GD, then GF).

    Head-to-head tiebreakers are NOT applied — this is a points/GD/GF ordering
    only, so it may diverge from an official table where teams are level.
    """
    rows: list[dict] = []
    for _, m in matches.iterrows():
        league = m["league"]
        hs, as_ = m["home_score"], m["away_score"]
        if pd.isna(hs) or pd.isna(as_):
            continue
        hs, as_ = int(hs), int(as_)
        # Home team perspective, then away team perspective.
        for side, team_id, team_name, gf, ga in (
            ("home", m["home_team_id"], m["home_team_name"], hs, as_),
            ("away", m["away_team_id"], m["away_team_name"], as_, hs),
        ):
            win = gf > ga
            draw = gf == ga
            loss = gf < ga
            rows.append({
                "league": league,
                "team_id": team_id,
                "team_name": team_name,
                "side": side,
                "gf": gf,
                "ga": ga,
                "win": int(win),
                "draw": int(draw),
                "loss": int(loss),
                "points": 3 if win else (1 if draw else 0),
            })

    if not rows:
        return pd.DataFrame(
            columns=["league", "team_id", "team_name", "matches_played"]
        )

    long = pd.DataFrame(rows)

    def _aggregate(frame: pd.DataFrame, prefix: str = "") -> pd.DataFrame:
        agg = (
            frame.groupby(["league", "team_id"])
            .agg(
                matches=("points", "size"),
                wins=("win", "sum"),
                draws=("draw", "sum"),
                losses=("loss", "sum"),
                goals_for=("gf", "sum"),
                goals_against=("ga", "sum"),
                points=("points", "sum"),
            )
            .reset_index()
        )
        rename = {
            "matches": f"{prefix}matches" if prefix else "matches_played",
            "wins": f"{prefix}wins",
            "draws": f"{prefix}draws",
            "losses": f"{prefix}losses",
            "goals_for": f"{prefix}goals_for",
            "goals_against": f"{prefix}goals_against",
            "points": f"{prefix}points",
        }
        return agg.rename(columns=rename)

    overall = _aggregate(long)
    home = _aggregate(long[long["side"] == "home"], prefix="home_")
    away = _aggregate(long[long["side"] == "away"], prefix="away_")

    # A team-name lookup independent of home/away framing.
    names = (
        long.groupby(["league", "team_id"])["team_name"].agg(
            lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]
        ).reset_index()
    )

    results = names.merge(overall, on=["league", "team_id"], how="left")
    results = results.merge(home, on=["league", "team_id"], how="left")
    results = results.merge(away, on=["league", "team_id"], how="left")

    split_cols = [
        "home_matches", "home_wins", "home_draws", "home_losses",
        "home_goals_for", "home_goals_against", "home_points",
        "away_matches", "away_wins", "away_draws", "away_losses",
        "away_goals_for", "away_goals_against", "away_points",
    ]
    for col in split_cols:
        if col not in results.columns:
            results[col] = 0
        results[col] = results[col].fillna(0).astype(int)

    results["goal_diff"] = results["goals_for"] - results["goals_against"]
    results["points_per_match"] = np.where(
        results["matches_played"] > 0,
        results["points"] / results["matches_played"],
        np.nan,
    )

    # League rank by Pts desc, then GD desc, then GF desc (no head-to-head).
    results = results.sort_values(
        ["league", "points", "goal_diff", "goals_for"],
        ascending=[True, False, False, False],
    )
    results["league_rank_points"] = (
        results.groupby("league").cumcount() + 1
    )
    return results.reset_index(drop=True)


# ─── Style Metrics ────────────────────────────────────────────────────

def compute_style_metrics(
    teams: pd.DataFrame, players: pd.DataFrame, matches: pd.DataFrame
) -> pd.DataFrame:
    """
    Per-team style/volume metrics from teams.csv and players.csv.

    teams.csv metrics: possession_share (per-match pass share averaged over
    matches — the same proxy player_features uses for opponent possession),
    pass_accuracy, per-match pass/shot/goal volumes plus opponent shots/goals
    via the match_id join, shot conversion for/against, key_passes_per_match,
    and ppda_proxy (opponent passes / (own tackles + interceptions), per match
    then averaged; lower = a more intense press).

    players.csv metrics: per-match action volumes summed to team-match then
    averaged, plus season-total ratios (long_ball_share, forward_pass_pct,
    aerial_win_rate, ball_winning_height). GK rows are INCLUDED in these team
    action sums — they are real team actions.
    """
    # ── teams.csv: attach opponent totals via a self-join on match_id ──
    t = teams.copy()
    opp = t[[
        "league", "match_id", "team_id", "total_passes", "total_shots", "goals",
    ]].rename(columns={
        "team_id": "opp_team_id",
        "total_passes": "opp_total_passes",
        "total_shots": "opp_total_shots",
        "goals": "opp_goals",
    })
    merged = t.merge(opp, on=["league", "match_id"])
    merged = merged[merged["team_id"] != merged["opp_team_id"]].copy()

    denom = (merged["total_passes"] + merged["opp_total_passes"]).replace(0, np.nan)
    merged["_poss_share"] = merged["total_passes"] / denom
    tackles_plus_int = (merged["tackles"] + merged["interceptions"]).replace(0, np.nan)
    merged["_ppda"] = merged["opp_total_passes"] / tackles_plus_int

    team_style = (
        merged.groupby(["league", "team_id"])
        .agg(
            _n_matches=("match_id", "nunique"),
            possession_share=("_poss_share", "mean"),
            ppda_proxy=("_ppda", "mean"),
            _total_passes=("total_passes", "sum"),
            _accurate_passes=("accurate_passes", "sum"),
            _total_shots=("total_shots", "sum"),
            _opp_shots=("opp_total_shots", "sum"),
            _goals=("goals", "sum"),
            _opp_goals=("opp_goals", "sum"),
            _key_passes=("key_passes", "sum"),
        )
        .reset_index()
    )

    n = team_style["_n_matches"].replace(0, np.nan)
    team_style["pass_accuracy"] = (
        team_style["_accurate_passes"] / team_style["_total_passes"].replace(0, np.nan)
    )
    team_style["passes_per_match"] = team_style["_total_passes"] / n
    team_style["shots_per_match"] = team_style["_total_shots"] / n
    team_style["shots_conceded_per_match"] = team_style["_opp_shots"] / n
    team_style["goals_per_match"] = team_style["_goals"] / n
    team_style["goals_conceded_per_match"] = team_style["_opp_goals"] / n
    team_style["shot_conversion"] = (
        team_style["_goals"] / team_style["_total_shots"].replace(0, np.nan)
    )
    team_style["shot_conversion_against"] = (
        team_style["_opp_goals"] / team_style["_opp_shots"].replace(0, np.nan)
    )
    team_style["key_passes_per_match"] = team_style["_key_passes"] / n

    team_style = team_style.drop(columns=[c for c in team_style.columns if c.startswith("_")])

    # ── players.csv: sum to team-match, average per match, plus ratios ──
    player_style = _compute_player_style(players)

    style = team_style.merge(player_style, on=["league", "team_id"], how="outer")
    return style


def _compute_player_style(players: pd.DataFrame) -> pd.DataFrame:
    """Team-match sums of player actions, averaged per match, plus season ratios."""
    p = players.copy()

    per_match_cols = {
        "progressive_passes": "progressive_passes_pm",
        "passes_into_final_third": "passes_into_final_third_pm",
        "long_balls": "long_balls_pm",
        "crosses": "crosses_pm",
        "successful_dribbles": "dribbles_pm",
        "aerials_won": "aerials_won_pm",
        "ball_recoveries": "ball_recoveries_pm",
        "possession_won_final_third": "possession_won_final_third_pm",
        "touches_final_third": "touches_final_third_pm",
        "penalty_area_touches": "penalty_area_touches_pm",
    }
    ratio_source_cols = [
        "total_passes", "forward_passes", "long_balls",
        "aerials_total", "aerials_won",
        "ball_winning_x_sum", "ball_winning_count",
    ]

    all_source_cols = list(per_match_cols) + ratio_source_cols
    for col in all_source_cols:
        if col not in p.columns:
            p[col] = 0.0
        p[col] = pd.to_numeric(p[col], errors="coerce").fillna(0.0)

    # Sum each team's player actions per match, then average across matches.
    team_match = (
        p.groupby(["league", "team_id", "match_id"])[list(per_match_cols)]
        .sum()
        .reset_index()
    )
    per_match = (
        team_match.groupby(["league", "team_id"])[list(per_match_cols)]
        .mean()
        .reset_index()
        .rename(columns=per_match_cols)
    )

    # Season-total ratios.
    totals = (
        p.groupby(["league", "team_id"])[ratio_source_cols].sum().reset_index()
    )
    totals["long_ball_share"] = (
        totals["long_balls"] / totals["total_passes"].replace(0, np.nan)
    )
    totals["forward_pass_pct"] = (
        totals["forward_passes"] / totals["total_passes"].replace(0, np.nan)
    )
    totals["aerial_win_rate"] = (
        totals["aerials_won"] / totals["aerials_total"].replace(0, np.nan)
    )
    totals["ball_winning_height"] = (
        totals["ball_winning_x_sum"] / totals["ball_winning_count"].replace(0, np.nan)
    )
    ratios = totals[[
        "league", "team_id",
        "long_ball_share", "forward_pass_pct", "aerial_win_rate", "ball_winning_height",
    ]]

    return per_match.merge(ratios, on=["league", "team_id"], how="outer")


# ─── Squad Profile ────────────────────────────────────────────────────

def compute_squad_profile(enriched: pd.DataFrame) -> pd.DataFrame:
    """
    Per-team squad profile from the merged player file, deduped to one row per
    (league, team_id, player_id) so a multi-group player counts once.

    squad_size, age_weighted (weighted by the player's summed minutes across
    their group rows), age_median, market_value_total_eur, market_value_median.
    Value columns are present-but-NaN when the non-enriched fallback is used.
    """
    df = enriched.copy()
    has_value = "market_value_eur" in df.columns
    has_age = "age" in df.columns

    minutes = pd.to_numeric(df.get("minutes_played", 0), errors="coerce").fillna(0.0)
    df["_minutes"] = minutes

    # Collapse group rows to one row per (league, team_id, player_id):
    # minutes summed across groups, age/value taken per player (first non-null).
    agg_spec = {"_minutes": ("_minutes", "sum")}
    if has_age:
        agg_spec["age"] = ("age", "first")
    if has_value:
        agg_spec["market_value_eur"] = ("market_value_eur", "first")
    per_player = (
        df.groupby(["league", "team_id", "player_id"]).agg(**agg_spec).reset_index()
    )

    rows: list[dict] = []
    for (league, team_id), grp in per_player.groupby(["league", "team_id"]):
        row = {
            "league": league,
            "team_id": team_id,
            "squad_size": grp["player_id"].nunique(),
        }
        if has_age:
            ages = pd.to_numeric(grp["age"], errors="coerce")
            wts = grp["_minutes"].where(ages.notna(), other=np.nan)
            valid = ages.notna() & wts.notna() & (wts > 0)
            if valid.any():
                row["age_weighted"] = float(
                    np.average(ages[valid], weights=wts[valid])
                )
            else:
                row["age_weighted"] = float(ages.mean()) if ages.notna().any() else np.nan
            row["age_median"] = float(ages.median()) if ages.notna().any() else np.nan
        else:
            row["age_weighted"] = np.nan
            row["age_median"] = np.nan

        if has_value:
            vals = pd.to_numeric(grp["market_value_eur"], errors="coerce")
            row["market_value_total_eur"] = (
                float(vals.sum()) if vals.notna().any() else np.nan
            )
            row["market_value_median_eur"] = (
                float(vals.median()) if vals.notna().any() else np.nan
            )
        else:
            row["market_value_total_eur"] = np.nan
            row["market_value_median_eur"] = np.nan
        rows.append(row)

    return pd.DataFrame(rows)


# ─── Team Ratings ─────────────────────────────────────────────────────

_RATING_GROUPS = ["DEF", "FB", "MID", "WING", "FW"]


def compute_team_ratings(
    enriched: pd.DataFrame, players: pd.DataFrame
) -> pd.DataFrame:
    """
    Minutes-weighted latent-z squad strength per team.

    Steps (per the SquadLens design):
      1. Rows with non-null overall_score → z = inv_cdf(clip(pct)/100).
      2. team_strength_z = sum(minutes * z) / sum(minutes) over the team's
         (player, group) rows. Minutes are group-scoped, so multi-group
         players are correctly weighted and never double-counted.
      3. team_rating = percentile rank of team_strength_z across ALL teams,
         scaled to 0-100 (the merge-style global rerank).
      4. global_rank / league_rank_rating by team_strength_z desc.
      5. rating_{GROUP}: minutes-weighted mean overall_score within that group,
         NaN when the group's summed minutes < TEAM_MIN_GROUP_MINUTES.
      6. qualified_players (unique player_ids), rating_coverage = enriched
         minutes / processed non-GK minutes (clipped to 1.0), and the
         low_coverage flag. Low-coverage teams are FLAGGED ONLY.
      7. perf_delta_rank = league_rank_points - league_rank_rating.
    """
    df = enriched.copy()
    df["_overall"] = pd.to_numeric(df.get(config.OVERALL_SCORE_COL), errors="coerce")
    df["_minutes"] = pd.to_numeric(df.get("minutes_played", 0), errors="coerce").fillna(0.0)

    inv_cdf = NormalDist().inv_cdf
    lo, hi = config.PCT_CLIP

    def _to_z(pct: float) -> float:
        if pd.isna(pct):
            return np.nan
        clipped = min(max(pct, lo), hi)
        return inv_cdf(clipped / 100.0)

    df["_z"] = df["_overall"].map(_to_z)

    scored = df[df["_z"].notna() & (df["_minutes"] > 0)].copy()

    # ── team_strength_z: minutes-weighted latent-z mean ──
    scored["_weighted_z"] = scored["_minutes"] * scored["_z"]
    strength = (
        scored.groupby(["league", "team_id"])
        .agg(_weighted_z=("_weighted_z", "sum"), _rating_minutes=("_minutes", "sum"))
        .reset_index()
    )
    strength[config.TEAM_STRENGTH_Z_COL] = (
        strength["_weighted_z"] / strength["_rating_minutes"].replace(0, np.nan)
    )
    strength = strength.drop(columns=["_weighted_z", "_rating_minutes"])

    # ── group sub-ratings (minutes-weighted mean overall_score) ──
    group_ratings = _compute_group_ratings(scored)
    strength = strength.merge(group_ratings, on=["league", "team_id"], how="left")

    # ── qualified players + enriched minutes per team ──
    qualified = (
        scored.groupby(["league", "team_id"])
        .agg(
            qualified_players=("player_id", "nunique"),
            _enriched_minutes=("_minutes", "sum"),
        )
        .reset_index()
    )
    strength = strength.merge(qualified, on=["league", "team_id"], how="left")

    # ── rating_coverage: enriched minutes / processed non-GK minutes ──
    coverage = _compute_coverage_denominator(players)
    strength = strength.merge(coverage, on=["league", "team_id"], how="left")
    denom = strength["_outfield_minutes"].replace(0, np.nan)
    strength["rating_coverage"] = (strength["_enriched_minutes"] / denom).clip(upper=1.0)
    strength["low_coverage"] = (
        (strength["rating_coverage"] < config.TEAM_MIN_COVERAGE)
        | (strength["qualified_players"] < config.TEAM_MIN_QUALIFIED_PLAYERS)
    )

    # ── team_rating (0-100 percentile rank across all teams) ──
    strength[config.TEAM_RATING_COL] = (
        strength[config.TEAM_STRENGTH_Z_COL].rank(pct=True) * 100
    )

    # ── global / league ranks by strength_z desc ──
    strength["global_rank"] = (
        strength[config.TEAM_STRENGTH_Z_COL]
        .rank(ascending=False, method="min")
        .astype("Int64")
    )
    strength["league_rank_rating"] = (
        strength.groupby("league")[config.TEAM_STRENGTH_Z_COL]
        .rank(ascending=False, method="min")
        .astype("Int64")
    )

    strength = strength.drop(columns=["_enriched_minutes", "_outfield_minutes"])
    return strength


def _compute_group_ratings(scored: pd.DataFrame) -> pd.DataFrame:
    """Minutes-weighted mean overall_score per (team, position group)."""
    group_col = config.POSITION_GROUP_COL
    records: dict[tuple, dict] = {}

    for (league, team_id, group), grp in scored.groupby(["league", "team_id", group_col]):
        if group not in _RATING_GROUPS:
            continue
        w = grp["_minutes"].to_numpy(dtype=float)
        vals = grp["_overall"].to_numpy(dtype=float)
        total = w.sum()
        key = (league, team_id)
        rec = records.setdefault(key, {"league": league, "team_id": team_id})
        if total >= config.TEAM_MIN_GROUP_MINUTES and total > 0:
            rec[f"rating_{group}"] = float(np.dot(w, vals) / total)
        else:
            rec[f"rating_{group}"] = np.nan

    frame = pd.DataFrame(list(records.values()))
    for group in _RATING_GROUPS:
        col = f"rating_{group}"
        if col not in frame.columns:
            frame[col] = np.nan
    if frame.empty:
        frame = pd.DataFrame(columns=["league", "team_id"] + [f"rating_{g}" for g in _RATING_GROUPS])
    return frame


def _compute_coverage_denominator(players: pd.DataFrame) -> pd.DataFrame:
    """
    Total processed minutes_played per team, excluding GK positions.

    This is the denominator of rating_coverage: the share of a team's outfield
    minutes that the merged (qualified) player pool actually accounts for.
    """
    p = players.copy()
    p["_minutes"] = pd.to_numeric(p.get("minutes_played", 0), errors="coerce").fillna(0.0)
    outfield = p[~p["position"].isin(config.GK_POSITIONS)]
    denom = (
        outfield.groupby(["league", "team_id"])["_minutes"]
        .sum()
        .rename("_outfield_minutes")
        .reset_index()
    )
    return denom


# ─── Club Elo (optional) ──────────────────────────────────────────────

# WhoScored team names vs ClubElo club names diverge for short/abbrev forms.
# Modeled on transfermarkt._WS_TEAM_ALIASES: map the WhoScored team_name to
# the ClubElo club string. Extend as unmatched names surface.
_WS_CLUBELO_ALIASES: dict[str, str] = {
    "AC Milan": "Milan",
    "Athletic Club": "Bilbao",
    "AZ Alkmaar": "Alkmaar",
    "AVS Futebol SAD": "AVS Futebol",
    "Borussia Dortmund": "Dortmund",
    "Man Utd": "Man United",
    "Man City": "Man City",
    "Wolves": "Wolves",
    "Newcastle": "Newcastle",
    "Nott'm Forest": "Forest",
    "Nottingham Forest": "Forest",
    "Sheff Utd": "Sheffield United",
    "Sheff Wed": "Sheffield Weds",
    "WBA": "West Brom",
    "QPR": "QPR",
    "PSG": "Paris SG",
    "RBL": "RB Leipzig",
    "FC Koln": "Koeln",
    "FC Heidenheim": "Heidenheim",
    "Borussia M.Gladbach": "Gladbach",
    "Eintracht Frankfurt": "Frankfurt",
    "Werder Bremen": "Werder",
    "Celta Vigo": "Celta",
    "Deportivo Alaves": "Alaves",
    "Real Betis": "Betis",
    "Real Oviedo": "Oviedo",
    "Real Sociedad": "Sociedad",
    "Casa Pia AC": "Casa Pia",
    "Estrela da Amadora": "Estrela Amadora",
    "Vitoria de Guimaraes": "Guimaraes",
    "FC Groningen": "Groningen",
    "FC Utrecht": "Utrecht",
    "FC Volendam": "Volendam",
    "Fortuna Sittard": "Sittard",
    "NAC Breda": "Breda",
    "NEC Nijmegen": "Nijmegen",
    "PEC Zwolle": "Zwolle",
    "PSV Eindhoven": "PSV",
    "SC Heerenveen": "Heerenveen",
    "Cercle Bruges": "Cercle Brugge",
    "Club Brugge": "Brugge",
    "FCV Dender EH": "Dender",
    "KV Mechelen": "Mechelen",
    "Royal Antwerp": "Antwerp",
    "Standard Liege": "Standard",
    "St.Truiden": "St Truiden",
    "Union St.Gilloise": "St Gillis",
    "Sporting Charleroi": "Charleroi",
    "OH Leuven": "Leuven",
    "RAAL La Louviere": "RAAL",
    "Fatih Karagumruk": "Fatih Karaguemruek",
    "Goztepe": "Goeztepe",
    "Istanbul Basaksehir": "Bueyueksehir",
    "Kayserispor": "Kayseri",
    "Parma Calcio 1913": "Parma",
}


def _normalize_club_name(name: str) -> str:
    """Casefold, strip diacritics, remove spaces/dots/hyphens for fuzzy match."""
    if not isinstance(name, str) or not name:
        return ""
    _PRE_SUB = {
        "ı": "i", "ø": "o", "Ø": "o", "ß": "ss",
        "æ": "ae", "Æ": "ae", "ł": "l", "Ł": "l",
    }
    for char, sub in _PRE_SUB.items():
        name = name.replace(char, sub)
    folded = unicodedata.normalize("NFD", name).encode("ascii", "ignore").decode("ascii")
    folded = folded.casefold()
    for ch in (" ", ".", "-", "'"):
        folded = folded.replace(ch, "")
    return folded


def _read_club_elos() -> pd.DataFrame | None:
    """Load the club Elo cache defensively: use the loader if importable, else
    read the CSV path directly; return None if unavailable."""
    if _load_club_elos is not None:
        try:
            return _load_club_elos()
        except Exception:  # pragma: no cover - defensive
            pass
    cache = config.DATA_ENRICHMENT / "clubelo_club_elo.csv"
    if cache.exists():
        return pd.read_csv(cache)
    return None


def attach_club_elo(df: pd.DataFrame) -> pd.DataFrame:
    """
    Attach an optional `club_elo` reference column, matched by team name.

    Matching: alias dict (_WS_CLUBELO_ALIASES) first, then a normalized-name
    fallback (casefold + diacritics folded + spaces/dots/hyphens removed).
    Unmatched teams get NaN and are listed in a single summary warning. If the
    cache is absent the column is omitted entirely with one warning line.
    """
    elos = _read_club_elos()
    if elos is None or elos.empty or "club" not in elos.columns or "elo" not in elos.columns:
        print("  [!] Club Elo cache unavailable — omitting the club_elo column.")
        return df

    # Build (league, normalized club) → elo lookup; team names can collide
    # across leagues, so the league key is part of the match.
    norm_lookup: dict[tuple[str, str], float] = {}
    for _, row in elos.iterrows():
        norm_lookup[(str(row["league"]), _normalize_club_name(str(row["club"])))] = row["elo"]

    def _match(row: pd.Series) -> float:
        league = str(row.get("league", ""))
        team_name = str(row.get("team_name", ""))
        alias = _WS_CLUBELO_ALIASES.get(team_name)
        if alias is not None:
            hit = norm_lookup.get((league, _normalize_club_name(alias)))
            if hit is not None:
                return hit
        return norm_lookup.get((league, _normalize_club_name(team_name)), np.nan)

    out = df.copy()
    out["club_elo"] = out.apply(_match, axis=1)

    unmatched = sorted(out.loc[out["club_elo"].isna(), "team_name"].astype(str).unique())
    if unmatched:
        print(
            f"  [!] {len(unmatched)} team(s) had no ClubElo match (club_elo=NaN): "
            f"{', '.join(unmatched)}"
        )
    return out


# ─── Orchestration ────────────────────────────────────────────────────

_IDENTITY_COLS = [
    "league", "team_id", "team_name",
    "competition_key", "competition_type", "competition_phase", "phase_table_scope",
]
_RESULTS_COLS = [
    "matches_played", "wins", "draws", "losses",
    "goals_for", "goals_against", "goal_diff", "points",
    "points_per_match", "league_rank_points",
    "home_matches", "home_wins", "home_draws", "home_losses",
    "home_goals_for", "home_goals_against", "home_points",
    "away_matches", "away_wins", "away_draws", "away_losses",
    "away_goals_for", "away_goals_against", "away_points",
]
_STYLE_COLS = [
    "possession_share", "pass_accuracy", "passes_per_match", "shots_per_match",
    "shots_conceded_per_match", "goals_per_match", "goals_conceded_per_match",
    "shot_conversion", "shot_conversion_against", "key_passes_per_match",
    "ppda_proxy",
    "progressive_passes_pm", "passes_into_final_third_pm", "long_balls_pm",
    "crosses_pm", "dribbles_pm", "aerials_won_pm", "ball_recoveries_pm",
    "possession_won_final_third_pm", "touches_final_third_pm",
    "penalty_area_touches_pm",
    "long_ball_share", "forward_pass_pct", "aerial_win_rate", "ball_winning_height",
]
_SQUAD_COLS = [
    "squad_size", "age_weighted", "age_median",
    "market_value_total_eur", "market_value_median_eur",
]
_RATING_COLS = [
    config.TEAM_STRENGTH_Z_COL, config.TEAM_RATING_COL,
    "global_rank", "league_rank_rating",
    "rating_DEF", "rating_FB", "rating_MID", "rating_WING", "rating_FW",
    "qualified_players", "rating_coverage", "low_coverage", "perf_delta_rank",
]


def _order_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Identity, results, style, squad, rating, then club_elo last."""
    ordered = list(_IDENTITY_COLS)
    for block in (_RESULTS_COLS, _STYLE_COLS, _SQUAD_COLS, _RATING_COLS):
        ordered.extend(c for c in block if c in df.columns)
    if "club_elo" in df.columns:
        ordered.append("club_elo")
    # Any stragglers keep their order at the end.
    ordered.extend(c for c in df.columns if c not in ordered)
    return df[ordered]


def _team_output_path(season: str, table_scope: str):
    if table_scope == config.TABLE_SCOPE_REGULAR:
        return config.get_teams_final_path(season)
    return config.DATA_FINAL / f"teams_{season}_{table_scope}.csv"


def run_team_features(
    season: str = config.SEASON,
    leagues: list[str] | None = None,
    table_scope: str = config.TABLE_SCOPE_REGULAR,
) -> pd.DataFrame:
    """Orchestrate all blocks, merge on (league, team_id, team_name), and write
    the team-analytics CSV plus the last_updated timestamp."""
    leagues = _resolve_leagues(leagues)
    print(f"Season: {season}  |  Leagues: {', '.join(leagues)}  |  Scope: {table_scope}\n")

    print("Loading processed per-match data...")
    matches, teams, players = load_processed(leagues, season)
    matches, teams, players = filter_to_table_scope(matches, teams, players, table_scope)
    print(
        f"  Scope filter kept {len(matches)} matches, "
        f"{len(teams)} team-matches, {len(players)} player-matches."
    )

    print("Loading merged player scores...")
    enriched, _has_values = _load_enriched_players(season)
    # Restrict the merged pool to the leagues we actually processed.
    if "league" in enriched.columns:
        enriched = enriched[enriched["league"].isin(set(matches["league"]))].copy()
    matches, teams, players = filter_processed_to_scored_team_pool(
        matches, teams, players, enriched
    )

    print("\nComputing results table...")
    results = compute_results_table(matches)
    if not results.empty:
        phase_lookup = (
            matches.groupby("league")
            .agg(
                competition_key=("competition_key", lambda s: s.mode().iloc[0] if not s.mode().empty else ""),
                competition_type=("competition_type", lambda s: s.mode().iloc[0] if not s.mode().empty else config.COMPETITION_TYPE_DOMESTIC),
                competition_phase=("competition_phase", lambda s: s.iloc[0] if s.nunique() == 1 else "multiple"),
            )
            .reset_index()
        )
        results = results.merge(phase_lookup, on="league", how="left")
        results["phase_table_scope"] = table_scope
    print("Computing style metrics...")
    style = compute_style_metrics(teams, players, matches)
    print("Computing squad profile...")
    squad = compute_squad_profile(enriched)
    print("Computing team ratings...")
    ratings = compute_team_ratings(enriched, players)

    # results carries the canonical (league, team_id, team_name) identity.
    df = results
    for block in (style, squad, ratings):
        keys = [k for k in ["league", "team_id"] if k in block.columns]
        df = df.merge(block, on=keys, how="left")

    # perf_delta_rank = points rank - rating rank.
    # Negative means results rank better than squad-quality rank (overperformance);
    # positive means results lag the squad-quality rank (underperformance).
    if "league_rank_rating" in df.columns and "league_rank_points" in df.columns:
        df["perf_delta_rank"] = (
            df["league_rank_points"] - df["league_rank_rating"]
        ).astype("Int64")

    print("Attaching club Elo (optional)...")
    df = attach_club_elo(df)

    df = _order_columns(df)
    df = df.sort_values(
        [config.TEAM_RATING_COL, "league", "team_name"],
        ascending=[False, True, True],
        na_position="last",
    ).reset_index(drop=True)

    output_path = _team_output_path(season, table_scope)
    config.DATA_FINAL.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"\nSaved → {output_path}")

    last_updated_path = config.DATA_FINAL / "last_updated.txt"
    last_updated_path.write_text(date.today().isoformat())
    print(f"Last updated timestamp saved → {last_updated_path}")

    _print_summary(df)
    return df


def _print_summary(df: pd.DataFrame) -> None:
    """Print n teams/leagues, top 5 by team_rating, and low-coverage flags."""
    n_leagues = df["league"].nunique() if "league" in df.columns else 0
    print(f"\n{'─'*60}")
    print(f"Team analytics: {len(df)} teams across {n_leagues} leagues")

    if config.TEAM_RATING_COL in df.columns:
        print("\nTop 5 by team_rating:")
        top = df.nlargest(5, config.TEAM_RATING_COL)
        for _, r in top.iterrows():
            print(
                f"  {r['team_name']:<26} {r['league']:<20} "
                f"rating={r[config.TEAM_RATING_COL]:.1f}"
            )

    if "low_coverage" in df.columns:
        flagged = df[df["low_coverage"] == True]  # noqa: E712 - pandas mask
        print(f"\nLow-coverage teams flagged: {len(flagged)}")
        for _, r in flagged.iterrows():
            cov = r.get("rating_coverage", np.nan)
            qp = r.get("qualified_players", np.nan)
            print(f"  {r['team_name']:<26} {r['league']:<20} "
                  f"coverage={cov:.2f} qualified={qp}")


def main():
    args = parse_arguments()
    run_team_features(season=args.season, leagues=args.league, table_scope=args.table_scope)


if __name__ == "__main__":
    main()
