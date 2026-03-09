# Identifying Elite Chance Creators in Serie A 2025/26
### A Data-Driven Scouting Framework

A scouting tool that identifies and profiles creative midfielders in Serie A using match event data from WhoScored. The pipeline extracts per-match event data, engineers chance-creation features, clusters players into creative archetypes, and presents findings through an interactive Streamlit dashboard.

## Project Structure

```
seria-chance-creators/
├── config.py                  # Central configuration (seasons, thresholds, paths)
├── requirements.txt
│
├── src/
│   ├── scraper/
│   │   └── whoscored_extractor.py   # Match ID → event CSV extraction (SeleniumBase)
│   ├── processing/
│   │   └── build_tables.py          # Event CSVs → matches, players, teams tables
│   ├── features/
│   │   ├── chance_creation.py       # Per-90 metrics, percentiles, composite scores
│   │   └── clustering.py            # K-means archetype clustering
│   ├── enrichment/
│   │   └── transfermarkt.py         # Market value, contract & feasibility (SeleniumBase)
│   └── visualization/
│       └── radar.py                 # Radar charts & comparison plots
│
├── data/
│   ├── events/Serie_A/2025-2026/    # Per-match event CSVs from WhoScored
│   ├── processed/                   # Aggregated tables (matches, players, teams)
│   ├── enrichment/                  # TM squad cache, player mapping, manual overrides
│   └── final/                       # Feature-engineered datasets ready for app
│
├── notebooks/
│   ├── 01_exploration.ipynb         # EDA & prototyping
│   └── 02_data_testing.ipynb        # Data quality checks & sanity validation
│
├── streamlit/
│   └── app.py                       # Interactive scouting dashboard (single-page)
│
├── tests/
│   ├── test_build_tables.py         # Unit tests for event parsing & enrichment
│   └── test_chance_creation.py      # Unit tests for feature engineering pipeline
│
└── docs/
    ├── methodology.md               # Approach, decisions, and limitations
    └── usage.md                     # Streamlit dashboard user guide
```

## Pipeline Overview

```
Match IDs (manual input)
    → WhoScored Extractor   (SeleniumBase UC mode)
    → Per-match Event CSVs
    → Build Tables          (matches / players / teams)
    → Feature Engineering   (per-90, percentiles, composite score)
    → Clustering            (K-Means creative archetypes)          [optional]
    → TM Enrichment         (market value, contract, feasibility)  [optional]
    → Streamlit Dashboard
```

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/rberkkaratas/seria-chance-creators.git
cd seria-chance-creators
pip install -r requirements.txt

# 2. Extract event data (provide WhoScored match IDs)
python -m src.scraper.whoscored_extractor --ids 1829473 1829474 1829475
# Or from a CSV file:
python -m src.scraper.whoscored_extractor --csv data/match_ids.csv

# 3. Build normalized tables from event CSVs
python -m src.processing.build_tables

# 4. Engineer features & cluster
python -m src.features.chance_creation
python -m src.features.clustering          # optional

# 5. Enrich with Transfermarkt data
python -m src.enrichment.transfermarkt     # optional — opens a browser, ~2 min
# Re-scrape on season refresh:
# python -m src.enrichment.transfermarkt --refresh

# 6. Launch dashboard
streamlit run streamlit/app.py
```

## Tests

```bash
pytest tests/ -v
```

38 tests covering event qualifier parsing (including regression guards for the WhoScored displayName casing bugs), the position-aware minutes filter, per-90 calculations, and composite score integrity.

## Data Sources

| Source | What it provides |
|--------|-----------------|
| [WhoScored](https://www.whoscored.com/) | Match event data for Serie A 2025/26 — extracted per-match via SeleniumBase |
| [Transfermarkt](https://www.transfermarkt.com/) | Market value, contract expiry, transfer feasibility — scraped from team squad pages |

This project is for personal educational and portfolio purposes only.

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/methodology.md](docs/methodology.md) | Feature selection, normalization, clustering, TM enrichment, limitations |
| [docs/usage.md](docs/usage.md) | Streamlit dashboard user guide |

## Author

**R. Berk Karatas** — Aspiring Football Performance Analyst
- [LinkedIn](https://www.linkedin.com/in/rberkkaratas/)
- [GitHub](https://github.com/rberkkaratas)
- rberkk@protonmail.com
