# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

SquadLens is a football analytics platform that scores outfield players and profiles teams across **ten European leagues** (Serie A, Premier League, La Liga, Bundesliga, Ligue 1, Championship, Liga Portugal, Eredivisie, Jupiler Pro League, Süper Lig) for the 2025/26 season. Each player receives a 0-100 score inside five position groups (DEF, FB, MID, WING, FW), plus a `primary_role` assignment and a group-specific `overall_score`. The system is two parts: an offline data pipeline (scrape → process → feature engineer → merge → enrich) and a Streamlit web dashboard.

## Commands

### Setup
```bash
pip install -r requirements.txt
```

### Run the pipeline (in order)
```bash
# 1. Collect match IDs from WhoScored fixture pages
python -m src.scraper.fixture_scraper --league all --season 2025-2026

# 2. Scrape match events (SeleniumBase UC mode)
python -m src.scraper.whoscored_extractor --league all --season 2025-2026 --manifest
# or single match IDs for testing:
python -m src.scraper.whoscored_extractor --ids 1829473 1829474

# 3. Build normalized tables from raw event CSVs
python -m src.processing.build_tables --league all --season 2025-2026

# 4. Engineer player features — per-90, percentiles, role scores, primary_role
#    --league all also triggers merge_leagues automatically
python -m src.features.player_features --league all --season 2025-2026

# 5. Enrich with Transfermarkt data — market value, contract, feasibility (optional)
python -m src.enrichment.transfermarkt

# 6. Build team analytics from processed + final player data
python -m src.features.team_features --season 2025-2026

# 7. Launch the dashboard
streamlit run streamlit/app.py
```

### Single league update + re-merge
```bash
python -m src.features.player_features --league Bundesliga --season 2025-2026
python -m src.features.merge_leagues --season 2025-2026
python -m src.features.team_features --season 2025-2026
```

### Tests
```bash
pytest tests/ -v
# Run a single test file:
pytest tests/test_build_tables.py -v
# Run a single test:
pytest tests/test_team_features.py::test_team_ratings_clip_scores_weight_minutes_and_count_unique_players -v
```

## Architecture

### Data Flow
```
WhoScored fixture pages
  → src/scraper/fixture_scraper.py         → data/match_ids/{league}_{season}.csv
  → src/scraper/whoscored_extractor.py     → data/events/{league}/{season}/*.csv
  → src/processing/build_tables.py         → data/processed/{league}/{season}/
  → src/features/player_features.py        → data/final/{league}_{season}.csv
  → src/features/merge_leagues.py          → data/final/all_leagues_{season}.csv
  → src/enrichment/transfermarkt.py        → data/final/all_leagues_{season}_enriched.csv
  → src/features/team_features.py          → data/final/teams_{season}.csv
  → streamlit/app.py                       (dashboard reads highest-priority file from data/final/)
```

### Key Modules

- **`config.py`** — Central configuration: data paths, league definitions, player filters, sample reliability, ClubElo settings, team analytics thresholds, and `POSITION_GROUPS`. All player role definitions live in `config.POSITION_GROUPS`; flattened maps (`ALL_ROLE_WEIGHTS`, `ALL_ROLE_COLORS`, `POSITION_TO_GROUP`) are generated from that config. Team analytics thresholds live in the `TEAM_*` constants.

- **`src/scraper/fixture_scraper.py`** — Extracts match IDs from WhoScored fixture pages. Outputs manifest CSVs to `data/match_ids/`. Supports `--league all`.

- **`src/scraper/whoscored_extractor.py`** — Uses SeleniumBase UC mode to bypass WhoScored anti-bot. Extracts `matchCentreData` JSON from page HTML. Dual regex strategies for JSON extraction. Outputs per-match event CSVs and player metadata CSVs. Supports manifest-based scraping (reads match_ids CSV, marks scraped=True after success).

