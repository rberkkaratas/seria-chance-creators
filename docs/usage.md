# Dashboard Usage Guide

## The Scouting Workflow

The dashboard is built around one flow: narrow the pool globally, surface the names worth investigating, profile them individually, then compare the shortlist head-to-head.

```
Filters  →  Shortlist  →  Scout Report  →  Scouting Dossier
```

---

## Launching the App

```bash
streamlit run streamlit/app.py
```

Opens at `http://localhost:8501`. The app reads the highest-priority data file it can find:

1. `all_leagues_{season}_enriched.csv` — 5-league dataset with Transfermarkt data (preferred)
2. `all_leagues_{season}.csv` — 5-league dataset without enrichment
3. `chance_creators_enriched.csv` — Serie A only, with enrichment (legacy fallback)
4. `chance_creators_clustered.csv` — Serie A only (legacy fallback)
5. `chance_creators.csv` — base Serie A output (last resort)

If none exist, the app shows pipeline instructions and stops.

---

## Filters

Filters sit inline at the top of every page in a four-column layout. Every filter applies across all tabs simultaneously — changing one updates every chart, table, and ranking in the app.

**Column 1 — Playing time**

| Filter | Default | Notes |
|--------|---------|-------|
| Min. minutes played | 600 | Slider, steps in 90-min increments — one full match per step |
| Age range | Full range | Dual-handle slider capped at `MAX_AGE` |
| Market value (€M) | Full range | Only shown when Transfermarkt data is available |

**Column 2 — Player profile**

| Filter | Notes |
|--------|-------|
| Positions | Multiselect from all WhoScored positions present (AMC, AML, AMR, MC, ML, MR). All selected by default. |
| Role | Multiselect from the four roles (Creator, Ball Progressor, Box Threat, Deep Builder). Filters by `primary_role`. |

**Column 3 — Club**

| Filter | Notes |
|--------|-------|
| Leagues | Multiselect — all five leagues shown when the merged dataset is loaded. |
| Teams | Multiselect, dynamically scoped to selected leagues. Blank = all teams. |

**Column 4 — Market & mode**

| Filter | Notes |
|--------|-------|
| Percentile mode | Radio: **All leagues** (global pool of ~420 players) or **Within league**. Controls role scores and radar percentiles. Only shown with multi-league data. |
| Transfer Feasibility | Multiselect: Expiring / Mid-term / Locked / Unknown. Only shown with Transfermarkt data. |

---

## Shortlist

**Start here.** Gives you a ranked view of the full filtered pool.

**Sort pills** across the top switch the ranking between Overall Score and each of the four role scores. Switching to Creator re-ranks the entire view to surface the best Creators — even if they rank lower overall.

**Podium cards** show the top 3 for the selected sort metric — medal, name, club with league flag, score, and primary role.

**Top-25 bar chart** — horizontal bars coloured by each player's primary role. A grey background track shows the 0–100 scale. A dotted white line marks the average for the selected metric. Score values are labelled outside each bar.

**Click any bar** to jump directly to that player's Scout Report. No dropdown needed.

**Full ranked table** below the chart shows the entire filtered pool. Columns: name, team, league, position, age, minutes, primary role, Overall Score, all four role scores. When Transfermarkt data is available: Market Value (€), Contract Until, and Feasibility.

**Typical workflow:**
1. Set your target filters — league, age, minutes
2. Switch the sort pill to the role you are scouting
3. Note the top 5–8 names from the chart
4. Click a name to open their Scout Report

---

## Creation Role Taxonomy

An overview of the four roles and how the filtered population distributes across them.

### Role cards

One card per role at the top. Each card shows:
- **Role name** and a **zone badge** (Deep / Dynamic / Advanced) indicating where on the pitch the role operates
- **Description** of the tactical profile
- **Metric weight bars** — a visual breakdown of each metric's contribution to the role score
- **Footer stats**: player count, average role score for players assigned to this role, and average market value (if Transfermarkt data is available)

### Who plays what?

Two charts shown side-by-side:
- **Role distribution donut** — share of players assigned to each primary role. The dominant role is pulled slightly outward.
- **Role Versatility Matrix** — a 4×4 heatmap. Rows are primary-role groups; columns are the four role scores. The diagonal shows how strongly each group scores on their own role. Off-diagonal brightness reveals versatility: a Ball Progressor who also scores high on Creator is a different player than one who is a pure carrier.

