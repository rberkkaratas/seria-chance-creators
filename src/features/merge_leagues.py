"""
Merge Leagues — Cross-League Player Feature Engineering
-------------------------------------------------------
Concatenates per-league player feature CSVs and recomputes global percentile
ranks and role scores within each position group.

Per-league run (player_features.py) produces:
  {metric}_league_pct  — within league x position group (never touched here)
  {metric}_pct         — starts as a copy of _league_pct

This step overwrites {metric}_pct with global ranks within each position group,
then recomputes role scores using those global percentiles:
  role_score_{Role}         — global (cross-league) score
  role_score_{Role}_league  — within-league score (copied from per-league files)
  primary_role              — based on global role scores
  primary_role_league       — based on within-league role scores

Output: data/final/all_leagues_{season}.csv

Usage:
    python -m src.features.player_features --league all --season 2025-2026

    python -m src.features.merge_leagues --season 2025-2026
"""

import argparse
from datetime import date

import pandas as pd

import config
from src.features.player_features import (
    compute_overall_score,
    compute_role_scores,
    sample_adjusted_metric,
)


# ─── CLI ─────────────────────────────────────────────────────────────

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Merge per-league CSVs and compute cross-league percentiles"
    )
    parser.add_argument(
        "--season", default=config.SEASON,
        help="Season string, e.g. 2025-2026 (default: %(default)s)"
    )
    parser.add_argument(
        "--leagues", nargs="+", default=list(config.LEAGUES.keys()),
        help="League keys to include (default: all 5)"
    )
    return parser.parse_args()


# ─── Load ─────────────────────────────────────────────────────────────

def load_league_files(leagues: list[str], season: str) -> pd.DataFrame:
    """Load and concat per-league final CSVs. Missing files are skipped with a warning."""
    frames = []
    for league in leagues:
        path = config.get_final_path(league, season)
        if not path.exists():
            print(f"  [!] {path.name} not found — skipping {league}. "
                  f"Run: python -m src.features.player_features --league {league} --season {season}")
            continue
        df = pd.read_csv(path)
        df["league"] = league          # ensure column is present
        frames.append(df)
        print(f"  Loaded {league}: {len(df)} players")

    if not frames:
        raise FileNotFoundError("No per-league files found. Run player_features.py for each league first.")

    return pd.concat(frames, ignore_index=True)


# ─── Global Percentiles ───────────────────────────────────────────────

