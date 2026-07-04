# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

This is SquadLens, a football analytics platform that scores outfield players and profiles teams across ten European leagues (Serie A, Premier League, La Liga, Bundesliga, Ligue 1, Championship, Liga Portugal, Eredivisie, Jupiler Pro League, Super Lig) for the 2025/26 season. It scores players inside five position groups:

- `DEF`: DC
- `FB`: DL, DR, DML, DMR
- `MID`: DMC, MC, AMC
- `WING`: ML, MR, AML, AMR, FWL, FWR
- `FW`: FW

Each `(player_id, position_group)` row receives 0-100 role scores, a `primary_role`, and a group-specific `overall_score`. Goalkeepers are excluded until GK-specific event parsing is added.

## Commands

```bash
pip install -r requirements.txt
pytest tests/ -v
python -m src.features.player_features --league all --season 2025-2026
python -m src.enrichment.transfermarkt
python -m src.features.team_features --season 2025-2026
streamlit run streamlit/app.py
```

Full scrape pipeline:

```bash
python -m src.scraper.fixture_scraper --league all --season 2025-2026
python -m src.scraper.whoscored_extractor --league all --season 2025-2026 --manifest
python -m src.processing.build_tables --league all --season 2025-2026
python -m src.enrichment.league_strength --refresh   # once per season
python -m src.features.player_features --league all --season 2025-2026
python -m src.enrichment.transfermarkt
python -m src.features.team_features --season 2025-2026
```

Single league update:

```bash
python -m src.features.player_features --league Bundesliga --season 2025-2026
python -m src.features.merge_leagues --season 2025-2026
python -m src.features.team_features --season 2025-2026
```

## Architecture

```text
fixture_scraper.py
  -> whoscored_extractor.py
  -> build_tables.py
  -> player_features.py
  -> merge_leagues.py   <- league_strength.py (ClubElo coefficients, cached CSV)
  -> transfermarkt.py
  -> team_features.py
  -> streamlit/app.py
```

## Key Rules

- Role definitions live in `config.POSITION_GROUPS`. Add/change roles there, not in feature code or UI tabs.
- Flattened lookups (`ALL_ROLE_WEIGHTS`, `ALL_ROLE_COLORS`, `ALL_ROLE_DESCRIPTIONS`, `POSITION_TO_GROUP`) are generated from `POSITION_GROUPS`.
- All role and `overall_score` weights must sum to 1.0; config import validates this.
- Percentiles are group-scoped:
  - `{metric}_league_pct`: within league x position group (merge input + debugging; not surfaced in the UI)
  - `{metric}_pct`: league-anchored cross-league rank within the position group after merge
- Cross-league anchoring: merge converts each `_league_pct` to a latent z (inverse normal CDF, clipped 0.5–99.5), adds the league's strength offset, and reranks globally. Offsets come from ClubElo mean club Elo per `config.LEAGUE_CLUBELO` (country, level); `config.ELO_PER_SIGMA` is the single calibration knob and only relative offsets matter. The cache `data/enrichment/clubelo_league_strength.csv` is committed — merge never needs network. Missing leagues in the cache are a hard error, never a silent zero offset.
- The merged output has a single scoring structure: no `role_score_*_league` or `primary_role_league` columns, and the UI has no percentile-mode toggle. `config.LEAGUE_STRENGTH_OFFSET_COL` carries each row's offset for transparency.
- Team analytics are built by `src/features/team_features.py` after Transfermarkt enrichment. It writes `data/final/teams_{season}.csv`; the dashboard loads it separately and leaves it unfiltered by the player sidebar.
- Team rating converts player `overall_score` to clipped latent z, minutes-weights all scored `(player_id, position_group)` rows, then percentile-ranks teams globally. There is no fixed position-group weight dict. Group sub-ratings are profile indicators only and are blank below `config.TEAM_MIN_GROUP_MINUTES`.
- `perf_delta_rank = league_rank_points - league_rank_rating`: negative means results are ahead of squad-quality rank; positive means results lag it. Low coverage is flagged with `low_coverage`, never dropped.
- `data/enrichment/clubelo_club_elo.csv` is an optional external reference for team tabs. It does not feed player or team ratings.
- A player can qualify in multiple groups. Do not assume `player_id` is unique in final files; use `(player_id, position_group)` for feature rows.
- `DataLoader._CANDIDATE_PATHS` intentionally only loads `all_leagues_{season}_enriched.csv` and `all_leagues_{season}.csv`.
- `chance_creation_score`, `chance_creators*` outputs, clustering, and `streamlit/app_legacy.py` are removed.
- Raw event CSVs under `data/events/` are gitignored; processed and final CSVs are committed.

## Critical Implementation Details

- `build_tables.py` qualifier casing constants are regression-guarded. Do not replace them with raw strings.
- Assist detection primarily uses event-type 92 in `satisfiedEventsTypes`; `IntentionalAssist` is only a fallback for unit-test contexts.
- Position filtering is group-aware: players enter from 180 active-group minutes; 600 active-group minutes is the full-sample confidence point.
- `goals`, `long_balls`, and `shot_creating_actions` are aggregated from processed `players.csv`; no re-scrape is required for those feature outputs.
- `progressive_carries` is not used in role scoring because the current pipeline leaves it as a placeholder.
- `overall_score` is standardize-then-rank: role scores are z-standardized within the pool, blended with `composite_weights`, then percentile-ranked to 0-100. Pools under 5 rows fall back to a plain weighted average. It is a within-group percentile, not an absolute grade.
- Rates in `config.RATE_SHRINKAGE` (aerial, tackle, cross, dribble rates) are shrunk toward the pool-average rate by attempt count (prior of 15 pseudo-attempts) before percentile ranking; the displayed raw rate columns stay untouched.
- Metrics in `config.PADJ_METRICS` (DEF, FB, MID) are possession-adjusted before percentile ranking: scaled by `0.5 / opp_possession_share`, where the share is derived per match from `teams.csv` pass counts and minutes-weighted per player. Displayed raw columns stay per-90. Never add recovery/press-regain metrics to PAdj — they correlate negatively with opponent possession and would double-reward dominant-team players.
