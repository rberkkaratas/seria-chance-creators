"""
Midfielder Feature Engineering
-------------------------------------
Aggregates player-match stats into per-90 metrics, computes percentile
rankings, and builds a composite overall midfielder score.

Per-league run:
  - Reads data/processed/{league}/{season}/players.csv
  - Computes within-league percentile ranks → stored as {metric}_league_pct
  - Also writes these to {metric}_pct (the working column used by the app/roles)
  - Saves to data/final/{league}_{season}.csv

The future merge step (merge_leagues.py) will concat all league CSVs and
recompute {metric}_pct across the full 5-league pool (global percentiles),
leaving {metric}_league_pct intact for the within-league toggle.

Usage:
    python -m src.features.chance_creation --league Serie_A --season 2025-2026
    python -m src.features.chance_creation --league Premier_League --season 2025-2026
"""

import argparse
from datetime import date

import pandas as pd
import numpy as np

import config


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Feature engineering: per-90, percentiles, role scores"
    )
    parser.add_argument(
        "--league", default=config.LEAGUE,
        choices=list(config.LEAGUES.keys()) + ["all"],
        help="League key (default: %(default)s) or 'all' to run feature engineering for every "
             "league and then automatically merge into all_leagues_{season}.csv"
    )
    parser.add_argument(
        "--season", default=config.SEASON,
        help="Season string, e.g. 2025-2026 (default: %(default)s)"
    )
    return parser.parse_args()


def load_players(league: str, season: str) -> pd.DataFrame:
    """Load the processed players table for the given league/season."""
    path = config.get_processed_path(league, season) / "players.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"players.csv not found at {path}\n"
            f"Run build_tables first: python -m src.processing.build_tables "
            f"--league {league} --season {season}"
        )
    return pd.read_csv(path)