def compute_global_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Overwrite {metric}_pct with cross-league rank-within-position-group percentiles.
    {metric}_league_pct is left unchanged.

    Only metrics that have a _league_pct column are processed — this guarantees
    we only touch metrics that were percentile-ranked in the per-league step.
    """
    if config.POSITION_GROUP_COL not in df.columns:
        raise KeyError(f"Missing required column: {config.POSITION_GROUP_COL}")

    league_pct_cols = [c for c in df.columns if c.endswith("_league_pct")]
    global_metrics = [c.replace("_league_pct", "") for c in league_pct_cols]

    reranked = 0
    for metric in global_metrics:
        raw_col = metric          # e.g. key_passes_p90
        pct_col = f"{metric}_pct"
        if raw_col in df.columns and pct_col in df.columns:
            df[pct_col] = pd.NA
            for group_key, group_idx in df.groupby(config.POSITION_GROUP_COL, dropna=False).groups.items():
                group_df = df.loc[group_idx]
                rank_source = sample_adjusted_metric(group_df, raw_col, group=group_key)
                df.loc[group_idx, pct_col] = rank_source.rank(pct=True) * 100
            df[pct_col] = pd.to_numeric(df[pct_col], errors="coerce")
            reranked += 1

    print(f"  Reranked {reranked} metrics within global position-group pools.")
    return df


# ─── Global Role Scores ───────────────────────────────────────────────

def compute_global_role_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute global role scores (0–100) using cross-league group-scoped
    {metric}_pct columns.

    Renames existing per-league role score columns to role_score_{Role}_league
    and primary_role to primary_role_league, then writes fresh global versions.
    """
    # Preserve league-mode role scores under a _league suffix
    for role_name in config.ALL_ROLE_WEIGHTS:
        league_col = f"{config.ROLE_SCORE_COL_PREFIX}{role_name}"
        if league_col in df.columns:
            df.rename(columns={league_col: f"{league_col}_league"}, inplace=True)

    if config.PRIMARY_ROLE_COL in df.columns:
        df.rename(columns={config.PRIMARY_ROLE_COL: "primary_role_league"}, inplace=True)

    group_results: dict[str, pd.DataFrame] = {}
    missing_cols: set[str] = set()

    for group in config.POSITION_GROUPS:
        group_mask = df[config.POSITION_GROUP_COL] == group
        if not group_mask.any():
            continue
        group_df = df.loc[group_mask].copy()
        group_df = compute_role_scores(group_df, group)
        group_df = compute_overall_score(group_df, group)
        group_results[group] = group_df
        missing_cols.update(set(group_df.columns) - set(df.columns))

    if missing_cols:
        df = pd.concat(
            [df, pd.DataFrame({col: pd.NA for col in sorted(missing_cols)}, index=df.index)],
            axis=1,
        )

    for group, group_df in group_results.items():
        group_mask = df[config.POSITION_GROUP_COL] == group
        for col in group_df.columns:
            df.loc[group_mask, col] = group_df[col]

    numeric_score_cols = [config.OVERALL_SCORE_COL]
    for role_name in config.ALL_ROLE_WEIGHTS:
        numeric_score_cols.append(f"{config.ROLE_SCORE_COL_PREFIX}{role_name}")
        numeric_score_cols.append(f"{config.ROLE_SCORE_COL_PREFIX}{role_name}_league")
    for col in numeric_score_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# ─── Summary ──────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame):
    """Print cross-league group and role distribution."""
    print(f"\n{'─'*60}")
    print(f"Cross-league pool: {len(df)} included outfield player rows")
    print(f"  " + "  ".join(
        f"{lg}={len(df[df['league']==lg])}"
        for lg in config.LEAGUES if lg in df['league'].values
    ))

    for group, group_df in df.groupby(config.POSITION_GROUP_COL):
        group_name = config.POSITION_GROUPS[group]["display_name"]
        print(f"\n{group_name}: {len(group_df)} players")
        role_counts = group_df[config.PRIMARY_ROLE_COL].value_counts()
        for role, count in role_counts.items():
            pct = count / len(group_df) * 100
            print(f"  {role:<24}: {count:>3} players ({pct:.0f}%)")

        print("  Top 3 per global role score:")
        for role_name in config.POSITION_GROUPS[group]["roles"]:
            col = f"{config.ROLE_SCORE_COL_PREFIX}{role_name}"
            if col not in group_df.columns:
                continue
            top = group_df.nlargest(3, col)[["player_name", "league", "team_name", col]]
            print(f"    {role_name}:")
            for _, row in top.iterrows():
                print(
                    f"      {row['player_name']:<25} {row['league']:<18} "
                    f"{row['team_name']:<20} {row[col]:.1f}"
                )


# ─── Entry Point ─────────────────────────────────────────────────────

def run_merge(season: str = config.SEASON, leagues: list[str] | None = None):
    if leagues is None:
        leagues = list(config.LEAGUES.keys())

    print(f"Season: {season}  |  Leagues: {', '.join(leagues)}\n")

    print("Loading per-league files...")
    df = load_league_files(leagues, season)
    print(f"Total: {len(df)} players\n")

    print("Computing global percentiles (cross-league rank-within-pool)...")
    df = compute_global_percentiles(df)

    print("Computing global role scores...")
    df = compute_global_role_scores(df)

    df = df.sort_values(
        [config.POSITION_GROUP_COL, config.OVERALL_SCORE_COL],
        ascending=[True, False],
    )

    output_path = config.DATA_FINAL / f"all_leagues_{season}.csv"
    config.DATA_FINAL.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"\nSaved → {output_path}")

    last_updated_path = config.DATA_FINAL / "last_updated.txt"
    last_updated_path.write_text(date.today().isoformat())
    print(f"Last updated timestamp saved → {last_updated_path}")

    print_summary(df)


if __name__ == "__main__":
    args = parse_arguments()
    run_merge(season=args.season, leagues=args.leagues)
