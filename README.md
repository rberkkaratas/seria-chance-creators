# Serie A Midfielder Scouting Tool 2025/26
### A Data-Driven Role-Based Profiling Framework

A scouting tool that profiles midfielders in Serie A across six tactical roles using WhoScored match event data. The pipeline extracts per-match events, engineers 20+ per-90 and rate metrics, assigns role scores (0–100) for each player across all roles, and presents findings through an interactive Streamlit dashboard.

**Live app:** [seria-chance-creators.streamlit.app](https://seria-chance-creators.streamlit.app/)

## Project Structure

```
seria-chance-creators/
├── config.py                  # Central config (paths, filters, metrics, role weights)
├── requirements.txt
│
├── src/
│   ├── scraper/
│   │   └── whoscored_extractor.py   # Match ID → event CSV (SeleniumBase UC mode)
│   ├── processing/
│   │   └── build_tables.py          # Event CSVs → matches, players, teams tables
│   ├── features/
│   │   ├── chance_creation.py       # Per-90 metrics, percentiles, role scores
│   │   └── clustering.py            # K-Means style clustering (optional)
│   ├── enrichment/
│   │   └── transfermarkt.py         # Market value, contract & feasibility (SeleniumBase)
│   └── visualization/
│       ├── radar.py                 # Radar charts & comparison plots
│       └── scatter_profiles.py      # Quadrant scatter plots for Statistical Profiles tab
│
├── data/
│   ├── events/Serie_A/2025-2026/    # Per-match event CSVs from WhoScored (gitignored)
│   ├── processed/                   # Aggregated tables (matches, players, teams)
│   ├── enrichment/                  # TM squad cache, player mapping, manual overrides
│   └── final/                       # Feature-engineered datasets ready for the app
│
├── notebooks/
│   ├── 01_exploration.ipynb         # EDA & prototyping
│   └── 02_data_testing.ipynb        # Data quality checks & sanity validation
│
├── streamlit/
│   └── app.py                       # Interactive scouting dashboard
│
├── tests/
│   ├── test_build_tables.py         # Unit tests for event parsing & enrichment flags
│   └── test_chance_creation.py      # Unit tests for feature engineering & role scoring
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
    → Feature Engineering   (per-90, percentiles, 6 role scores, primary_role)
    → Clustering            (K-Means style sub-groups)              [optional]
    → TM Enrichment         (market value, contract, feasibility)   [optional]
    → Streamlit Dashboard
```

## Six Midfielder Roles

Each player receives a 0–100 score for every role. `primary_role` is the role with their highest score.

| Role | Key metrics |
|------|-------------|
| **Playmaker** | Key passes, through balls, passes into box, shot-creating actions, assists |
| **Ball Progressor** | Progressive passes, passes into final third, pass accuracy, pass volume |
| **Ball Winner** | Possession won, tackles, interceptions, tackle success rate |
| **Defensive Shield** | Clearances, blocks, aerial duels, aerial win rate |
| **Dribbler** | Successful dribbles, dribble success rate, shot-creating actions |
| **Wide Creator** | Crosses, cross accuracy, passes into box |

Role scores are computed as a weighted average of per-metric percentile ranks within the filtered midfielder group.

## Dashboard Tabs

| Tab | What it shows |
|-----|---------------|
| **Rankings** | All midfielders ranked by any role score or metric; bars colored by primary role |
| **Player Profile** | Header with role badge, role ratings bar chart, chance-creation radar, season totals |
| **Compare** | Side-by-side radar & grouped bar chart for up to 4 players |
| **Scatter Explorer** | Free-axis scatter colored by primary role with quadrant shading |
| **Roles** | Role distribution donut, 6×6 role-score heatmap, per-role player tables |
| **Statistical Profiles** | 7 quadrant scatter plots (Passing, Pass Patterns, Aerial Duels, Defence, Possession, Tackling, Crossing) in a 2-column expandable grid |

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/rberkkaratas/seria-chance-creators.git
cd seria-chance-creators
pip install -r requirements.txt

# 2. Extract event data (WhoScored match IDs)
python -m src.scraper.whoscored_extractor --ids 1829473 1829474 1829475
# or from a CSV:
python -m src.scraper.whoscored_extractor --csv data/match_ids.csv

# 3. Build normalized tables
python -m src.processing.build_tables

# 4. Engineer features & role scores
python -m src.features.chance_creation

# 5. (optional) K-Means style clustering
python -m src.features.clustering

# 6. (optional) Enrich with Transfermarkt data — opens a browser
python -m src.enrichment.transfermarkt

# 7. Launch dashboard
streamlit run streamlit/app.py
```

## Tests

```bash
pytest tests/ -v
```

67 tests covering: event qualifier parsing (WhoScored displayName casing regression guards), position-aware minutes filter, per-90 calculations, carry and half-space detection, possession-won zone flags, ball-winning height accumulation, composite score integrity, role weight integrity, role score output range, and primary role validity.

## Data Sources

| Source | What it provides |
|--------|-----------------|
| [WhoScored](https://www.whoscored.com/) | Match event data for Serie A 2025/26 — extracted per-match via SeleniumBase |
| [Transfermarkt](https://www.transfermarkt.com/) | Market value, contract expiry, transfer feasibility — scraped from team squad pages |

This project is for personal educational and portfolio purposes only.

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/methodology.md](docs/methodology.md) | Feature selection, role scoring, normalization, clustering, TM enrichment, limitations |
| [docs/usage.md](docs/usage.md) | Streamlit dashboard user guide |

## Author

**R. Berk Karatas** — Aspiring Football Performance Analyst
- [LinkedIn](https://www.linkedin.com/in/rberkkaratas/)
- [GitHub](https://github.com/rberkkaratas)
- rberkk@protonmail.com
