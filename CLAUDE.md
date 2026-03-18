# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A football analytics scouting tool that profiles qualified midfielders across the **top 5 European leagues** (Serie A, Premier League, La Liga, Bundesliga, Ligue 1) for the 2025/26 season. Each player receives a 0–100 score for four tactical roles — Creator, Ball Progressor, Box Threat, Deep Builder — plus a `primary_role` assignment and a legacy composite `chance_creation_score`. The system is two parts: an offline data pipeline (scrape → process → feature engineer → merge → enrich) and a Streamlit web dashboard.

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

# 4. Engineer features — per-90, percentiles, role scores, primary_role
#    --league all also triggers merge_leagues automatically
python -m src.features.chance_creation --league all --season 2025-2026

# 5. Enrich with Transfermarkt data — market value, contract, feasibility (optional)
python -m src.enrichment.transfermarkt

# 6. Launch the dashboard
streamlit run streamlit/app.py
```

### Single league update + re-merge
```bash
python -m src.features.chance_creation --league Bundesliga --season 2025-2026
python -m src.features.merge_leagues --season 2025-2026
```

### Tests
```bash
pytest tests/ -v
# Run a single test file:
pytest tests/test_build_tables.py -v
# Run a single test:
pytest tests/test_chance_creation.py::test_filter_midfielders_position_aware -v
```

## Architecture

### Data Flow
```
WhoScored fixture pages
  → src/scraper/fixture_scraper.py         → data/match_ids/{league}_{season}.csv
  → src/scraper/whoscored_extractor.py     → data/events/{league}/{season}/*.csv
  → src/processing/build_tables.py         → data/processed/{league}/{season}/
  → src/features/chance_creation.py        → data/final/{league}_{season}.csv
  → src/features/merge_leagues.py          → data/final/all_leagues_{season}.csv
  → src/enrichment/transfermarkt.py        → data/final/all_leagues_{season}_enriched.csv
  → streamlit/app.py                       (dashboard reads highest-priority file from data/final/)
```

### Key Modules

- **`config.py`** — Central configuration: data paths, league definitions, player filters (600+ midfield min), WhoScored qualifier IDs, CHANCE_CREATION_METRICS, composite score weights, `ROLE_WEIGHTS` (4 roles × weighted metrics: Creator, Ball Progressor, Box Threat, Deep Builder), `ROLE_COLORS`, `ROLE_SCORE_COL_PREFIX`, `PRIMARY_ROLE_COL`. All role definitions live here. Adding or changing a role → update `config.ROLE_WEIGHTS` only.

- **`src/scraper/fixture_scraper.py`** — Extracts match IDs from WhoScored fixture pages. Outputs manifest CSVs to `data/match_ids/`. Supports `--league all`.

- **`src/scraper/whoscored_extractor.py`** — Uses SeleniumBase UC mode to bypass WhoScored anti-bot. Extracts `matchCentreData` JSON from page HTML. Dual regex strategies for JSON extraction. Outputs per-match event CSVs and player metadata CSVs. Supports manifest-based scraping (reads match_ids CSV, marks scraped=True after success).

- **`src/processing/build_tables.py`** — Parses WhoScored qualifier lists.
  - **Qualifier casing is critical**: WhoScored displayNames are inconsistent and undocumented. Named constants (`_Q_THROUGH_BALL`, `_Q_LONG_BALL`, `_Q_INTENTIONAL_ASSIST`, etc.) are defined at the top of the file. Tests in `tests/test_build_tables.py` document confirmed casings as regression guards — do not change them without verifying against raw data.
  - Enriches events with boolean flags: key pass, assist, through ball, progressive pass, pass into box, forward pass, half-space pass, penalty area touch, carry into final third, cross, tackle success, aerial total, shots blocked, possession won (total and final-third), ball-winning height.
  - Aggregates to player-match level. Outputs to `data/processed/{league}/{season}/`.

- **`src/features/chance_creation.py`** — Filters midfielders using **position-aware minutes** (only midfield appearances count toward the 600-min threshold — a bug previously counted all-position minutes; tests `test_filter_midfielders_*` guard this). Computes per-90 rates and rate stats. Computes percentile ranks within the league. Runs `compute_role_scores()` which scores each player 0–100 on all 6 roles and assigns `primary_role`. Writes `last_updated.txt` after saving.

- **`src/features/merge_leagues.py`** — Concatenates per-league CSVs, overwrites `{metric}_pct` with global (cross-league) percentile ranks (preserving `{metric}_league_pct`), recomputes global role scores, and renames per-league role columns to `{col}_league`. Writes `last_updated.txt` after saving.

- **`src/enrichment/transfermarkt.py`** — Scrapes market value, contract expiry, and transfer feasibility from Transfermarkt squad pages. Uses a local cache (`data/enrichment/tm_squads_cache.csv`) and persistent name-matching results (`data/enrichment/tm_player_mapping.csv`). Manual overrides in `data/enrichment/tm_manual_players.csv`.

- **`src/visualization/radar.py`** — Dark-themed Plotly radar charts. `create_radar_chart()` for single-player profiles; `create_comparison_radar()` for multi-player overlays.

- **`src/visualization/scatter_profiles.py`** — Quadrant scatter plots for the Statistical Profiles and Free Explore views.

- **`streamlit/app.py`** — Entry point. Loads data (fallback chain: enriched → merged → legacy), displays `last_updated.txt` as st.info, applies sidebar filters globally, renders 6 tabs.

- **`streamlit/core/data_loader.py`** — `DataLoader._CANDIDATE_PATHS` is a priority-ordered list of CSV paths; `load()` returns the first one that exists. `load_raw()` reads per-match player stats from all processed dirs. `load_last_updated()` reads `data/final/last_updated.txt`.

- **`streamlit/core/filter_service.py`** — `FilterService.apply()` applies UI filters to the DataFrame; `FilterService.build_app_state()` constructs the `AppState` view model from filtered data.

- **`streamlit/core/models.py`** — `FilterState` and `AppState` dataclasses. `AppState` is the shared context passed to all tab renderers.

- **`streamlit/tabs/__init__.py`** — `TabRenderer` abstract base class. All tab classes implement `render(state: AppState)`.

### The Four Roles (config.ROLE_WEIGHTS)
- **Creator** — passes_into_penalty_area_p90 (30%), key_passes_p90 (25%), assists_p90 (20%), crosses_p90 (15%), through_balls_p90 (10%)
- **Ball Progressor** — carries_into_final_third_p90 (40%), successful_dribbles_p90 (30%), progressive_passes_p90 (20%), progressive_carries_p90 (10%)
- **Box Threat** — penalty_area_touches_p90 (40%), shots_p90 (35%), touches_final_third_p90 (15%), passes_into_penalty_area_p90 (10%)
- **Deep Builder** — progressive_passes_p90 (35%), pass_accuracy (25%), total_passes_p90 (20%), forward_pass_pct (10%), key_passes_p90 (10%)

### Important Implementation Details

- **Qualifier naming constants**: `build_tables.py` defines module-level constants (`_Q_KEY_PASS`, `_Q_THROUGH_BALL`, `_Q_LONG_BALL`, `_Q_CROSS`, `_Q_INTENTIONAL_ASSIST`) for all WhoScored displayName strings. Never use raw strings in new qualifier checks — add a constant.
- **Assist detection dual-path**: Primary signal is event-type 92 in `satisfiedEventsTypes` (pass directly preceded a goal). Fallback to `IntentionalAssist` qualifier only when `satisfiedEventsTypes` is absent (unit test context). Do not use `IntentionalAssist` as the primary signal — it appears on all key passes, not just those that led to goals.
- **Position-aware filtering**: `chance_creation.py` aggregates minutes per position before applying the 600-min threshold. Tests `test_filter_midfielders_*` guard this invariant.
- **Dual percentile columns**: Each metric has `{metric}_league_pct` (within-league, permanent) and `{metric}_pct` (global, overwritten by merge step). The dashboard sidebar toggle controls which set is used.
- **Role scoring**: Role scores are weighted averages of percentile ranks. All weights sum to 1.0 (enforced by test). All percentiles are computed within the filtered midfielder group.
- **Composite weights** (`config.COMPOSITE_WEIGHTS`) are domain-driven and retained for backward compatibility (radar charts, legacy CSV). Do not change them without a specific reason.
- **`DataLoader._CANDIDATE_PATHS`**: Adding a new output file format → append to this list. Do not add new `if path.exists()` branches.
- **Raw event CSVs** (`data/events/`) are gitignored; processed and final data are committed.
- **`last_updated.txt`**: Written by `chance_creation.py` and `merge_leagues.py` after each pipeline run. Read by `DataLoader.load_last_updated()` and displayed as `st.info` in `app.py`.

### Test Coverage (67 tests)
Tests cover: qualifier parsing, qualifier casing regression (Throughball/Longball/IntentionalAssist), position-aware minutes filter, per-90 arithmetic, carry inference, half-space pass detection, possession-won zone flags, ball-winning height accumulation, composite score integrity, role weight sums (all must equal 1.0), role score output range (0–100), and primary role validity.