### Role DNA

A heatmap of every metric used across all four roles, averaged by primary role group. Bright cells show where each archetype genuinely excels; dark cells reveal where they don't. This is the most granular view of what separates the profiles statistically.

### Role Share by League

A 100% stacked bar chart showing what percentage of each league's midfielders fall into each role. Only shown when more than one league is visible. Reveals each league's tactical identity — which leagues produce more Creators vs Deep Builders.

### Top Players by Role

The top 8 players per role ranked by their role score, displayed with a score bar. Players are grouped by pitch zone (Deep → Dynamic → Advanced) for easier scanning.

### Role Score vs Market Value

A scatter plot of each player's role score (on their primary role) against their market value. Only shown when Transfermarkt data is available and at least 5 players have values. Top-left is the undervalued quadrant — high performance, low cost. Median lines divide the chart into quadrants.

---

## Scout Report

Detailed profile for a single player.

**Player selector** — dropdown sorted by Overall Score. Pre-populated if you clicked a bar in the Shortlist.

**Header banner** — name, club, position, age, primary role badge (in role colour), appearances, minutes played, and a score circle. When Transfermarkt data is available: market value, contract expiry year, and a feasibility chip. Both the global rank and within-league rank are shown.

**Radar chart** — percentile ranks across the core chance-creation metrics. Hover any vertex to see both the percentile rank and the raw per-90 value. The shape tells the story quickly: a player who fills the top hemisphere of the radar is creating from everywhere; one who fills only one axis is a specialist.

**Per-90 bar chart** — player values overlaid against the dataset maximum. The grey background bar is the ceiling; the coloured bar is the player's output. Hover for the percentile rank. Good for spotting which specific metrics a player leads the dataset on.

**Role ratings** — four horizontal bars, one per role, each in its role colour with the score labelled numerically. Read this alongside the radar: the role bars show the overall profile fit; the radar shows the underlying metrics.

**Season totals** — raw counting stats for the season displayed as stat cards: goals, assists, key passes, through balls, passes into box, box touches, dribbles won, progressive passes, crosses. Each card shows the season total and per-match average.

**Match log** — full-season fixture timeline:
- A vertical bar per match represents minutes played, coloured by result (green = win, grey = draw, red = loss, dark/absent = DNP)
- Goals and assists are annotated on bars
- Below the chart, a scrollable table shows per-match: date, opponent, score, result, status (Started / Sub / DNP), minutes, goals, assists, key passes, and more

The match log is the fastest way to add context to a statistical profile: a player whose peak outputs come against mid-table sides in home matches is a different proposition to one who produces consistently in away fixtures against top-six clubs.

---

## Scouting Dossier

Side-by-side tactical comparison of up to 4 players — described by the app as "role fit, key battlegrounds, and where each player gives you something the other can't."

**Important:** the player pool here draws from the **full dataset**, not the current filter selection. You can compare a Serie A player with a Premier League player even if your League filter is set to Serie A only.

Select 2–4 players from the dropdown (sorted by Overall Score). Charts appear once at least 2 are selected.

The tab renders a full tactical dossier for the group. Use this after the Shortlist surfaces several candidates for the same role to understand exactly where they differ.

---

## Scouting Explorer

Two exploration modes toggled by a radio button at the top:

### Lens Explorer

Preset scouting lenses — each one pairs two metrics that together answer a specific question about a midfielder type. Select a lens, then optionally add bubble sizing and spotlight a specific player.

**Available lenses:**

| Lens | X axis | Y axis | Elite label |
|------|--------|--------|-------------|
| Creator | Key passes / 90 | Passes into penalty area / 90 | Prolific creators |
| Ball Progressor | Successful dribbles / 90 | Carries into final third / 90 | Direct progressors |
| Box Threat | Shots / 90 | Penalty area touches / 90 | Box dominators |
| Deep Builder | Progressive passes / 90 | Pass accuracy (%) | Reliable builders |
| Wide Creator | Crosses / 90 | Passes into penalty area / 90 | Wide deliverers |
| Custom | Choose any metric | Choose any metric | — |

