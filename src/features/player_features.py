"""
Player Feature Engineering
--------------------------
Aggregates player-match stats into per-90 metrics, computes position-group
percentile ranks, assigns tactical role scores, and writes per-league outputs.

Per-league run:
  - Reads data/processed/{league}/{season}/players.csv
  - Emits one row per (player_id, position_group) when the player reaches the
    group-specific inclusion threshold
  - Computes usage confidence from minutes, appearances, starts, and start rate
  - Computes sample-adjusted {metric}_league_pct within league x position group
  - Copies those ranks to {metric}_pct for role scoring and dashboard defaults
  - Saves data/final/{league}_{season}.csv

The merge step recomputes {metric}_pct within the global position-group pool
while preserving {metric}_league_pct for within-league mode.

Usage:
    python -m src.features.player_features --league all --season 2025-2026
    python -m src.features.player_features --league Serie_A --season 2025-2026
"""

from __future__ import annotations

import argparse
from datetime import date

import numpy as np
import pandas as pd

import config


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Feature engineering: per-90, group percentiles, role scores"
    )
    parser.add_argument(
        "--league",
        default=config.LEAGUE,
        choices=list(config.LEAGUES.keys()) + ["all"],
        help=(
            "League key (default: %(default)s) or 'all' to run feature engineering "
            "for every league and then automatically merge into all_leagues_{season}.csv"
        ),
    )
    parser.add_argument(
        "--season",
        default=config.SEASON,
        help="Season string, e.g. 2025-2026 (default: %(default)s)",
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


def load_opponent_possession(league: str, season: str) -> pd.DataFrame | None:
    """
    Per (match_id, team_id) opponent possession share, proxied by pass counts
    from teams.csv. Returns None when the file or columns are unavailable so
    the pipeline degrades to unadjusted ranking.
    """
    path = config.get_processed_path(league, season) / "teams.csv"
    if not path.exists():
        return None
    teams = pd.read_csv(path)
    if not {"match_id", "team_id", "total_passes"}.issubset(teams.columns):
        return None

    match_totals = teams.groupby("match_id")["total_passes"].transform("sum")
    opp_share = (match_totals - teams["total_passes"]) / match_totals.replace(0, np.nan)
    return pd.DataFrame({
        "match_id": teams["match_id"],
        "team_id": teams["team_id"],
        config.PADJ_OPPONENT_SHARE_COL: opp_share,
    })


def group_metrics(group: str) -> list[str]:
    """Return all raw/rate metrics that need percentile columns for a group."""
    group_cfg = config.POSITION_GROUPS[group]
    metrics: list[str] = []
    for metric in group_cfg["radar_metrics"]:
        if metric not in metrics:
            metrics.append(metric)
    for weights in group_cfg["roles"].values():
        for metric in weights:
            if metric not in metrics:
                metrics.append(metric)
    return metrics


def filter_position_group(df: pd.DataFrame, group: str) -> pd.DataFrame:
    """
    Filter to rows in a position group and players with enough minutes to be
    visible in that same group. Minutes outside the group do not count.
    """
    if group not in config.POSITION_GROUPS:
        raise KeyError(f"Unknown position group: {group}")

    positions = config.POSITION_GROUPS[group]["positions"]
    mask_position = df["position"].isin(positions)

    group_minutes = (
        df[mask_position]
        .groupby("player_id")["minutes_played"]
        .sum()
    )
    qualified = group_minutes[group_minutes >= config.MIN_MINUTES_INCLUDED].index
    filtered = df[mask_position & df["player_id"].isin(qualified)].copy()
    filtered[config.POSITION_GROUP_COL] = group

    print(
        f"  {group}: {filtered['player_id'].nunique()} included players "
        f"({len(filtered)} appearances)"
    )
    return filtered


def resolve_substitute_positions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replace WhoScored's generic "Sub" position with a player's primary
    outfield position inferred from their non-sub appearances in the same
    league-season.

    WhoScored metadata labels substitutes as "Sub", not as their tactical
    position. If left unchanged, substitute appearances are dropped by the
    position-group filter, which makes appearances equal starts for every
    player. We only infer from known outfield positions; sub-only players stay
    unresolved rather than being assigned to an unreliable group.
    """
    if "position" not in df.columns or "player_id" not in df.columns:
        return df

    outfield_positions = set(config.POSITION_TO_GROUP)
    known_positions = df[df["position"].isin(outfield_positions)].copy()
    if known_positions.empty:
        return df

    if "minutes_played" in known_positions.columns:
        known_positions["_position_weight"] = pd.to_numeric(
            known_positions["minutes_played"], errors="coerce"
        ).fillna(0)
    else:
        known_positions["_position_weight"] = 1

    primary_positions = (
        known_positions
        .groupby(["player_id", "position"], as_index=False)["_position_weight"]
        .sum()
        .sort_values(
            ["player_id", "_position_weight", "position"],
            ascending=[True, False, True],
        )
        .drop_duplicates("player_id")
        .set_index("player_id")["position"]
    )

    resolved = df.copy()
    sub_mask = resolved["position"].eq("Sub")
    inferred_positions = resolved.loc[sub_mask, "player_id"].map(primary_positions)
    resolvable_mask = sub_mask & inferred_positions.notna()
    resolved.loc[resolvable_mask, "position"] = inferred_positions[resolvable_mask]

    if sub_mask.any():
        print(
            "  Substitute position inference: "
            f"{int(resolvable_mask.sum())} appearances resolved, "
            f"{int((sub_mask & ~resolvable_mask).sum())} left as Sub"
        )

    return resolved


def aggregate_per_player(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate match-level stats to season-level per player within one position
    group. Returns one row per player.
    """
    sum_cols = [
        "minutes_played",
        "total_passes",
        "accurate_passes",
        "key_passes",
        "through_balls",
        "long_balls",
        "assists",
        "second_assists",
        "shot_creating_actions",
        "progressive_passes",
        "passes_into_final_third",
        "passes_into_penalty_area",
        "successful_dribbles",
        "total_dribbles",
        "shots",
        "shots_on_target",
        "goals",
        "tackles",
        "tackles_successful",
        "interceptions",
        "ball_recoveries",
        "clearances",
        "aerials_won",
        "aerials_total",
        "shots_blocked",
        "crosses",
        "crosses_successful",
        "possession_lost",
        "touches",
        "touches_final_third",
        "forward_passes",
        "penalty_area_touches",
        "half_space_passes",
        "possession_won_final_third",
        "carries_into_final_third",
        "ball_winning_x_sum",
        "ball_winning_count",
    ]

    agg_dict = {col: "sum" for col in sum_cols if col in df.columns}
    agg_dict["match_id"] = "count"

    opp_share_col = config.PADJ_OPPONENT_SHARE_COL
    if opp_share_col in df.columns:
        df = df.copy()
        df["_opp_share_x_minutes"] = (
            pd.to_numeric(df[opp_share_col], errors="coerce")
            * df["minutes_played"]
        )
        agg_dict["_opp_share_x_minutes"] = "sum"

    if "isFirstEleven" in df.columns:
        df = df.copy()
        df["isFirstEleven"] = (
            df["isFirstEleven"]
            .astype("string")
            .fillna("false")
            .map(lambda v: str(v).strip().lower() in {"true", "1", "1.0", "yes"})
        )
        agg_dict["isFirstEleven"] = "sum"

    agg = df.groupby("player_id").agg(agg_dict).reset_index()
    agg.rename(columns={"match_id": "appearances"}, inplace=True)
    if "_opp_share_x_minutes" in agg.columns:
        agg[config.PADJ_OPPONENT_SHARE_COL] = (
            agg["_opp_share_x_minutes"]
            / agg["minutes_played"].replace(0, np.nan)
        )
        agg.drop(columns=["_opp_share_x_minutes"], inplace=True)
    if "isFirstEleven" in agg.columns:
        agg.rename(columns={"isFirstEleven": "starts"}, inplace=True)
    else:
        agg["starts"] = 0

    meta_cols = [
        "player_name",
        "team_name",
        "team_id",
        "position",
        "age",
        "league",
        config.POSITION_GROUP_COL,
    ]
    available_meta_cols = [col for col in meta_cols if col in df.columns]
    meta = (
        df.sort_values("match_id", ascending=False)
        .groupby("player_id")
        .first()[available_meta_cols]
        .reset_index()
    )
    return agg.merge(meta, on="player_id", how="left")


def compute_sample_reliability(df: pd.DataFrame) -> pd.DataFrame:
    """
    Estimate how trustworthy a player's scores are from usage volume.

    600 minutes is no longer a hard inclusion gate. It is the point where the
    minutes component reaches full confidence. Starts and appearances add
    context so a 540-minute regular starter is treated more reliably than a
    540-minute bench-only profile, while both remain visible.
    """
    def _numeric_col(name: str) -> pd.Series:
        if name not in df.columns:
            return pd.Series(0, index=df.index, dtype=float)
        return pd.to_numeric(df[name], errors="coerce").fillna(0)

    minutes = _numeric_col("minutes_played")
    appearances = _numeric_col("appearances")
    starts = _numeric_col("starts")

    min_mins = float(config.MIN_MINUTES_INCLUDED)
    full_mins = float(config.FULL_SAMPLE_MINUTES)
    minutes_span = max(full_mins - min_mins, 1.0)

    minutes_component = ((minutes - min_mins) / minutes_span).clip(0, 1)
    appearances_component = (appearances / config.FULL_SAMPLE_APPEARANCES).clip(0, 1)
    starts_component = (starts / config.FULL_SAMPLE_STARTS).clip(0, 1)
    start_rate = (starts / appearances.replace(0, np.nan)).fillna(0).clip(0, 1)

    weights = config.SAMPLE_RELIABILITY_WEIGHTS
    reliability = (
        minutes_component * weights["minutes"]
        + appearances_component * weights["appearances"]
        + starts_component * weights["starts"]
        + start_rate * weights["start_rate"]
    ).clip(0, 1)

    df["starts"] = starts.astype(int)
    df["minutes_per_appearance"] = (
        minutes / appearances.replace(0, np.nan)
    ).fillna(0).round(1)
    df["ninety_equivalents"] = (minutes / 90).round(1)
    df["start_rate"] = (start_rate * 100).round(1)
    df[config.SAMPLE_RELIABILITY_COL] = reliability.round(4)
    df[config.SCORE_CONFIDENCE_COL] = (reliability * 100).round(1)
    df["is_full_sample"] = minutes >= config.FULL_SAMPLE_MINUTES

    tier = np.select(
        [
            (minutes >= config.FULL_SAMPLE_MINUTES) & (reliability >= 0.75),
            (minutes >= 360) | (reliability >= 0.45),
        ],
        ["Full sample", "Rotation sample"],
        default="Limited sample",
    )
    df[config.SAMPLE_TIER_COL] = tier
    return df


def compute_per_90(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-90-minute rates and rate stats for all available columns."""
    counting_cols = [
        "key_passes",
        "through_balls",
        "long_balls",
        "assists",
        "second_assists",
        "shot_creating_actions",
        "progressive_passes",
        "passes_into_final_third",
        "passes_into_penalty_area",
        "successful_dribbles",
        "total_dribbles",
        "shots",
        "shots_on_target",
        "goals",
        "tackles",
        "tackles_successful",
        "interceptions",
        "ball_recoveries",
        "clearances",
        "aerials_won",
        "aerials_total",
        "shots_blocked",
        "crosses",
        "crosses_successful",
        "possession_lost",
        "touches",
        "touches_final_third",
        "total_passes",
        "accurate_passes",
        "penalty_area_touches",
        "half_space_passes",
        "possession_won_final_third",
        "carries_into_final_third",
        "forward_passes",
    ]

    minutes = df["minutes_played"].replace(0, np.nan)
    for col in counting_cols:
        if col in df.columns:
            df[f"{col}_p90"] = (df[col] / minutes) * 90

    if "total_passes" in df.columns and "accurate_passes" in df.columns:
        df["pass_accuracy"] = (
            df["accurate_passes"] / df["total_passes"].replace(0, np.nan)
        ) * 100

    if "successful_dribbles" in df.columns and "total_dribbles" in df.columns:
        df["dribble_success_rate"] = (
            df["successful_dribbles"] / df["total_dribbles"].replace(0, np.nan)
        ) * 100

    if "aerials_won" in df.columns and "aerials_total" in df.columns:
        df["aerial_win_rate"] = (
            df["aerials_won"] / df["aerials_total"].replace(0, np.nan)
        ) * 100

    if "tackles_successful" in df.columns and "tackles" in df.columns:
        df["tackle_success_rate"] = (
            df["tackles_successful"] / df["tackles"].replace(0, np.nan)
        ) * 100

    if "crosses_successful" in df.columns and "crosses" in df.columns:
        df["cross_accuracy"] = (
            df["crosses_successful"] / df["crosses"].replace(0, np.nan)
        ) * 100

    poss_won_cols = [
        col for col in ["ball_recoveries", "tackles_successful", "interceptions"]
        if col in df.columns
    ]
    if poss_won_cols:
        df["possession_won"] = df[poss_won_cols].sum(axis=1)
        df["possession_won_p90"] = (df["possession_won"] / minutes) * 90

    if "forward_passes" in df.columns and "total_passes" in df.columns:
        df["forward_pass_pct"] = (
            df["forward_passes"] / df["total_passes"].replace(0, np.nan)
        ) * 100

    if "ball_winning_x_sum" in df.columns and "ball_winning_count" in df.columns:
        df["ball_winning_height"] = (
            df["ball_winning_x_sum"] / df["ball_winning_count"].replace(0, np.nan)
        )

    if "shot_creating_actions_p90" not in df.columns:
        if "key_passes_p90" in df.columns and "successful_dribbles_p90" in df.columns:
            df["shot_creating_actions_p90"] = (
                df["key_passes_p90"] + df["successful_dribbles_p90"]
            )

    if "tackles_p90" in df.columns and "interceptions_p90" in df.columns:
        df["def_actions_p90"] = df["tackles_p90"] + df["interceptions_p90"]

    if "key_passes_p90" in df.columns and "assists_p90" in df.columns:
        df["direct_creation_p90"] = df["key_passes_p90"] + df["assists_p90"]

    return df


def sample_adjusted_metric(
    df: pd.DataFrame, metric: str, group: str | None = None
) -> pd.Series:
    """
    Shrink a metric toward the group median before percentile ranking when the
    player's sample is thin. This keeps low-minute outliers visible without
    letting a tiny sample dominate role scores.

    Rate metrics listed in config.RATE_SHRINKAGE are instead shrunk toward the
    pool-average rate by their contest count (e.g. aerial duels), which is the
    correct sample measure for a rate — a high-minute player with few contests
    is still a thin sample. Displayed raw rate columns are left untouched.

    When `group` is given, metrics listed in config.PADJ_METRICS for that group
    are possession-adjusted first: scaled to a 50% opponent-possession baseline
    so defenders on dominant sides are ranked per defensive opportunity, not
    per minute.
    """
    shrink_spec = config.RATE_SHRINKAGE.get(metric)
    if shrink_spec is not None:
        successes_col = shrink_spec["successes"]
        attempts_col = shrink_spec["attempts"]
        if successes_col in df.columns and attempts_col in df.columns:
            successes = pd.to_numeric(df[successes_col], errors="coerce").fillna(0)
            attempts = pd.to_numeric(df[attempts_col], errors="coerce").fillna(0)
            k = float(shrink_spec["prior_strength"])
            total_attempts = attempts.sum()
            prior_rate = successes.sum() / total_attempts if total_attempts > 0 else 0.5
            return (successes + k * prior_rate) / (attempts + k) * 100

    values = pd.to_numeric(df[metric], errors="coerce")

    if (
        group is not None
        and metric in config.PADJ_METRICS.get(group, ())
        and config.PADJ_OPPONENT_SHARE_COL in df.columns
    ):
        lo, hi = config.PADJ_OPP_SHARE_CLIP
        opp_share = (
            pd.to_numeric(df[config.PADJ_OPPONENT_SHARE_COL], errors="coerce")
            .clip(lo, hi)
        )
        values = values * (config.PADJ_BASELINE / opp_share).fillna(1.0)
    if config.SAMPLE_RELIABILITY_COL not in df.columns:
        return values

    median = values.median(skipna=True)
    if pd.isna(median):
        return values

    reliability = (
        pd.to_numeric(df[config.SAMPLE_RELIABILITY_COL], errors="coerce")
        .fillna(1.0)
        .clip(0, 1)
    )
    return median + reliability * (values - median)


def compute_percentiles(df: pd.DataFrame, group: str) -> pd.DataFrame:
    """
    Compute within-league, within-position-group percentile ranks for all group
    role/radar metrics.
    """
    for metric in group_metrics(group):
        if metric in df.columns:
            rank_source = sample_adjusted_metric(df, metric, group=group)
            league_rank = rank_source.rank(pct=True) * 100
            df[f"{metric}_league_pct"] = league_rank
            df[f"{metric}_pct"] = league_rank
    return df


def adjust_score_for_sample(score: pd.Series, df: pd.DataFrame) -> pd.Series:
    """Pull low-confidence scores toward the neutral 50-point baseline."""
    if config.SAMPLE_RELIABILITY_COL not in df.columns:
        return score

    reliability = (
        pd.to_numeric(df[config.SAMPLE_RELIABILITY_COL], errors="coerce")
        .fillna(1.0)
        .clip(0, 1)
    )
    neutral = float(config.SCORE_NEUTRAL_POINT)
    return neutral + reliability * (score - neutral)


def compute_role_scores(df: pd.DataFrame, group: str) -> pd.DataFrame:
    """Compute role scores and primary_role for one position group."""
    df = df.copy()
    roles = config.POSITION_GROUPS[group]["roles"]
    score_cols = []

    for role_name, weights in roles.items():
        col = f"{config.ROLE_SCORE_COL_PREFIX}{role_name}"
        score = pd.Series(0.0, index=df.index)
        total_weight = 0.0
        for metric, weight in weights.items():
            pct_col = f"{metric}_pct"
            if pct_col in df.columns:
                score += df[pct_col].fillna(0) * weight
                total_weight += weight
        if 0 < total_weight < 1.0:
            score = score / total_weight
        df[col] = adjust_score_for_sample(score, df).round(1)
        score_cols.append(col)

    if score_cols:
        df[config.PRIMARY_ROLE_COL] = (
            df[score_cols]
            .idxmax(axis=1)
            .str.replace(config.ROLE_SCORE_COL_PREFIX, "", regex=False)
        )

    return df


def compute_overall_score(df: pd.DataFrame, group: str) -> pd.DataFrame:
    """
    Build group-specific overall_score from that group's role scores.

    Role scores are z-standardized within the pool before the composite
    weights are applied, so a role whose score distribution is wider (e.g. few
    correlated metrics) cannot exert more influence than its nominal weight.
    The weighted composite is then percentile-ranked back to 0-100 within the
    pool, matching the pipeline's percentile conventions and avoiding the
    range compression a plain average of near-independent scores produces.

    Pools too small to standardize (fewer than MIN_RANK_POOL rows) fall back
    to the plain weighted average of raw role scores.
    """
    MIN_RANK_POOL = 5

    df = df.copy()
    group_cfg = config.POSITION_GROUPS[group]
    default_weights = group_cfg["composite_weights"]
    position_weights = group_cfg.get("position_composite_weights", {})

    role_cols = {
        role_name: f"{config.ROLE_SCORE_COL_PREFIX}{role_name}"
        for role_name in group_cfg["roles"]
        if f"{config.ROLE_SCORE_COL_PREFIX}{role_name}" in df.columns
    }

    standardized: dict[str, pd.Series] = {}
    if len(df) >= MIN_RANK_POOL:
        for role_name, col in role_cols.items():
            values = pd.to_numeric(df[col], errors="coerce")
            std = values.std()
            if pd.notna(std) and std > 0:
                standardized[col] = (values - values.mean()) / std
            else:
                standardized[col] = pd.Series(0.0, index=df.index)

    def _row_score(row: pd.Series) -> float:
        weights = position_weights.get(row.get("position"), default_weights)
        score = 0.0
        total_weight = 0.0

        for role_name, weight in weights.items():
            col = f"{config.ROLE_SCORE_COL_PREFIX}{role_name}"
            if col in row and pd.notna(row[col]):
                if standardized:
                    score += float(standardized[col].loc[row.name]) * weight
                else:
                    score += float(row[col]) * weight
                total_weight += weight

        if 0 < total_weight < 1.0:
            score = score / total_weight
        return score

    composite = df.apply(_row_score, axis=1)
    if standardized:
        composite = composite.rank(pct=True) * 100
    df[config.OVERALL_SCORE_COL] = composite.round(1)
    return df


def build_group_features(players: pd.DataFrame, group: str, league: str) -> pd.DataFrame:
    """Run the full feature pipeline for one position group in one league."""
    group_df = filter_position_group(players, group)
    if group_df.empty:
        return pd.DataFrame()

    group_df = aggregate_per_player(group_df)
    if "league" not in group_df.columns:
        group_df["league"] = league
    group_df[config.POSITION_GROUP_COL] = group

    group_df = compute_sample_reliability(group_df)
    group_df = compute_per_90(group_df)
    group_df = compute_percentiles(group_df, group)
    group_df = compute_role_scores(group_df, group)
    group_df = compute_overall_score(group_df, group)
    return group_df


def run_feature_engineering(league: str = config.LEAGUE, season: str = config.SEASON):
    """
    Full feature engineering pipeline for a single league/season.
    Percentiles are within league x position group. The merge step produces
    global x position group percentiles.
    """
    print(f"League: {league}  Season: {season}")
    print("Loading player data...")
    players = load_players(league, season)
    players = resolve_substitute_positions(players)

    opponent_possession = load_opponent_possession(league, season)
    if opponent_possession is not None:
        players = players.merge(
            opponent_possession, on=["match_id", "team_id"], how="left"
        )
        print("Attached per-match opponent possession share (PAdj).")
    else:
        print("teams.csv unavailable — skipping possession adjustment.")

    print("Building position-group features...")
    group_frames = []
    for group in config.POSITION_GROUPS:
        frame = build_group_features(players, group, league)
        if not frame.empty:
            group_frames.append(frame)

    if not group_frames:
        raise ValueError(f"No included outfield players found for {league} {season}.")

    df = pd.concat(group_frames, ignore_index=True, sort=False)
    df = df.sort_values(
        [config.POSITION_GROUP_COL, config.OVERALL_SCORE_COL],
        ascending=[True, False],
    )

    config.DATA_FINAL.mkdir(parents=True, exist_ok=True)
    output_path = config.get_final_path(league, season)
    df.to_csv(output_path, index=False)

    last_updated_path = config.DATA_FINAL / "last_updated.txt"
    last_updated_path.write_text(date.today().isoformat())
    print(f"Last updated timestamp saved -> {last_updated_path}")

    print(f"\nSaved to {output_path}")
    for group, group_df in df.groupby(config.POSITION_GROUP_COL):
        print(
            f"  {group}: {len(group_df)} players, "
            f"top {group_df.iloc[0]['player_name']} "
            f"({group_df.iloc[0][config.OVERALL_SCORE_COL]:.1f})"
        )

    return df


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
