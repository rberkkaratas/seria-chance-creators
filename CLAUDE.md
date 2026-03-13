# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Serie A Midfielder Scouting Tool is a football analytics dashboard that profiles all qualified midfielders in Serie A 2025/26 across **six tactical roles** using WhoScored match event data. Each player receives a 0–100 score for every role (Playmaker, Ball Progressor, Ball Winner, Defensive Shield, Dribbler, Wide Creator) plus a `primary_role` assignment. It is a two-part system: a data pipeline (scraping → processing → feature engineering) and a Streamlit web dashboard.

## Commands

### Setup
```bash
pip install -r requirements.txt
```

### Run the pipeline (in order)
```bash
# 1. Scrape match events from WhoScored
python -m src.scraper.whoscored_extractor --ids 1829473 1829474
# or from a CSV of match IDs:
python -m src.scraper.whoscored_extractor --csv data/match_ids.csv

# 2. Build normalized tables from raw event CSVs
python -m src.processing.build_tables

# 3. Engineer features — per-90, percentiles, role scores, primary_role
python -m src.features.chance_creation

# 4. K-Means style sub-clustering (optional)
python -m src.features.clustering

# 5. Enrich with Transfermarkt data — market value, contract, feasibility (optional)
python -m src.enrichment.transfermarkt

# 6. Launch the dashboard
streamlit run streamlit/app.py
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
WhoScored match IDs
  → src/scraper/whoscored_extractor.py   → data/events/Serie_A/2025-2026/*.csv
  → src/processing/build_tables.py       → data/processed/{matches,players,teams}.csv
  → src/features/chance_creation.py      → data/final/chance_creators.csv
  → src/features/clustering.py           → data/final/chance_creators_clustered.csv  [optional]
  → src/enrichment/transfermarkt.py      → data/final/chance_creators_enriched.csv  [optional]
  → streamlit/app.py                     (dashboard reads the final CSV; prefers enriched)
```

### Key Modules

- **`config.py`** — Central configuration: data paths, player filters (600+ midfield min), WhoScored qualifier IDs, 6 chance-creation metrics, composite score weights, `ROLE_WEIGHTS` (6 roles × weighted metrics), `ROLE_COLORS`, `ROLE_SCORE_COL_PREFIX`, `PRIMARY_ROLE_COL`. All role definitions live here.

- **`src/scraper/whoscored_extractor.py`** — Uses SeleniumBase UC mode to bypass WhoScored anti-bot. Extracts `matchCentreData` JSON from page HTML, outputs per-match event CSVs and player metadata CSVs.

- **`src/processing/build_tables.py`** — Parses WhoScored qualifier lists (note: casing bugs in source data, e.g. `"Throughball"` not `"ThroughBall"`). Enriches events with boolean flags: key pass, assist, through ball, progressive pass, pass into box, forward pass, half-space pass, penalty area touch, carry into final third, cross, cross success, tackle success, aerial total, shots blocked, possession won (total and final-third), ball-winning height. Aggregates to player-match level.

- **`src/features/chance_creation.py`** — Filters midfielders using **position-aware minutes** (only midfield appearances count toward the 600-min threshold). Computes per-90 rates and rate stats (pass accuracy, aerial win rate, forward pass %, dribble success rate, ball-winning height). Computes percentile ranks for all metrics needed by any role. Runs `compute_role_scores()` which scores each player 0–100 on all 6 roles and assigns `primary_role`. Also produces the legacy `chance_creation_score` composite.

- **`src/features/clustering.py`** — Standardizes features, fits K-Means (k=3), assigns legacy archetype labels. Now optional/supplementary — roles are the primary classification.

- **`src/visualization/radar.py`** — Dark-themed Plotly radar charts. `create_radar_chart()` for single-player profiles; `create_comparison_radar()` for multi-player overlays.

- **`src/visualization/scatter_profiles.py`** — Quadrant scatter plots for the Statistical Profiles tab. `create_quadrant_scatter()` renders all 7 plots with dark background, solid median lines, corner labels (green = best quadrant, amber = others), and blue pill-badge annotations for top players. `get_best_quadrant_df()` returns the top players in the best quadrant.

- **`streamlit/app.py`** — Loads `chance_creators_enriched.csv` → `chance_creators_clustered.csv` → `chance_creators.csv` in that order. Sidebar filters apply globally including a Role filter. Six tabs: Rankings, Player Profile, Compare, Scatter Explorer, Roles, Statistical Profiles.

### Important Implementation Details

- **Qualifier parsing**: WhoScored qualifier casing is inconsistent and undocumented. Tests in `tests/test_build_tables.py` document confirmed casings as regression tests — don't change them without verifying against raw data.
- **Position-aware filtering**: `chance_creation.py` aggregates minutes per position before applying the 600-min threshold. A bug previously counted all-position minutes (tests `test_filter_midfielders_*` guard this).
- **Role scoring**: Role scores are weighted averages of percentile ranks. All percentiles are computed within the filtered midfielder group (not the whole dataset). Adding or changing a role → update `config.ROLE_WEIGHTS` only.
- **Composite weights** (`config.COMPOSITE_WEIGHTS`) are domain-driven and kept for backward compatibility (radar charts, legacy CSV). Do not change them without a specific reason.
- **Statistical Profiles plots**: All 7 scatter metrics must exist in the final CSV. If a plot shows a "missing columns" warning, re-run `build_tables` + `chance_creation` to regenerate.
- **Raw event CSVs** (`data/events/`) are gitignored; only processed and final data are committed.
- **Test count**: 67 tests covering qualifier parsing, position-aware filter, per-90 math, carry/half-space/possession-zone/ball-winning-height detection, composite score, role weight integrity, role score range, and primary role validity.