**Controls** (three columns):
- **Scouting lens** — select from the presets or Custom
- **Bubble size** (preset lenses) / **X axis** (Custom) — optionally scale dots by a third metric
- **Spotlight player** (preset lenses) / **Y axis** (Custom) — type a surname to highlight that player with a larger outlined dot and name label

**Chart features:**
- Points coloured by primary role
- Quadrant colour fills: green (top-right, elite), amber (top-left), blue (bottom-right), near-black (bottom-left)
- Dotted median lines on both axes
- Top 5 players by Y metric annotated by surname (spotlight players skipped — they're already labelled)
- **Lens insight callout** below the chart: who leads the lens, their two metric values, and what percentage of the filtered pool sits in the elite quadrant

**Top-10 table** below the callout: the 10 highest-ranked players by the Y metric, with league, role, and both metric values.

### Statistical Profiles

Seven fixed scatter plots covering distinct skill dimensions. Displayed in a 2-column grid, each with an italic insight callout beneath.

| Plot | X axis | Y axis | Best quadrant |
|------|--------|--------|---------------|
| Passing Volume & Accuracy | Pass accuracy (%) | Pass attempts / 90 | Top right |
| Progressive Intent | Progressive passes / 90 | Pass accuracy (%) | Top right |
| Aerial Presence | Aerial win rate (%) | Aerial attempts / 90 | Top right |
| Defensive Contribution | Clearances / 90 | Blocks / 90 | Top right |
| Possession Battle | Possession lost / 90 | Possession won / 90 | Top left — win it, don't lose it |
| Tackling | Tackle success rate (%) | Tackles / 90 | Top right |
| Crossing | Cross accuracy (%) | Crosses / 90 | Top right |

Each chart: solid median lines, corner labels (green = best quadrant, grey = others), top-5 annotated players.

Use the **Role filter** in the filters panel to zoom into a specific archetype across all seven plots simultaneously.

---

## League Identity

Cross-league analysis — requires the merged 5-league dataset. Not shown with single-league data.

**League identity cards** — one per league. Each shows the league's dominant role (highest avg role score), second and third roles, total player count, average Overall Score, and average market value (if Transfermarkt data is available).

**Role Fingerprint by League** — a heatmap of average role scores per league. A ★ marks the top-scoring league for each role. This is the fastest way to see which leagues over-index on specific profiles.

**Role Scores — League vs League** — grouped bar chart comparing average role scores across all five leagues side by side for each role.

**Best in Class** — a table showing the top-scoring player per role per league. Only players whose primary role matches the column role are included, so scores reflect genuine role fit rather than secondary scoring.

**Age Profile by League** — box plots showing the distribution of midfielder ages per league. Reveals which leagues trust younger players and which rely on experience. Mean and standard deviation are shown.

**Market Value by League** — bar chart of average market value per league with diamond markers for the median. Only shown with Transfermarkt data.

---

## Tips

**Click bars in Shortlist** to navigate directly to a player's Scout Report — faster than finding them in the dropdown.

**Raise the minutes filter to 900–1350** to focus on regular starters with enough sample to trust. A player at 620 minutes deserves more scrutiny than one at 2000.

**Check role ratings before the radar** in Scout Report. A player with a high Creator score and a weak Deep Builder score is a specialist; one who scores near-evenly across all four roles is a different type of signing.

**Use Spotlight in Lens Explorer** to track a specific player across different lenses. Type their surname and they'll be highlighted with a larger dot and label even when zoomed into a different metric pair.

**Compare pulls from the full dataset** — you can compare a player from a league you've filtered out. Set the League filter to Serie A to narrow the Shortlist, then open Scouting Dossier and add a Premier League player to the comparison.

**Role Share by League in Creation Role Taxonomy** reveals which leagues to target for specific profiles. If you need a Deep Builder, check which league over-indexes on that role before narrowing further.

**Global percentiles for cross-league comparisons; Within League for domestic scouting.** A player ranked 88th globally and 95th in their own league is genuinely elite in their context. A player ranked 70th globally but 90th in their league may be a big fish in a smaller pond.

**Set Feasibility to Expiring** when budget is the constraint. Players in their final contract year are the most accessible — filter to Expiring in the sidebar and the entire ranking reflects that constraint.

**If Transfermarkt data is missing**, run `python -m src.enrichment.transfermarkt` from the project root and restart the app. The market value filter, feasibility chip, and Role Score vs Market Value scatter will all activate.
