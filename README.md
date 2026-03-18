# Midfielder Scout 2025/26
### A Role-Based Profiling System for the Top 5 European Leagues

Traditional scouting starts with a name. Someone watches a match, sees a midfielder they like, and a report gets written. This project starts from the opposite direction — it asks: *across 400+ qualified midfielders in Europe's top five leagues, who actually fits the role you need?*

Built on WhoScored match event data, the pipeline extracts every pass, carry, dribble and tackle from every match, engineers 30+ per-90 and rate metrics, and produces a 0–100 role score for each player across four tactical profiles. The result is a live scouting dashboard where a sporting director can filter by role, age, market value, and transfer feasibility — and arrive at a ranked, data-backed shortlist before a single video is pulled.

**Live app:** [seria-chance-creators.streamlit.app](https://seria-chance-creators.streamlit.app/)

---

## The Four Roles

Every player is scored 0–100 on each role. `primary_role` is the profile where they score highest. All weights are defined in `config.ROLE_WEIGHTS` — transparent, configurable, summing to 1.0.

| Role | The Player You Are Looking For | Key metrics |
|------|-------------------------------|-------------|
| **Creator** | Delivers into dangerous areas — central key passes, crosses, through balls, assists | passes_into_box (30%), key_passes (25%), assists (20%), crosses (15%), through_balls (10%) |
| **Ball Progressor** | Drives forward by carrying and dribbling — crosses the final-third line with the ball | carries_into_final_third (40%), successful_dribbles (30%), progressive_passes (20%), progressive_carries (10%) |
| **Box Threat** | Lives in the penalty area — shoots, creates from proximity, threatens directly | penalty_area_touches (40%), shots (35%), final_third_touches (15%), passes_into_box (10%) |
| **Deep Builder** | Enables through volume and precision — progressive passing, directional intent, accuracy | progressive_passes (35%), pass_accuracy (25%), total_passes (20%), forward_pass_% (10%), key_passes (10%) |

The **Overall Score** is a weighted blend of the four role scores: Creator 35% · Ball Progressor 25% · Box Threat 25% · Deep Builder 15%.

---

## How It Works

The system is two parts: an offline data pipeline and a Streamlit dashboard that reads the result.

```
WhoScored fixture pages
    → Fixture Scraper       →  data/match_ids/{league}_{season}.csv
    → WhoScored Extractor   →  data/events/{league}/{season}/*.csv
    → Build Tables          →  data/processed/{league}/{season}/
    → Feature Engineering   →  data/final/{league}_{season}.csv
    → Merge Leagues         →  data/final/all_leagues_{season}.csv
    → TM Enrichment         →  market value · contract · feasibility  [optional]
    → Streamlit Dashboard
```

Every stage is autonomous — re-run any step without repeating earlier ones. Intermediate files are committed so the dashboard works out of the box without re-scraping.

### Dual Percentile Modes

Role scores and radar charts are computed in two modes, toggleable in the filter panel:

| Mode | Scope | Question it answers |
|------|-------|---------------------|
| **All leagues** | ~420 qualified midfielders across 5 leagues | How does this player rank in Europe? |
| **Within league** | Players in the same league only | How does this player rank among his direct peers? |

---

## Project Structure

```
seria-chance-creators/
├── config.py                        # Single source of truth: paths, leagues, role weights, metrics
├── requirements.txt
│
├── src/
│   ├── scraper/
│   │   ├── fixture_scraper.py       # WhoScored fixture page → match ID manifest CSV
│   │   └── whoscored_extractor.py   # Match IDs → per-match event CSVs (SeleniumBase UC mode)
│   ├── processing/
│   │   └── build_tables.py          # Event CSVs → matches · players · teams tables
│   ├── features/
│   │   ├── chance_creation.py       # Per-90, percentiles, role scores — per league
│   │   ├── merge_leagues.py         # Cross-league global percentiles + merged dataset
│   │   └── clustering.py            # K-Means sub-groups (optional)
│   ├── enrichment/
│   │   └── transfermarkt.py         # Market value, contract expiry, transfer feasibility
│   └── visualization/
│       ├── radar.py                 # Single-player and comparison radar charts
│       └── scatter_profiles.py      # Quadrant scatter plots with median dividers
│
├── data/
│   ├── events/{league}/{season}/    # Raw per-match event CSVs  (gitignored)
│   ├── match_ids/                   # Fixture manifests with scraped/pending status
│   ├── processed/{league}/{season}/ # Normalised matches · players · teams tables
│   ├── enrichment/                  # TM cache, player name mapping, manual overrides
│   └── final/
│       ├── {league}_{season}.csv              # Per-league feature-engineered output
│       ├── all_leagues_{season}.csv           # Merged 5-league dataset (dashboard source)
│       ├── all_leagues_{season}_enriched.csv  # + Transfermarkt data
│       └── last_updated.txt                   # ISO date written after each pipeline run
│
├── streamlit/
│   ├── app.py                       # Entry point — data loading, filters, tab routing
│   ├── core/                        # DataLoader, FilterService, AppState, constants, theme
│   ├── components/                  # CSS, inline filter panel, header banner
│   └── tabs/                        # One file per tab — all implement TabRenderer ABC
│
├── tests/
│   ├── test_build_tables.py         # Qualifier parsing, event enrichment, assist detection
│   └── test_chance_creation.py      # Position-aware filter, per-90 math, role scoring
│
└── docs/
    ├── methodology.md               # Metric design, role definitions, and known limitations
    └── usage.md                     # Dashboard walkthrough and scouting workflow
```

---

## Running the Pipeline

### All leagues at once

```bash
# 1. Collect match IDs from fixture pages
python -m src.scraper.fixture_scraper --league all --season 2025-2026

# 2. Scrape event data from all manifests (SeleniumBase — browser must be installed)
python -m src.scraper.whoscored_extractor --league all --season 2025-2026 --manifest

# 3. Build player / match / team tables from raw event CSVs
python -m src.processing.build_tables --league all --season 2025-2026

# 4. Feature engineering + auto-merge → all_leagues_2025-2026.csv
python -m src.features.chance_creation --league all --season 2025-2026
```

### Single league update

Update one league, then re-merge to refresh the combined dataset:

```bash
python -m src.scraper.fixture_scraper --league Bundesliga --season 2025-2026
python -m src.scraper.whoscored_extractor --league Bundesliga --season 2025-2026 --manifest
python -m src.processing.build_tables --league Bundesliga --season 2025-2026
python -m src.features.chance_creation --league Bundesliga --season 2025-2026
python -m src.features.merge_leagues --season 2025-2026
```

Valid league keys: `Serie_A` · `Premier_League` · `La_Liga` · `Bundesliga` · `Ligue_1`

### Optional steps

```bash
# Transfermarkt enrichment — market value, contract expiry, transfer feasibility
python -m src.enrichment.transfermarkt

# K-Means sub-group clustering (supplementary — not required by the dashboard)
python -m src.features.clustering
```

### Launch the dashboard

```bash
streamlit run streamlit/app.py
```

The app tries data files in priority order: `all_leagues_{season}_enriched.csv` → `all_leagues_{season}.csv` → legacy Serie A fallbacks. It also displays the date from `last_updated.txt` as an info banner — written automatically after every pipeline run.

### New season setup

WhoScored fixture URLs contain season-specific IDs. Update once per season in `config.py`:

```python
LEAGUES = {
    "Serie_A":        {"fixture_url": "https://www.whoscored.com/regions/108/..."},
    "Premier_League": {"fixture_url": "https://www.whoscored.com/regions/252/..."},
    "La_Liga":        {"fixture_url": "https://www.whoscored.com/regions/206/..."},
    "Bundesliga":     {"fixture_url": "https://www.whoscored.com/regions/81/..."},
    "Ligue_1":        {"fixture_url": "https://www.whoscored.com/regions/74/..."},
}
```

---

## Dashboard

Filters sit in an inline four-column panel at the top of every page and apply across all tabs simultaneously: min. minutes · age range · market value · positions · roles · leagues · teams · percentile mode · transfer feasibility.

| Tab | What you get |
|-----|-------------|
| **📊 Shortlist** | Sort by Overall Score or any role score. Podium cards for the top 3. Top-25 bar chart coloured by primary role with an average reference line — click any bar to jump directly to that player's Scout Report. Full ranked table with role score columns and optional TM data. |
| **⚡ Role Map** | Four role cards showing metric weight bars, player count, and avg score per role. Role distribution donut. 4×4 Versatility Matrix heatmap (how each role group scores across all four roles). Role DNA heatmap (avg metric percentile per role group). Role Share by League stacked bar (which leagues over-index on each role). Top 8 players per role with score bars, grouped by pitch zone. Role Score vs Market Value scatter when TM data is available. |
| **👤 Scout Report** | Player header with global + league rank, score, role, TM data. Radar chart (8 metrics, percentile + raw value on hover). Per-90 bars vs dataset maximum. Four role-score bars. Season stat cards. Full match log — bars coloured by result, goals/assists annotated, scrollable per-match table. |
| **🔍 Compare** | Select 2–4 players from the full dataset (sidebar filters don't restrict the pool). Overlay radar, grouped per-90 bar chart, and transposed stats table. Supports cross-league comparison. |
| **📈 Explore** | **Lens Explorer** — five preset scouting lenses (Creator, Ball Progressor, Box Threat, Deep Builder, Wide Creator) plus Custom. Spotlight any player by surname. Quadrant fills, median lines, top-5 annotations, lens insight callout, top-10 table. **Statistical Profiles** — seven fixed scatter plots across key dimensions (Passing, Progressive Intent, Aerial Presence, Defensive Contribution, Possession Battle, Tackling, Crossing), displayed in a 2-column grid with insight callouts. |
| **🌍 League Overview** | League identity cards (dominant role, player count, avg score, avg market value). Role Fingerprint heatmap (★ marks top league per role). League vs League grouped bar chart. Best-in-Class table (top player per role per league). Age profile box plots. Market value bar + median scatter. |

---

## Tests

```bash
pytest tests/ -v
```

67 tests covering: WhoScored qualifier display-name casing (regression guards for `"Throughball"`, `"Longball"`, `"IntentionalAssist"`), position-aware minutes filter, per-90 arithmetic, carry inference, half-space pass detection, possession-won zone flags, ball-winning height accumulation, composite score integrity, role weight sums (all must equal 1.0), role score output range (0–100), and primary role validity.

---

## Data Sources

| Source | What it provides |
|--------|-----------------|
| [WhoScored](https://www.whoscored.com/) | Match event data — all 5 leagues, 2025/26, extracted per match via SeleniumBase UC mode |
| [Transfermarkt](https://www.transfermarkt.com/) | Market value, contract expiry, transfer feasibility — scraped from squad pages, cached locally |

This project is for personal educational and portfolio purposes only.

---

## Author

**R. Berk Karatas** — Aspiring Football Performance Analyst
- [LinkedIn](https://www.linkedin.com/in/rberkkaratas/)
- [GitHub](https://github.com/rberkkaratas)
- rberkk@protonmail.com
