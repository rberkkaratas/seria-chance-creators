"""
Merge Leagues — Cross-League Feature Engineering
-------------------------------------------------
Concatenates all per-league chance_creator CSVs and recomputes
global (cross-league) percentile ranks and role scores.

Per-league run (chance_creation.py) produces:
  {metric}_league_pct  — within-league rank (permanent, never touched here)
  {metric}_pct         — starts as a copy of _league_pct

This step overwrites {metric}_pct with global ranks across all ~420 players,
then recomputes role scores using those global percentiles:
  role_score_{Role}         — global (cross-league) score
  role_score_{Role}_league  — within-league score (copied from per-league files)
  primary_role              — based on global role scores
  primary_role_league       — based on within-league role scores

Output: data/final/all_leagues_{season}.csv

Usage:
    # Run chance_creation.py for all leagues first:
    python -m src.features.chance_creation --league Serie_A --season 2025-2026
    python -m src.features.chance_creation --league Premier_League --season 2025-2026
    python -m src.features.chance_creation --league La_Liga --season 2025-2026
    python -m src.features.chance_creation --league Bundesliga --season 2025-2026
    python -m src.features.chance_creation --league Ligue_1 --season 2025-2026

    # Then merge:
    python -m src.features.merge_leagues --season 2025-2026
"""

import argparse
from datetime import date

import pandas as pd

import config


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
                  f"Run: python -m src.features.chance_creation --league {league} --season {season}")
            continue
        df = pd.read_csv(path)
        df["league"] = league          # ensure column is present
        frames.append(df)
        print(f"  Loaded {league}: {len(df)} players")

    if not frames:
        raise FileNotFoundError("No per-league files found. Run chance_creation.py for each league first.")

    return pd.concat(frames, ignore_index=True)


# ─── Global Percentiles ───────────────────────────────────────────────

def compute_global_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Overwrite {metric}_pct with cross-league rank-within-pool percentiles.
    {metric}_league_pct is left unchanged (within-league, set by chance_creation.py).

    Only metrics that have a _league_pct column are processed — this guarantees
    we only touch metrics that were percentile-ranked in the per-league step.
    """
    league_pct_cols = [c for c in df.columns if c.endswith("_league_pct")]
    global_metrics = [c.replace("_league_pct", "") for c in league_pct_cols]

    reranked = 0
    for metric in global_metrics:
        raw_col = metric          # e.g. key_passes_p90
        pct_col = f"{metric}_pct"
        if raw_col in df.columns and pct_col in df.columns:
            df[pct_col] = df[raw_col].rank(pct=True) * 100
            reranked += 1

    print(f"  Reranked {reranked} metrics across {len(df)} players (global pool).")
    return df


# ─── Global Role Scores ───────────────────────────────────────────────

def compute_global_role_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute global role scores (0–100) using cross-league {metric}_pct columns.

    Renames existing per-league role score columns to role_score_{Role}_league
    and primary_role to primary_role_league, then writes fresh global versions.
    """
    # Preserve league-mode role scores under a _league suffix
    for role_name in config.ROLE_WEIGHTS:
        league_col = f"{config.ROLE_SCORE_COL_PREFIX}{role_name}"
        if league_col in df.columns:
            df.rename(columns={league_col: f"{league_col}_league"}, inplace=True)

    if config.PRIMARY_ROLE_COL in df.columns:
        df.rename(columns={config.PRIMARY_ROLE_COL: "primary_role_league"}, inplace=True)

    # Compute global role scores using the overwritten global _pct columns
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


# ─── Summary ──────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame):
    """Print cross-league role distribution and top players per role."""
    print(f"\n{'─'*60}")
    print(f"Cross-league pool: {len(df)} qualified midfielders")
    print(f"  " + "  ".join(
        f"{lg}={len(df[df['league']==lg])}"
        for lg in config.LEAGUES if lg in df['league'].values
    ))

    print(f"\nGlobal role distribution:")
    role_counts = df[config.PRIMARY_ROLE_COL].value_counts()
    for role, count in role_counts.items():
        pct = count / len(df) * 100
        print(f"  {role:<20}: {count:>3} players ({pct:.0f}%)")

    print(f"\nTop 5 per global role score:")
    for role_name in config.ROLE_WEIGHTS:
        col = f"{config.ROLE_SCORE_COL_PREFIX}{role_name}"
        if col not in df.columns:
            continue
        top = df.nlargest(5, col)[["player_name", "league", "team_name", col]]
        print(f"\n  {role_name}:")
        for _, row in top.iterrows():
            print(f"    {row['player_name']:<25} {row['league']:<18} {row['team_name']:<20} {row[col]:.1f}")


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

    df = df.sort_values("chance_creation_score", ascending=False)

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