def filter_midfielders(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter for midfield/attacking positions and minimum minutes.
    """
    # Filter by position
    mask_position = df["position"].isin(config.POSITIONS)

    # Aggregate minutes only from midfield appearances (position-filtered rows)
    mid_minutes = (
        df[mask_position]
        .groupby("player_id")["minutes_played"]
        .sum()
    )
    qualified = mid_minutes[mid_minutes >= config.MIN_MINUTES_PLAYED].index

    mask_qualified = df["player_id"].isin(qualified)

    filtered = df[mask_position & mask_qualified].copy()
    print(f"Filtered to {filtered['player_id'].nunique()} players "
          f"({len(filtered)} appearances) from "
          f"{df['player_id'].nunique()} total.")
    return filtered


def aggregate_per_player(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate match-level stats to season-level per player.
    Returns one row per player with totals and metadata.
    """
    # Stats to sum across matches
    sum_cols = [
        "minutes_played", "total_passes", "accurate_passes",
        "key_passes", "through_balls", "long_balls_accurate",
        "assists", "second_assists",
        "progressive_passes", "progressive_carries",
        "passes_into_final_third", "passes_into_penalty_area",
        "successful_dribbles", "total_dribbles",
        "shots", "shots_on_target",
        "tackles", "tackles_successful",
        "interceptions", "ball_recoveries",
        "clearances", "aerials_won", "aerials_total", "shots_blocked",
        "crosses", "crosses_successful",
        "possession_lost",
        "touches", "touches_final_third",
        # New spatial metrics
        "forward_passes", "penalty_area_touches", "half_space_passes",
        "possession_won_final_third", "carries_into_final_third",
        "ball_winning_x_sum", "ball_winning_count",
    ]

    agg_dict = {col: "sum" for col in sum_cols if col in df.columns}
    agg_dict["match_id"] = "count"  # number of appearances

    agg = df.groupby("player_id").agg(agg_dict).reset_index()
    agg.rename(columns={"match_id": "appearances"}, inplace=True)

    # Add player metadata (name, team, age, position) from most recent appearance
    meta = (
        df.sort_values("match_id", ascending=False)
        .groupby("player_id")
        .first()[["player_name", "team_name", "team_id", "position", "age"]]
        .reset_index()
    )
    agg = agg.merge(meta, on="player_id", how="left")

    return agg


def compute_per_90(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-90-minute rates for all counting stats.
    """
    counting_cols = [
        "key_passes", "through_balls", "assists", "second_assists",
        "progressive_passes", "progressive_carries",
        "passes_into_final_third", "passes_into_penalty_area",
        "successful_dribbles", "total_dribbles",
        "shots", "shots_on_target",
        "tackles", "tackles_successful",
        "interceptions", "ball_recoveries",
        "clearances", "aerials_won", "aerials_total", "shots_blocked",
        "crosses", "crosses_successful",
        "possession_lost",
        "touches", "touches_final_third",
        "total_passes", "accurate_passes",
        # New spatial metrics
        "penalty_area_touches", "half_space_passes",
        "possession_won_final_third", "carries_into_final_third",
        "forward_passes",
    ]

    minutes = df["minutes_played"].replace(0, np.nan)
    for col in counting_cols:
        if col in df.columns:
            df[f"{col}_p90"] = (df[col] / minutes) * 90

    # Derived metrics
    if "total_passes" in df.columns and "accurate_passes" in df.columns:
        df["pass_accuracy"] = (
            df["accurate_passes"] / df["total_passes"].replace(0, np.nan)
        ) * 100

    if "successful_dribbles" in df.columns and "total_dribbles" in df.columns:
        df["dribble_success_rate"] = (
            df["successful_dribbles"] / df["total_dribbles"].replace(0, np.nan)
        ) * 100

    # Aerial win rate
    if "aerials_won" in df.columns and "aerials_total" in df.columns:
        df["aerial_win_rate"] = (
            df["aerials_won"] / df["aerials_total"].replace(0, np.nan)
        ) * 100

    # Tackle success rate
    if "tackles_successful" in df.columns and "tackles" in df.columns:
        df["tackle_success_rate"] = (
            df["tackles_successful"] / df["tackles"].replace(0, np.nan)
        ) * 100

    # Cross accuracy
    if "crosses_successful" in df.columns and "crosses" in df.columns:
        df["cross_accuracy"] = (
            df["crosses_successful"] / df["crosses"].replace(0, np.nan)
        ) * 100

    # Possession won (derived: ball recoveries + successful tackles + interceptions)
    poss_won_cols = [c for c in ["ball_recoveries", "tackles_successful", "interceptions"] if c in df.columns]
    if poss_won_cols:
        df["possession_won"] = df[poss_won_cols].sum(axis=1)
        df["possession_won_p90"] = (df["possession_won"] / minutes) * 90

    # Forward pass percentage
    if "forward_passes" in df.columns and "total_passes" in df.columns:
        df["forward_pass_pct"] = (
            df["forward_passes"] / df["total_passes"].replace(0, np.nan)
        ) * 100

    # Ball-winning height: average x-coordinate of interceptions + ball recoveries
    # Higher value = wins the ball higher up the pitch (0–100 scale)
    if "ball_winning_x_sum" in df.columns and "ball_winning_count" in df.columns:
        df["ball_winning_height"] = (
            df["ball_winning_x_sum"] / df["ball_winning_count"].replace(0, np.nan)
        )

    # Shot-Creating Actions proxy (key passes + successful dribbles)
    # Adjust if you can derive a more precise SCA from event data
    if "key_passes_p90" in df.columns and "successful_dribbles_p90" in df.columns:
        df["shot_creating_actions_p90"] = (
            df["key_passes_p90"] + df["successful_dribbles_p90"]
        )

    # Defensive actions per 90 — combined volume of tackles and interceptions.
    # Used as the primary metric in the Box-to-Box role to reward balanced midfielders.
    if "tackles_p90" in df.columns and "interceptions_p90" in df.columns:
        df["def_actions_p90"] = df["tackles_p90"] + df["interceptions_p90"]

    # Direct creation per 90 — key passes + assists (passes that directly lead to a shot or goal).
    if "key_passes_p90" in df.columns and "assists_p90" in df.columns:
        df["direct_creation_p90"] = df["key_passes_p90"] + df["assists_p90"]

    return df


def compute_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute within-league percentile ranks (0-100) for all role metrics.

    Writes two columns per metric:
      {metric}_league_pct  — rank within this league (permanent)
      {metric}_pct         — working column used by role scoring and the app.
                             Starts as a copy of _league_pct.
                             The future merge_leagues step overwrites _pct with
                             global (cross-league) ranks without touching _league_pct.
    """
    all_metrics = set(config.CHANCE_CREATION_METRICS)
    for weights in config.ROLE_WEIGHTS.values():
        all_metrics.update(weights.keys())

    for metric in all_metrics:
        if metric in df.columns:
            league_rank = df[metric].rank(pct=True) * 100
            df[f"{metric}_league_pct"] = league_rank
            df[f"{metric}_pct"] = league_rank  # overwritten by merge step for global mode

    return df


def compute_role_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute a 0–100 score for each of the 6 midfielder roles and assign
    primary_role (the role with the highest score) to each player.
    """
    score_cols = []
    for role_name, weights in config.ROLE_WEIGHTS.items():
        col = f"{config.ROLE_SCORE_COL_PREFIX}{role_name}"
        score = pd.Series(0.0, index=df.index)
        total_weight = 0.0
        for metric, weight in weights.items():
            pct_col = f"{metric}_pct"
            if pct_col in df.columns:
                score += df[pct_col].fillna(0) * weight
                total_weight += weight
        # Rescale if any metric was missing
        if 0 < total_weight < 1.0:
            score = score / total_weight
        df[col] = score.round(1)
        score_cols.append(col)

    if score_cols:
        df[config.PRIMARY_ROLE_COL] = (
            df[score_cols]
            .idxmax(axis=1)
            .str.replace(config.ROLE_SCORE_COL_PREFIX, "", regex=False)
        )

    return df


def compute_composite_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build weighted composite chance-creation score from role scores.
    COMPOSITE_WEIGHTS maps role name → weight (sums to 1.0).
    Must be called AFTER compute_role_scores().
    """
    score = pd.Series(0.0, index=df.index)
    total_weight = 0.0

    for role_name, weight in config.COMPOSITE_WEIGHTS.items():
        col = f"{config.ROLE_SCORE_COL_PREFIX}{role_name}"
        if col in df.columns:
            score += df[col] * weight
            total_weight += weight

    # Rescale if any role column was missing
    if 0 < total_weight < 1.0:
        score = score / total_weight

    df["chance_creation_score"] = score.round(1)
    return df


def run_feature_engineering(league: str = config.LEAGUE, season: str = config.SEASON):
    """
    Full feature engineering pipeline for a single league/season.
    Percentiles are within-league. The merge step produces global percentiles.
    """
    print(f"League: {league}  Season: {season}")

    print("Loading player data...")
    df = load_players(league, season)

    print("Filtering midfielders...")
    df = filter_midfielders(df)

    print("Aggregating per player...")
    df = aggregate_per_player(df)

    # Ensure league column is present (comes from players.csv; add as fallback)
    if "league" not in df.columns:
        df["league"] = league

    print("Computing per-90 metrics...")
    df = compute_per_90(df)

    print("Computing within-league percentile rankings...")
    df = compute_percentiles(df)

    print("Computing role scores...")
    df = compute_role_scores(df)

    print("Computing composite scores...")
    df = compute_composite_score(df)

    df = df.sort_values("chance_creation_score", ascending=False)

    # Save per-league final file
    config.DATA_FINAL.mkdir(parents=True, exist_ok=True)
    output_path = config.get_final_path(league, season)
    df.to_csv(output_path, index=False)

    # Also maintain backward-compatible chance_creators.csv for Serie A
    if league == "Serie_A" and season == config.SEASON:
        compat_path = config.DATA_FINAL / "chance_creators.csv"
        df.to_csv(compat_path, index=False)
        print(f"  (also saved to {compat_path} for backward compatibility)")

    last_updated_path = config.DATA_FINAL / "last_updated.txt"
    last_updated_path.write_text(date.today().isoformat())
    print(f"Last updated timestamp saved → {last_updated_path}")

    print(f"\nSaved to {output_path}")
    print(f"Top 10 by composite score:")
    display_cols = [c for c in ["player_name", "team_name", "age", "minutes_played",
                                "chance_creation_score"] if c in df.columns]
    print(df[display_cols].head(10).to_string(index=False))


if __name__ == "__main__":
    args = parse_arguments()
    if args.league == "all":
        from src.features.merge_leagues import run_merge
        leagues = list(config.LEAGUES.keys())
        print(f"Running feature engineering for all {len(leagues)} leagues: {', '.join(leagues)}\n")
        succeeded = []
        for league in leagues:
            try:
                run_feature_engineering(league=league, season=args.season)
                succeeded.append(league)
                print()
            except Exception as e:
                print(f"  [!] {league} failed: {e}\n")
        if succeeded:
            print(f"Merging {len(succeeded)} league(s) into all_leagues_{args.season}.csv ...")
            run_merge(season=args.season, leagues=succeeded)
        print("All done.")
    else:
        run_feature_engineering(league=args.league, season=args.season)
