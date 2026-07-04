# Dashboard Usage Guide

## Launch

```bash
streamlit run streamlit/app.py
```

The app loads:

1. `data/final/all_leagues_{season}_enriched.csv`
2. `data/final/all_leagues_{season}.csv`

Team tabs additionally load `data/final/teams_{season}.csv` when it exists.

If neither exists, run:

```bash
python -m src.features.player_features --league all --season 2025-2026
python -m src.enrichment.transfermarkt
python -m src.features.team_features --season 2025-2026
```

## Workflow

```text
Position Group -> Filters -> Player tabs
Team Rankings -> Team Profile
```

## Filters

| Filter | Notes |
|--------|-------|
| Position group | Defenders, Fullbacks, Midfielders, Wingers, or Forwards. Every tab is scoped to this choice. |
| Min. minutes | Counts only minutes played in the active group. Default is 180; 600 minutes is the full-sample confidence point. |
| Positions | WhoScored positions inside the active group. |
| Role | Primary roles from the active group only. |
| Market filters | Available after Transfermarkt enrichment. |

## Tabs

| Tab | Purpose |
|-----|---------|
| Shortlist | Rank the active group by Overall or any role score. |
| Role Map | Inspect role taxonomy, distribution, DNA, league share, and market-value patterns. |
| Scout Report | Player-level profile with radar, role bars, totals, similar players, and match log. |
| Compare | Side-by-side comparison of 2-4 players inside the active group. |
| Explore | Group-specific lenses and statistical profile scatter plots. |
| League Overview | League identity and role strength comparisons for the active group. |
| Team Rankings | League table and global team ranking views with team rating and performance delta. |
| Team Profile | One-team profile with result summary, group ratings, style profile, and squad table. |

## Percentiles

- `{metric}_league_pct`: rank within league x position group. Kept in the CSVs as the merge input and for debugging; not shown in the dashboard.
- `{metric}_pct`: league-adjusted cross-league rank within the position group. The merge step converts each within-league percentile to a latent z-score, shifts it by a per-league strength offset (ClubElo mean club Elo, `config.ELO_PER_SIGMA` Elo per SD), and reranks globally.

All role scores, radar values, and `overall_score` in the dashboard use the league-adjusted `_pct` columns — there is no percentile mode toggle. Refresh coefficients once per season with:

```bash
python -m src.enrichment.league_strength --refresh
```

## Team Ratings

`team_rating` is derived from player `overall_score`, not from raw league-table points. Each scored `(player_id, position_group)` row is converted to a clipped latent z-score and minutes-weighted into `team_strength_z`; teams are then percentile-ranked globally.

`perf_delta_rank = league_rank_points - league_rank_rating`. Negative values mean the team is ahead of its squad-quality rank in the table; positive values mean the points rank trails the rating rank.

## Score Confidence

Players below 600 group minutes are visible. Their scores are calibrated with a sample-confidence model using total minutes, appearances, starts, and start rate. Low-confidence role scores are pulled toward 50, so small-sample spikes and small-sample droughts do not dominate the ranking.
