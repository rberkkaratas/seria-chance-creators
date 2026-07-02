# Dashboard Usage Guide

## Launch

```bash
streamlit run streamlit/app.py
```

The app loads:

1. `data/final/all_leagues_{season}_enriched.csv`
2. `data/final/all_leagues_{season}.csv`

If neither exists, run:

```bash
python -m src.features.player_features --league all --season 2025-2026
python -m src.enrichment.transfermarkt
```

## Workflow

```text
Position Group -> Filters -> Shortlist -> Scout Report -> Compare
```

## Filters

| Filter | Notes |
|--------|-------|
| Position group | Defenders, Fullbacks, Midfielders, Wingers, or Forwards. Every tab is scoped to this choice. |
| Min. minutes | Counts only minutes played in the active group. Default is 180; 600 minutes is the full-sample confidence point. |
| Positions | WhoScored positions inside the active group. |
| Role | Primary roles from the active group only. |
| Percentile mode | All-leagues or within-league percentiles, both group-scoped. |
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

## Percentile Modes

- `{metric}_league_pct`: rank within league x position group.
- `{metric}_pct`: rank within all-leagues x position group after merge.

The dashboard switches role scores and radar values between these two modes when league score columns are present.

## Score Confidence

Players below 600 group minutes are visible. Their scores are calibrated with a sample-confidence model using total minutes, appearances, starts, and start rate. Low-confidence role scores are pulled toward 50, so small-sample spikes and small-sample droughts do not dominate the ranking.
