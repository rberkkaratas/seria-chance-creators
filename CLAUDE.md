# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Serie A Chance Creators is a football analytics scouting tool that identifies elite chance-creating midfielders in Serie A 2025/26 using WhoScored match event data. It is a two-part system: a data pipeline (scraping → processing → feature engineering → clustering) and a Streamlit web dashboard.

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

# 3. Engineer features (per-90, percentiles, composite score)
python -m src.features.chance_creation

# 4. Cluster players into archetypes (optional)
python -m src.features.clustering

# 5. Launch the dashboard
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
  → src/features/clustering.py           → data/final/chance_creators_clustered.csv
  → streamlit/app.py                     (dashboard reads the final CSV)
```

### Key Modules

- **`config.py`** — Central configuration: data paths, player filters (900+ min, midfield positions), WhoScored qualifier IDs, 7 chance-creation metrics, composite score weights, clustering settings (k=3). Change filters or weights here only.

- **`src/scraper/whoscored_extractor.py`** — Uses SeleniumBase UC mode to bypass WhoScored anti-bot. Extracts `matchCentreData` JSON from page HTML, outputs per-match event CSVs and player metadata CSVs.

- **`src/processing/build_tables.py`** — Parses WhoScored qualifier lists (note: casing bugs in the source data, e.g. `"Throughball"` not `"ThroughBall"`). Enriches events with boolean flags (key pass, assist, through ball, progressive pass, pass into box, etc.) using x/y coordinates and qualifier IDs. Aggregates to player-match level.

- **`src/features/chance_creation.py`** — Filters midfielders using **position-aware minutes** (only midfield appearances count toward the 900-min threshold, not total minutes across all positions). Computes per-90 rates, percentile ranks, and a weighted composite score.

- **`src/features/clustering.py`** — Standardizes features, fits K-Means (k=3), assigns archetype labels: "Final-Ball Specialist", "Progressive Carrier", "Volume Creator".

- **`src/visualization/radar.py`** — Dark-themed Plotly radar charts. `create_radar_chart()` for single-player profiles; `create_comparison_radar()` for multi-player overlays.

- **`streamlit/app.py`** — Loads `chance_creators_clustered.csv` if available, else `chance_creators.csv`. Sidebar filters apply globally. Five dashboard tabs: Rankings, Player Profile, Compare, Scatter Explorer, Archetypes.

### Important Implementation Details

- **Qualifier parsing**: WhoScored qualifier casing is inconsistent and undocumented. Tests in `tests/test_build_tables.py` document the confirmed casings as regression tests — don't change them without verifying against raw data.
- **Position-aware filtering**: The filter in `chance_creation.py` aggregates minutes per position before applying the threshold. A bug previously counted all-position minutes (test `test_filter_midfielders_position_aware` guards this).
- **Composite weights** are domain-driven (not data-driven) and defined in `config.COMPOSITE_WEIGHTS`. Current weights: key passes 25%, SCA 20%, box passes 15%, through balls 15%, progressive passes 10%, assist-pass % 10%, dribble success 5%.
- **Raw event CSVs** (`data/events/`) are gitignored; only processed data is committed.