- **`src/processing/build_tables.py`** — Parses WhoScored qualifier lists.
  - **Qualifier casing is critical**: WhoScored displayNames are inconsistent and undocumented. Named constants (`_Q_THROUGH_BALL`, `_Q_LONG_BALL`, `_Q_INTENTIONAL_ASSIST`, etc.) are defined at the top of the file. Tests in `tests/test_build_tables.py` document confirmed casings as regression guards — do not change them without verifying against raw data.
  - Enriches events with boolean flags: key pass, assist, through ball, progressive pass, pass into box, forward pass, half-space pass, penalty area touch, carry into final third, cross, tackle success, aerial total, shots blocked, possession won (total and final-third), ball-winning height.
  - Aggregates to player-match level. Outputs to `data/processed/{league}/{season}/`.

- **`src/features/player_features.py`** — Resolves WhoScored `Sub` rows to a player's primary known outfield position, filters players by active position-group minutes (180 visible, 600 full-confidence), computes per-90/rate metrics, sample-adjusted league percentiles, role scores, `primary_role`, and group-specific `overall_score`. `--league all` automatically runs `merge_leagues.py`. Writes `last_updated.txt` after saving.

- **`src/features/merge_leagues.py`** — Concatenates per-league CSVs, overwrites `{metric}_pct` with league-anchored cross-league percentiles (each `{metric}_league_pct` → latent z via inverse normal CDF → + per-league ClubElo strength offset → rerank within position group; `_league_pct` is preserved as input/debug), then recomputes global role scores and `overall_score` in place — no `*_league` role-score copies. Writes `last_updated.txt` after saving.

- **`src/enrichment/league_strength.py`** — Fetches ClubElo ratings, reduces them to mean Elo per league via `config.LEAGUE_CLUBELO` (country, level), and caches to `data/enrichment/clubelo_league_strength.csv` (committed — merge needs no network). The same snapshot writes `data/enrichment/clubelo_club_elo.csv` for optional team reference display. Offsets are computed at merge time, centered on the loaded league pool; `config.ELO_PER_SIGMA` is the single calibration knob.

- **`src/enrichment/transfermarkt.py`** — Scrapes market value, contract expiry, and transfer feasibility from Transfermarkt squad pages. Uses a local cache (`data/enrichment/tm_squads_cache.csv`) and persistent name-matching results (`data/enrichment/tm_player_mapping.csv`). Manual overrides in `data/enrichment/tm_manual_players.csv`.

- **`src/features/team_features.py`** — Builds `data/final/teams_{season}.csv` from processed `matches.csv`, `teams.csv`, `players.csv`, merged/enriched player scores, and optional club Elo. Outputs results table fields, style metrics, squad profile, `team_strength_z`, `team_rating`, group sub-ratings, global/league ranks, coverage flags, and `perf_delta_rank`. It also drops wrong-league fixture leakage when a processed match's teams do not exist in that league's scored-player pool.

- **`src/visualization/radar.py`** — Dark-themed Plotly radar charts. `create_radar_chart()` for single-player profiles; `create_comparison_radar()` for multi-player overlays.

- **`src/visualization/scatter_profiles.py`** — Quadrant scatter plots for the Statistical Profiles and Free Explore views.

- **`streamlit/app.py`** — Entry point. Loads player data (fallback chain: enriched → merged), loads `teams_{season}.csv` when available, displays `last_updated.txt` as st.info, applies sidebar filters to player tabs, and renders the player + team tabs.

- **`streamlit/core/data_loader.py`** — `DataLoader._CANDIDATE_PATHS` is a priority-ordered list of player CSV paths; `load()` returns the first one that exists. `load_teams()` reads `data/final/teams_{season}.csv` or returns an empty frame. `load_raw()` reads per-match player stats from all processed dirs. `load_last_updated()` reads `data/final/last_updated.txt`.

- **`streamlit/core/filter_service.py`** — `FilterService.apply()` applies UI filters to the DataFrame; `FilterService.build_app_state()` constructs the `AppState` view model from filtered data.

