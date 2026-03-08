# Dashboard Usage Guide

## Launching the App

```bash
streamlit run streamlit/app.py
```

The app opens at `http://localhost:8501`.

---

## Navigation

The top navbar has two pages:

| Page | Contents |
|------|----------|
| **Dashboard** | All scouting views — rankings, profiles, comparisons, scatter, archetypes |
| **About** | Methodology, data source, dataset coverage, composite score weights |

---

## Sidebar Filters (Dashboard only)

All filters apply across every tab simultaneously.

| Filter | Description |
|--------|-------------|
| **Min. minutes played** | Excludes players below this threshold. Default: 900 (≈10 full games). Raise to focus on established starters; lower to include emerging players. |
| **Age range** | Narrows by player age. Default upper bound: 28. |
| **Positions** | Includes only selected positions (AMC, AML, AMR, MC, ML, MR). Deselect to narrow to a specific role. |
| **Teams** | Filter to one or more clubs. Leave blank for all teams. |
| **Archetype** | Filter by creative style (only available after running the clustering step). |

---

## Dashboard Tabs

### Rankings

The main leaderboard view.

- **Sort by** dropdown — switch the ranking metric (composite score, key passes, through balls, etc.). The bar chart and table both update.
- **Top 20 bar chart** — click any bar to jump directly to that player's full profile in the Player Profile tab.
- **Full rankings table** — scrollable, sortable. The Score column shows a progress bar for quick visual comparison.

### Player Profile

Detailed view for a single player.

- **Select a player** — dropdown sorted by composite score. Automatically pre-selects whoever you clicked in the Rankings bar chart.
- **Header banner** — name, club, position, age, archetype (if available), minutes, appearances, and score circle.
- **Radar chart** — percentile ranks across all 7 metrics. Hover to see both the percentile and the raw per-90 value.
- **Per-90 bar chart** — player values overlaid against the league maximum for each metric. Shows how close the player is to the dataset ceiling.
- **Season totals** — raw counting stats for the full season (goals, assists, key passes, through balls, etc.) displayed as cards.

### Compare

Side-by-side comparison of up to 4 players.

- Select players from the dropdown (sorted by composite score).
- **Overlay radar** — all selected players on a single spider chart with distinct colours.
- **Grouped bar chart** — per-90 values side by side for each metric.
- **Stats table** — transposed so metrics are rows and players are columns. All numeric values rounded to 2 decimal places.

### Scatter Explorer

Two-metric scatter plot for pattern discovery.

- **X axis / Y axis** — choose any two per-90 metrics. Defaults to Key Passes (X) vs Shot-Creating Actions (Y).
- **Bubble size** — optionally scale dot size by a third metric.
- **Quadrant shading** — the top-right quadrant (above median on both axes) is highlighted as the "Elite" zone.
- **Median reference lines** — dashed lines mark the filtered dataset median for each axis.
- **Top 5 annotations** — the 5 highest-scoring players are labelled by surname.
- **Top 5 table** — below the chart, ranked by the Y-axis metric.

### Archetypes

Requires the clustering step to have been run (`python -m src.features.clustering`).

- **Donut chart** — distribution of players across the three creative archetypes.
- **Violin plot** — composite score distribution per archetype, showing spread and median.
- **Average radar** — one radar per archetype showing the mean percentile profile, making archetype differences easy to read at a glance.
- **Player tables** — expandable section per archetype listing its top 20 players by composite score.

---

## Tips

- **Click a bar in Rankings** to instantly navigate to that player's profile without using the dropdown.
- **Raise the minutes filter** if you want to focus only on regular starters (e.g., 1350 min = 15 full games).
- **Combine Scatter + Compare** — use the scatter to spot an interesting cluster of players, then switch to Compare to put them head-to-head on the radar.
- **Archetype filter in sidebar** — useful for scouting a specific profile type (e.g., "show me only Final-Ball Specialists under 25").
- If archetypes are not shown, run `python -m src.features.clustering` and restart the app.
