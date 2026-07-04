# SquadLens

Football analytics platform covering player and team performance across ten European leagues for the 2025/26 season. The pipeline turns WhoScored match events into per-90 metrics, sample-adjusted group percentiles, tactical role scores, a `primary_role`, and a group-specific `overall_score`.

Goalkeepers are excluded for now because GK-specific event parsing is not implemented.

## Position Groups

Players are evaluated inside their position group. A player can appear in more than one group, producing one row per `(player_id, position_group)`.

| Group | Positions | Roles |
|-------|-----------|-------|
| DEF | DC | Stopper, Aerial Dominator, Ball-Playing Defender |
| FB | DL, DR, DML, DMR | Defensive Fullback, Attacking Fullback, Inverted Fullback, Crossing Fullback |
| MID | DMC, MC, AMC | Creator, Ball Progressor, Box Threat, Deep Builder, Ball Winner |
| WING | ML, MR, AML, AMR, FWL, FWR | Touchline Winger, Inside Forward, Wide Creator, Pressing Winger |
| FW | FW | Finisher, Target Man, Creative Forward, Pressing Forward |

Players enter the dataset from 180 group minutes. The old 600-minute threshold is now the full-sample confidence point: lower-minute players remain visible, but their metric percentiles and role scores are shrunk toward neutral using minutes, appearances, starts, and start rate. WhoScored substitute rows are mapped to the player's primary known outfield position before group filtering, so bench appearances count without being mislabeled as starts. Percentiles are computed within the active position group per league; the merge step then anchors them across leagues — each within-league percentile becomes a latent z-score shifted by a per-league strength offset derived from ClubElo mean club Elo, so equal standing counts for more in a stronger league. Overall score is also group-specific, so centre-backs, fullbacks, central midfielders, wingers, and forwards are ranked in cleaner tactical pools. Role definitions live in `config.POSITION_GROUPS`; flattened lookup maps such as `config.ALL_ROLE_WEIGHTS` and `config.POSITION_TO_GROUP` are generated from that config.

## Pipeline

```text
WhoScored fixture pages
  -> src/scraper/fixture_scraper.py
  -> src/scraper/whoscored_extractor.py
  -> src/processing/build_tables.py
  -> src/features/player_features.py
  -> src/features/merge_leagues.py   <- src/enrichment/league_strength.py (ClubElo, cached)
  -> src/enrichment/transfermarkt.py
  -> src/features/team_features.py
  -> streamlit/app.py
```

Run the full local pipeline:

```bash
python -m src.scraper.fixture_scraper --league all --season 2025-2026
python -m src.scraper.whoscored_extractor --league all --season 2025-2026 --manifest
python -m src.processing.build_tables --league all --season 2025-2026
python -m src.enrichment.league_strength --refresh   # once per season
python -m src.features.player_features --league all --season 2025-2026
python -m src.enrichment.transfermarkt
python -m src.features.team_features --season 2025-2026
streamlit run streamlit/app.py
```

The configured 2025/26 league set currently includes Serie A, Premier League, La Liga, Bundesliga, Ligue 1, Championship, Liga Portugal, Eredivisie, Jupiler Pro League, and Super Lig.

Run from existing processed data without scraping:

```bash
python -m src.features.player_features --league all --season 2025-2026
python -m src.enrichment.transfermarkt
python -m src.features.team_features --season 2025-2026
streamlit run streamlit/app.py
```

Single league refresh:

```bash
python -m src.features.player_features --league Bundesliga --season 2025-2026
python -m src.features.merge_leagues --season 2025-2026
python -m src.features.team_features --season 2025-2026
```

## Outputs

| File | Description |
|------|-------------|
| `data/final/{league}_{season}.csv` | Per-league feature output with league/group percentiles |
| `data/final/all_leagues_{season}.csv` | Merged output with league-adjusted global percentiles and global role scores |
| `data/final/all_leagues_{season}_enriched.csv` | Merged output plus Transfermarkt data |
| `data/final/teams_{season}.csv` | Team results, style metrics, squad profile, ratings, and ranks |
| `data/final/last_updated.txt` | ISO date written after feature/merge runs |
| `data/enrichment/clubelo_league_strength.csv` | Cached ClubElo league mean Elos (committed; merge needs no network) |
| `data/enrichment/clubelo_club_elo.csv` | Cached per-club ClubElo rows used as an optional team reference column |

The Streamlit app loads the merged all-leagues player output, preferring the enriched file when present, and loads `teams_{season}.csv` for the team tabs when available.

## Team Analytics

`src/features/team_features.py` builds one row per club from existing processed match/team/player tables plus the merged player scores. It does not require a new scrape.

Team strength converts each scored `(player_id, position_group)` row's `overall_score` to a clipped latent z-score, minutes-weights those rows inside the club, then percentile-ranks clubs globally into `team_rating`. There is no fixed position-group weighting: a wingback-heavy or striker-light system is rated by the minutes it actually played. Group sub-ratings (`rating_DEF`, `rating_FB`, `rating_MID`, `rating_WING`, `rating_FW`) are profile indicators only and become blank below the configured group-minute threshold.

`perf_delta_rank = league_rank_points - league_rank_rating`: negative values mean results are ahead of squad-quality rank; positive values mean results lag the rating rank. Low coverage is flagged with `low_coverage` and never dropped.

## Tests

```bash
pytest tests/ -v
```

Tests cover WhoScored qualifier parsing, position-group-aware inclusion filtering, per-90 math, sample reliability, role weight integrity, role score ranges, primary role validity, group-scoped percentiles, league-strength offset math, and merge-time league-anchored percentile recomputation.

## Data Sources

| Source | Use |
|--------|-----|
| WhoScored | Match events and player metadata |
| Transfermarkt | Market value, contract expiry, and feasibility |
| ClubElo | League-strength offsets and optional club Elo reference |

This project is for personal educational and portfolio purposes only.
