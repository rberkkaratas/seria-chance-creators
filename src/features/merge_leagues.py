"""
Merge Leagues — Cross-League Player Feature Engineering
-------------------------------------------------------
Concatenates per-league player feature CSVs and recomputes global percentile
ranks and role scores within each position group.

Per-league run (player_features.py) produces:
  {metric}_league_pct  — within league x position group (never touched here)
  {metric}_pct         — starts as a copy of _league_pct

This step overwrites {metric}_pct with league-anchored global percentiles:
each within-league percentile is mapped to a latent z-score (inverse normal
CDF, clipped to [0.5, 99.5]) and shifted by a per-league strength offset
derived from ClubElo mean club Elo (see src/enrichment/league_strength.py
and config.ELO_PER_SIGMA), then reranked within the cross-league position
group. Rate shrinkage, possession adjustment, and reliability shrinkage are
inherited from the within-league step — they are not re-applied on pooled
raw values.

Role scores, primary_role, and overall_score are then recomputed from the
adjusted percentiles. The merged output keeps a single scoring structure:
per-league role_score_{Role} / primary_role values loaded from the CSVs are
overwritten in place (no *_league copies).

Output: data/final/all_leagues_{season}.csv

Usage:
    python -m src.features.player_features --league all --season 2025-2026

    python -m src.features.merge_leagues --season 2025-2026
"""

import argparse
from datetime import date
from statistics import NormalDist

import pandas as pd

import config
from src.enrichment.league_strength import get_league_strength, load_offsets_for
from src.features.player_features import (
    compute_overall_score,
    compute_role_scores,
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
    parser.add_argument(
        "--skip-league-strength",
        action="store_true",
        help=(
            "Temporarily disable ClubElo anchoring and use neutral 0.0 offsets "
            "for every loaded league. Intended only when ClubElo is unavailable."
        ),
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

# Clipping keeps the latent z in ~[-2.58, +2.58], so no percentile maps to
# ±inf and league offsets can still reorder tail players.
PCT_CLIP = (0.5, 99.5)


def compute_global_percentiles(df: pd.DataFrame, offsets: dict[str, float]) -> pd.DataFrame:
    """
    Overwrite {metric}_pct with league-anchored cross-league percentiles.
    {metric}_league_pct is left unchanged.

    Each within-league percentile becomes a latent z (inverse normal CDF),
    shifted by the league's strength offset (SD units), then reranked within
    the cross-league position group. Raw metric values are not consulted —
    shrinkage and possession adjustment are already baked into _league_pct.
    """
    if config.POSITION_GROUP_COL not in df.columns:
        raise KeyError(f"Missing required column: {config.POSITION_GROUP_COL}")
    if "league" not in df.columns:
        raise KeyError("Missing required column: league")

    offset_series = df["league"].map(offsets)
    if offset_series.isna().any():
        unknown = sorted(df.loc[offset_series.isna(), "league"].unique())
        raise KeyError(f"No strength offset for leagues: {unknown}")

    inv_cdf = NormalDist().inv_cdf
    league_pct_cols = [c for c in df.columns if c.endswith("_league_pct")]

    reranked = 0
    for league_pct_col in league_pct_cols:
        pct_col = league_pct_col.removesuffix("_league_pct") + "_pct"
        if pct_col not in df.columns:
            continue
        pct = pd.to_numeric(df[league_pct_col], errors="coerce").clip(*PCT_CLIP)
        z = pct.map(lambda p: inv_cdf(p / 100.0) if pd.notna(p) else float("nan"))
        adjusted = z + offset_series          # NaN percentiles stay NaN

        df[pct_col] = pd.NA
        for group_key, group_idx in df.groupby(config.POSITION_GROUP_COL, dropna=False).groups.items():
            df.loc[group_idx, pct_col] = adjusted.loc[group_idx].rank(pct=True) * 100
        df[pct_col] = pd.to_numeric(df[pct_col], errors="coerce")
        reranked += 1

    print(f"  League-anchored rerank of {reranked} metrics within global position-group pools.")
    return df


# ─── Global Role Scores ───────────────────────────────────────────────

def compute_global_role_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute global role scores (0–100) using cross-league group-scoped
    {metric}_pct columns.

    Per-league role_score_{Role} / primary_role values loaded from the CSVs
    are overwritten in place — the merged output carries a single scoring
    structure with no *_league copies.
    """
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
    for col in numeric_score_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# ─── Summary ──────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame, offsets: dict[str, float], skipped_strength: bool = False):
    """Print league strength offsets, cross-league group and role distribution."""
    print(f"\n{'─'*60}")
    print(f"Cross-league pool: {len(df)} included outfield player rows")
    print(f"  " + "  ".join(
        f"{lg}={len(df[df['league']==lg])}"
        for lg in config.LEAGUES if lg in df['league'].values
    ))

    if skipped_strength:
        print("\nLeague strength offsets: skipped (neutral 0.00 offsets)")
        print(f"  {'league':<22} {'offset σ':>9}")
        for lg in sorted(offsets):
            print(f"  {lg:<22} {offsets[lg]:>+9.2f}")
    else:
        strength = get_league_strength()
        mean_elos = dict(zip(strength["league"], strength["mean_elo"]))
        print(f"\nLeague strength offsets ({config.ELO_PER_SIGMA:.0f} Elo per σ):")
        print(f"  {'league':<22} {'mean Elo':>9} {'offset σ':>9}")
        for lg, off in sorted(offsets.items(), key=lambda kv: kv[1], reverse=True):
            elo = mean_elos.get(lg)
            elo_str = f"{elo:>9.1f}" if elo is not None else f"{'?':>9}"
            print(f"  {lg:<22} {elo_str} {off:>+9.2f}")

    for group, group_df in df.groupby(config.POSITION_GROUP_COL):
        group_name = config.POSITION_GROUPS[group]["display_name"]
        print(f"\n{group_name}: {len(group_df)} players")

        top_n = min(50, len(group_df))
        top_mix = group_df.nlargest(top_n, config.OVERALL_SCORE_COL)["league"].value_counts()
        print(f"  Top-{top_n} league mix (vs pool share):")
        for lg, count in top_mix.items():
            pool_share = len(group_df[group_df["league"] == lg]) / len(group_df) * 100
            print(f"    {lg:<22}: {count:>3}  (pool {pool_share:.0f}%)")
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

def run_merge(
    season: str = config.SEASON,
    leagues: list[str] | None = None,
    skip_league_strength: bool = False,
):
    if leagues is None:
        leagues = list(config.LEAGUES.keys())

    print(f"Season: {season}  |  Leagues: {', '.join(leagues)}\n")

    print("Loading per-league files...")
    df = load_league_files(leagues, season)
    print(f"Total: {len(df)} players\n")

    print("Loading league strength offsets...")
    # Offsets are centered on the leagues actually loaded — files can be skipped.
    loaded_leagues = sorted(df["league"].unique())
    if skip_league_strength:
        print("  [!] ClubElo anchoring skipped; using neutral offsets for this merge.")
        offsets = {league: 0.0 for league in loaded_leagues}
    else:
        offsets = load_offsets_for(loaded_leagues)
    df[config.LEAGUE_STRENGTH_OFFSET_COL] = df["league"].map(offsets).round(3)

    print("Computing global percentiles (league-anchored cross-league rank)...")
    df = compute_global_percentiles(df, offsets)

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

    print_summary(df, offsets, skipped_strength=skip_league_strength)


if __name__ == "__main__":
    args = parse_arguments()
    run_merge(
        season=args.season,
        leagues=args.leagues,
        skip_league_strength=args.skip_league_strength,
    )