- **`streamlit/core/models.py`** — `FilterState` and `AppState` dataclasses. `AppState` is the shared context passed to all tab renderers.

- **`streamlit/tabs/team_rankings.py`** — League table and global team ranking views, with `team_rating`, rating rank, points rank, `perf_delta_rank`, low-coverage flags, and PPM-vs-rating scatter.

- **`streamlit/tabs/team_profile.py`** — One-team profile: results/rank header, group sub-rating bars, style-vs-league-median profile, and deduped squad table from the player dataset.

- **`streamlit/tabs/__init__.py`** — `TabRenderer` abstract base class. All tab classes implement `render(state: AppState)`.

### Position Groups and Roles
Roles are group-specific and live under `config.POSITION_GROUPS`:
- **DEF** — Stopper, Aerial Dominator, Ball-Playing Defender
- **FB** — Defensive Fullback, Attacking Fullback, Inverted Fullback, Crossing Fullback
- **MID** — Creator, Ball Progressor, Box Threat, Deep Builder, Ball Winner
- **WING** — Touchline Winger, Inside Forward, Wide Creator, Pressing Winger
- **FW** — Finisher, Target Man, Creative Forward, Pressing Forward

### Important Implementation Details

- **Qualifier naming constants**: `build_tables.py` defines module-level constants (`_Q_KEY_PASS`, `_Q_THROUGH_BALL`, `_Q_LONG_BALL`, `_Q_CROSS`, `_Q_INTENTIONAL_ASSIST`) for all WhoScored displayName strings. Never use raw strings in new qualifier checks — add a constant.
- **Assist detection dual-path**: Primary signal is event-type 92 in `satisfiedEventsTypes` (pass directly preceded a goal). Fallback to `IntentionalAssist` qualifier only when `satisfiedEventsTypes` is absent (unit test context). Do not use `IntentionalAssist` as the primary signal — it appears on all key passes, not just those that led to goals.
- **Position-aware filtering**: `player_features.py` aggregates minutes by active position group before applying the 180-minute visibility threshold and 600-minute full-confidence threshold. Minutes outside the group do not count.
- **Percentile columns**: Each metric has `{metric}_league_pct` (within-league, permanent; merge input and debugging only) and `{metric}_pct` (league-anchored cross-league rank, overwritten by the merge step). The dashboard uses only the `_pct` set — there is no percentile-mode toggle.
- **Role scoring**: Role scores are weighted averages of percentile ranks. All weights sum to 1.0 (enforced by test). Percentiles are computed within the active position group.
- **Team scoring**: `team_rating` is a global percentile rank of minutes-weighted latent z from player `overall_score`. There is no fixed position-group weighting. `low_coverage` is a flag only; teams are not dropped for coverage.
- **Performance delta**: `perf_delta_rank = league_rank_points - league_rank_rating`. Negative means results are ahead of squad-quality rank; positive means results lag rating rank.
- **Composite weights** (`config.POSITION_GROUPS[*]["composite_weights"]`) are domain-driven. Do not change them without a specific reason.
- **`DataLoader._CANDIDATE_PATHS`**: Adding a new player output file format → append to this list. Do not add new `if path.exists()` branches.
- **Raw event CSVs** (`data/events/`) are gitignored; processed and final data are committed.
- **`last_updated.txt`**: Written by player/merge/team feature runs. Read by `DataLoader.load_last_updated()` and displayed as `st.info` in `app.py`.

### Test Coverage
Tests cover: qualifier parsing, qualifier casing regression (Throughball/Longball/IntentionalAssist), position-aware minutes filtering, per-90 arithmetic, carry inference, half-space pass detection, possession-won zone flags, ball-winning height accumulation, composite score integrity, role weight sums (all must equal 1.0), role score output range (0–100), primary role validity, league-strength offsets, and team-feature aggregation.
