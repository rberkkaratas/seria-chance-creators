# Player Scout 2025/26

Role-based scouting dashboard for outfield players across Europe's top five leagues. The pipeline turns WhoScored match events into per-90 metrics, sample-adjusted group percentiles, tactical role scores, a `primary_role`, and a group-specific `overall_score`.

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

Players enter the dataset from 180 group minutes. The old 600-minute threshold is now the full-sample confidence point: lower-minute players remain visible, but their metric percentiles and role scores are shrunk toward neutral using minutes, appearances, starts, and start rate. WhoScored substitute rows are mapped to the player's primary known outfield position before group filtering, so bench appearances count without being mislabeled as starts. Percentiles and role scores are computed within the active position group, both per league and globally after merge. Overall score is also group-specific, so centre-backs, fullbacks, central midfielders, wingers, and forwards are ranked in cleaner tactical pools. Role definitions live in `config.POSITION_GROUPS`; flattened lookup maps such as `config.ALL_ROLE_WEIGHTS` and `config.POSITION_TO_GROUP` are generated from that config.

## Pipeline

```text
WhoScored fixture pages
  -> src/scraper/fixture_scraper.py
  -> src/scraper/whoscored_extractor.py
  -> src/processing/build_tables.py
  -> src/features/player_features.py
  -> src/features/merge_leagues.py
  -> src/enrichment/transfermarkt.py
  -> streamlit/app.py
```

Run the full local pipeline:

```bash
python -m src.scraper.fixture_scraper --league all --season 2025-2026
python -m src.scraper.whoscored_extractor --league all --season 2025-2026 --manifest
python -m src.processing.build_tables --league all --season 2025-2026
python -m src.features.player_features --league all --season 2025-2026
python -m src.enrichment.transfermarkt
streamlit run streamlit/app.py
```

Run from existing processed data without scraping:

```bash
python -m src.features.player_features --league all --season 2025-2026
python -m src.enrichment.transfermarkt
streamlit run streamlit/app.py
```

Single league refresh:

```bash
python -m src.features.player_features --league Bundesliga --season 2025-2026
python -m src.features.merge_leagues --season 2025-2026
```

## Outputs

| File | Description |
|------|-------------|
| `data/final/{league}_{season}.csv` | Per-league feature output with league/group percentiles |
| `data/final/all_leagues_{season}.csv` | Merged output with global/group percentiles and global role scores |
| `data/final/all_leagues_{season}_enriched.csv` | Merged output plus Transfermarkt data |
| `data/final/last_updated.txt` | ISO date written after feature/merge runs |

The Streamlit app loads only the merged all-leagues outputs, preferring the enriched file when present.

## Tests

```bash
pytest tests/ -v
```

Tests cover WhoScored qualifier parsing, position-group-aware inclusion filtering, per-90 math, sample reliability, role weight integrity, role score ranges, primary role validity, group-scoped percentiles, and merge-time global percentile recomputation.

## Data Sources

| Source | Use |
|--------|-----|
| WhoScored | Match events and player metadata |
| Transfermarkt | Market value, contract expiry, and feasibility |

This project is for personal educational and portfolio purposes only.
