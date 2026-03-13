"""
Chance Creation Feature Engineering
-------------------------------------
Aggregates player-match stats into per-90 metrics, computes percentile
rankings, and builds a composite chance-creation score.

Usage:
    python -m src.features.chance_creation
"""

import pandas as pd
import numpy as np

import config


def load_players() -> pd.DataFrame:
    """Load the processed players table."""
    return pd.read_csv(config.DATA_PROCESSED / "players.csv")


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

    return df


def compute_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute percentile rank (0-100) for all metrics used in chance-creation
    scoring and role scoring.
    """
    # Core chance-creation metrics (existing)
    all_metrics = set(config.CHANCE_CREATION_METRICS)

    # Add every metric referenced by any role definition
    for weights in config.ROLE_WEIGHTS.values():
        all_metrics.update(weights.keys())

    for metric in all_metrics:
        if metric in df.columns:
            df[f"{metric}_pct"] = df[metric].rank(pct=True) * 100

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
    Build weighted composite chance-creation score from percentile ranks.
    """
    score = pd.Series(0.0, index=df.index)

    for metric, weight in config.COMPOSITE_WEIGHTS.items():
        pct_col = f"{metric}_pct"
        if pct_col in df.columns:
            score += df[pct_col] * weight

    df["chance_creation_score"] = score.round(1)
    return df


def run_feature_engineering():
    """
    Full feature engineering pipeline.
    """
    print("Loading player data...")
    df = load_players()

    print("Filtering midfielders...")
    df = filter_midfielders(df)

    print("Aggregating per player...")
    df = aggregate_per_player(df)

    print("Computing per-90 metrics...")
    df = compute_per_90(df)

    print("Computing percentile rankings...")
    df = compute_percentiles(df)

    print("Computing composite scores...")
    df = compute_composite_score(df)

    print("Computing role scores...")
    df = compute_role_scores(df)

    # Sort by composite score
    df = df.sort_values("chance_creation_score", ascending=False)

    # Save
    config.DATA_FINAL.mkdir(parents=True, exist_ok=True)
    output_path = config.DATA_FINAL / "chance_creators.csv"
    df.to_csv(output_path, index=False)

    print(f"\nSaved to {output_path}")
    print(f"Top 10 chance creators:")
    print(
        df[["player_name", "team_name", "age", "minutes_played",
            "chance_creation_score"]].head(10).to_string(index=False)
    )


if __name__ == "__main__":
    run_feature_engineering()
