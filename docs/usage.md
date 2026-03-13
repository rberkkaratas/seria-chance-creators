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
| **Dashboard** | All scouting views — shortlist, role map, scout reports, comparisons, exploration |
| **About** | Methodology, pipeline overview, metrics reference, composite score weights, dataset coverage |

---

## Sidebar Filters (Dashboard only)

All filters apply across every tab simultaneously.

| Filter | Description |
|--------|-------------|
| **Min. minutes played** | Excludes players below this threshold. Default: 600 (≈7 full games). Raise to focus on established starters; lower to include emerging players. Steps in 90-minute increments. |
| **Age range** | Narrows by player age. Drag both handles to set a window. |
| **Positions** | Includes only the selected WhoScored positions (AMC, AML, AMR, MC, ML, MR). Deselect positions to narrow to a specific sub-group. |
| **Teams** | Filter to one or more clubs. Leave blank for all teams. |
| **Role** | Filter by primary role. Deselect roles to surface only specific profiles. |
| **Transfer Feasibility** | Filter by contract status — Expiring (≤1 yr), Mid-term (1–2 yrs), Locked (2+ yrs), Unknown. Only available after running the Transfermarkt enrichment step. |

---

## Dashboard Tabs

### Shortlist

The main leaderboard view.

- **Rank by** dropdown — switch the sort metric between CC Score, each of the six role scores, or individual per-90 metrics. The bar chart and table both update.
- **Top 25 bar chart** — bars coloured by primary role. Click any bar to jump directly to that player's Scout Report.
- **Full rankings table** — scrollable, with progress bars for CC Score and each role score. When Transfermarkt data is available, the table also includes Market Value (€), Contract Until, and Feasibility columns.

### Role Map

Overview of the six tactical roles and how the current filtered group distributes across them.

- **Role description pills** — one card per role with a brief description and role colour, displayed at the top for reference.
- **Distribution donut chart** — shows the share of players assigned to each primary role.
- **Role score heatmap** — a 6×6 grid showing the average score of each primary-role group on every role. The diagonal (a group's own role) should be the brightest; off-diagonal brightness reveals role versatility.
- **Per-role expanders** — one collapsible section per role listing its top 20 players by role score, with the raw metrics used for that role shown as additional columns.

### Scout Report

Detailed profile for a single player.

- **Select a player** — dropdown sorted by CC Score. Pre-populated if you clicked a bar in the Shortlist.
- **Header banner** — name, club, position, age, primary role, minutes played, appearances, and a score circle. When Transfermarkt data is available, the banner also shows market value, contract expiry year, and a colour-coded feasibility chip (green = Expiring, amber = Mid-term, red = Locked).
- **Radar chart** — percentile ranks on the six core chance-creation metrics. Hover to see both the percentile and the raw per-90 value.
- **Per-90 bar chart** — player values overlaid against the dataset maximum for each metric. The grey background bar represents the ceiling; the coloured bar is the player's output. Hover for percentile rank.
- **Role ratings** — horizontal bars for all six role scores, each coloured by its role. Scores are labelled numerically outside the bar.
- **Season totals** — raw counting stats (goals, assists, key passes, through balls, passes into box, half-space passes, box touches, dribbles won, progressive passes, crosses) displayed as stat cards showing the season total and per-match average.
- **Match log** — full-season fixture timeline. A vertical bar per match represents minutes played, coloured by result (green = win, grey = draw, red = loss, dark = DNP). Goals and assists are annotated on bars with emoji markers. Below the chart, a scrollable table shows per-match stats (date, opponent, score, result, status, minutes, goals, assists, key passes, and more).

### Compare

Side-by-side comparison of up to 4 players.

- Select players from the dropdown (sorted by CC Score). Minimum 2 required to display charts.
- **Overlay radar** — all selected players on a single spider chart with distinct colours.
- **Grouped bar chart** — per-90 values side by side for each core metric.
- **Stats table** — transposed so metrics are rows and players are columns. All numeric values rounded to 2 decimal places.

### Explore

Two exploration modes toggled by a radio button at the top of the tab.

**Free Explore**

Two-metric scatter plot for open-ended pattern discovery.

- **X axis / Y axis** — choose any per-90 or rate metric. Defaults to Key Passes vs. Passes into Box.
- **Bubble size** — optionally scale dot size by a third metric (select "None" to use uniform sizing).
- Points are coloured by primary role using the role colour palette.
- **Quadrant shading** — top-right quadrant (above median on both axes) is shaded green as the "Elite" zone; adjacent quadrants are shaded amber/blue.
- **Median reference lines** — dotted lines mark the filtered dataset median for each axis.
- **Top 5 annotations** — the 5 highest CC-scoring players are labelled by name.

**Statistical Profiles**

Seven fixed quadrant scatter plots covering key statistical dimensions:

| Plot | X axis | Y axis | Best quadrant |
|------|--------|--------|---------------|
| Passing | Total passes / 90 | Pass accuracy (%) | Top right — high volume, high accuracy |
| Pass patterns | Progressive passes / 90 | Forward pass % | Top right — progressive and direct |
| Aerial duels | Aerial attempts / 90 | Aerial win rate (%) | Top right — active and dominant |
| Defence | Tackles / 90 | Tackle success rate (%) | Top right — active and efficient |
| Possession | Possession won / 90 | Possession lost / 90 | Top left — win possession, don't lose it |
| Tackling | Tackles / 90 | Interceptions / 90 | Top right — high across both actions |
| Crossing | Crosses / 90 | Cross accuracy (%) | Top right — high volume, high accuracy |

Each chart shows median dividers, corner labels (green = best quadrant, amber = others), and blue pill-badge annotations for the top 8 players by CC Score.

---

## Tips

- **Click a bar in Shortlist** to instantly navigate to that player's Scout Report without using the dropdown.
- **Raise the minutes filter** to focus on regular starters (e.g. 900 min = 10 full games; 1350 min = 15 full games).
- **Combine Free Explore + Compare** — use the scatter to spot an interesting cluster of players, then switch to Compare to put them head-to-head on the radar.
- **Role filter in sidebar** — useful for scouting a specific profile (e.g. "show me only Ball Progressors from the top six clubs").
- **Feasibility filter** — set to "Expiring" only to surface players who could move on a free or low fee at the end of the season.
- If Transfermarkt data is not shown (no market value, no feasibility chip), run `python -m src.enrichment.transfermarkt` and restart the app.
- The About page includes live dataset coverage stats (matches processed, teams, eligible midfielders) pulled directly from the processed data files.
