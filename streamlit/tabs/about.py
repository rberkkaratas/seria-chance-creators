"""About tab — usage guide, methodology, and data coverage."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

import config
from tabs import TabRenderer
from core.models import AppState
from core.constants import label, ROLE_DESCRIPTIONS


class AboutTab(TabRenderer):
    def render(self, state: AppState) -> None:
        st.markdown("## About This Project")
        st.markdown(
            "This dashboard profiles **midfielders** across the top 5 European leagues "
            "using raw match event data from WhoScored — built as a data-driven scouting tool "
            "a sporting director or head scout could act on."
        )
        st.markdown("---")

        about_tab_usage, about_tab_method, about_tab_data = st.tabs([
            "How to Use", "Methodology", "Data & Coverage"
        ])

        with about_tab_usage:
            col_u1, col_u2 = st.columns([1, 1])

            with col_u1:
                st.markdown("### Sidebar Filters")
                st.markdown(
                    "All filters apply across every tab simultaneously."
                )
                st.markdown("""
| Filter | Description |
|--------|-------------|
| **Min. minutes** | Exclude players below this threshold. Default: {min_min} min. Steps in 90-min increments. |
| **Age range** | Drag both handles to set a window. |
| **Positions** | Narrow to specific WhoScored positions (AMC, AML, AMR, MC, ML, MR). |
| **Teams** | Filter to one or more clubs. Leave blank for all. |
| **Role** | Filter by primary role. Deselect to surface specific profiles only. |
| **Transfer Feasibility** | Expiring (≤1 yr), Mid-term (1–2 yrs), Locked (2+ yrs). Shown only when Transfermarkt data is available. |
                """.format(min_min=config.MIN_MINUTES_PLAYED))

                st.markdown("### Dashboard Tabs")

                st.markdown("**Shortlist**")
                st.markdown("""
- Rank all eligible midfielders by Overall Score, any role score, or a specific per-90 metric.
- Top-25 horizontal bar chart, coloured by primary role. **Click a bar** to jump straight to that player's Scout Report.
- Full table with progress-bar columns for Overall Score and all six role scores. When TM data is available, Market Value, Contract Until, and Feasibility are appended.
                """)

                st.markdown("**Role Map**")
                st.markdown("""
- Role description pills explain what each role captures.
- **Distribution donut** — share of players per primary role.
- **6×6 heatmap** — average score of each primary-role group across every role. Bright diagonal = clear role identity; off-diagonal brightness = versatility.
- **Per-role expanders** — top 20 players in each role with the raw metrics used for scoring.
                """)

                st.markdown("**Scout Report**")
                st.markdown("""
- Pick a player (sorted by Overall Score). Pre-populated if you clicked a bar in Shortlist.
- **Header banner** — name, club, position, age, primary role, minutes, appearances, score circle. With TM data: market value, contract year, and a colour-coded feasibility chip.
- **Radar chart** — percentile ranks on the six core chance-creation metrics. Hover for raw per-90 value.
- **Per-90 bar chart** — player output vs. the dataset maximum for each metric.
- **Role ratings** — horizontal bars for all six role scores, colour-coded and numerically labelled.
- **Season totals** — stat cards (goals, assists, key passes, through balls, passes into box, half-space passes, box touches, dribbles, progressive passes, crosses) with per-match averages.
- **Match log** — full-season fixture timeline bar chart (green = win, grey = draw, red = loss, dark = DNP) with goals/assists emoji markers. Scrollable per-match stats table below.
                """)

            with col_u2:
                st.markdown("**Compare**")
                st.markdown("""
- Select 2–4 players (sorted by Overall Score).
- **Overlay radar** — all players on one spider chart with distinct colours.
- **Grouped bar chart** — per-90 values side by side for each core metric.
- **Stats table** — transposed so metrics are rows and players are columns.
                """)

                st.markdown("**Explore**")
                st.markdown("""
Toggle between two modes:

*Free Explore*
- Choose any two per-90 or rate metrics for X and Y axes.
- Optionally scale bubble size by a third metric.
- Points coloured by primary role. Quadrant shading highlights the elite zone (top-right). Top-5 players by Overall Score are labelled.

*Statistical Profiles*
Seven fixed quadrant scatter plots covering key statistical dimensions:

| Plot | X axis | Y axis |
|------|--------|--------|
| Passing | Total passes / 90 | Pass accuracy % |
| Pass patterns | Progressive passes / 90 | Forward pass % |
| Aerial duels | Aerial attempts / 90 | Aerial win rate % |
| Defence | Tackles / 90 | Tackle success rate % |
| Possession | Possession won / 90 | Possession lost / 90 |
| Tackling | Tackles / 90 | Interceptions / 90 |
| Crossing | Crosses / 90 | Cross accuracy % |

Each chart marks median dividers, corner labels (green = best quadrant), and blue pill-badge annotations for the top 8 players by Overall Score.
                """)

                st.markdown("### Tips")
                st.markdown("""
- **Click a bar in Shortlist** → jumps directly to Scout Report.
- **Raise the minutes filter** to restrict to established starters (e.g. 900 min = 10 full games).
- **Combine Free Explore + Compare** — spot a cluster in the scatter, then compare head-to-head on the radar.
- **Role filter** — e.g. "show me only Ball Progressors from the top six clubs".
- **Feasibility filter** — set to Expiring to surface players who could move on a free or low fee.
- If TM data columns are missing, run `python -m src.enrichment.transfermarkt` and restart.
                """)

        with about_tab_method:
            col_left, col_right = st.columns([3, 2])

            with col_left:
                st.markdown("### Pipeline")
                st.markdown("""
```
Match IDs (manual input)
  → WhoScored Extractor   (SeleniumBase UC mode)
  → Per-match Event CSVs
  → Build Tables          (matches / players / teams)
  → Feature Engineering   (per-90, percentiles, 6 role scores, primary_role)
  → Clustering            (K-Means sub-groups)              [optional]
  → TM Enrichment         (market value, contract, feasibility) [optional]
  → Dashboard
```
                """)
                st.markdown("---")

                st.markdown("### Player Selection")
                st.markdown(f"""
Players are included if they meet **all** of the following:

| Criterion | Value |
|-----------|-------|
| Positions | AMC, AML, AMR, MC, ML, MR |
| Minimum minutes (midfield only) | {config.MIN_MINUTES_PLAYED}+ |
| League | Serie A 2025/26 |

Minutes are counted **only from midfield appearances** — a player who logs 800 minutes as a
centre-back and 50 minutes as a midfielder does not qualify.
                """)
                st.markdown("---")

                st.markdown("### Metrics")
                st.markdown(
                    "All counting stats are normalised to **per-90-minute rates**. "
                    "Rate stats (pass accuracy, aerial win rate, etc.) are used as-is. "
                    "Every metric is then ranked into a **percentile (0–100)** within the "
                    "filtered midfielder group before being used in role scoring."
                )

                st.markdown("**Attacking / chance creation**")
                st.markdown("""
| Metric | What it captures |
|--------|-----------------|
| Key Passes / 90 | Passes directly leading to a shot |
| Through Balls / 90 | Line-breaking passes into space |
| Assists / 90 | Direct goal contributions |
| Passes into Box / 90 | High-value delivery into the penalty area |
| Half-Space Passes / 90 | Deliveries into the most dangerous off-centre zones (x ≥ 66, y < 37 or y > 63) |
| Box Touches / 90 | Touches inside the opposition penalty area |
| Successful Dribbles / 90 | Chance creation through individual ball-carrying |
| Carries into Final Third / 90 | Ball carries crossing the final-third line — inferred from sequential event coordinates |
| Poss. Won (Att. Third) / 90 | Possession regained at x ≥ 66.7 — pressing and counter-press output |
| Ball-Winning Height | Average pitch position when winning the ball (higher = presses further up) |
| Forward Pass % | Share of total passes directed forward — directional intent |
                """)

                st.markdown("**Progression**")
                st.markdown("""
| Metric | What it captures |
|--------|-----------------|
| Progressive Passes / 90 | Passes moving the ball ≥25% closer to the opponent's goal |
| Total Passes / 90 | Volume and orchestration |
| Crosses / 90 | Deliveries from wide positions |
| Pass Accuracy % | Accurate passes as a share of total |
| Cross Accuracy % | Accurate crosses as a share of total |
                """)

                st.markdown("**Defensive**")
                st.markdown("""
| Metric | What it captures |
|--------|-----------------|
| Tackles / 90 | Tackle attempts |
| Tackle Success Rate % | Successful tackles as a share of total |
| Interceptions / 90 | Interception events |
| Clearances / 90 | Clearance events |
| Shots Blocked / 90 | Blocked shots or passes |
| Aerial Duels / 90 | Total aerial contest volume |
| Aerial Win Rate % | Won aerials as a share of total |
                """)
                st.markdown("---")

                st.markdown("### Role Scoring")
                st.markdown(
                    "Each player receives a **0–100 score for every role**, computed as a "
                    "weighted average of per-metric percentile ranks within the filtered midfielder group. "
                    "The role with the highest score becomes their **primary role**. "
                    "All weight sets sum to exactly 1.0."
                )

                for role, weights in config.ROLE_WEIGHTS.items():
                    rc = config.ROLE_COLORS.get(role, "#888")
                    desc = ROLE_DESCRIPTIONS.get(role, "")
                    rows = [
                        {"Metric": label(m), "Weight": f"{w * 100:.0f}%"}
                        for m, w in weights.items()
                    ]
                    with st.expander(f"**{role}** — {desc}"):
                        st.dataframe(
                            pd.DataFrame(rows),
                            use_container_width=False,
                            hide_index=True,
                        )

                st.markdown("---")

                st.markdown("### Chance-Creation Score")
                st.markdown(
                    "A **0–100 composite score** measuring how directly a player creates "
                    "goal-scoring opportunities. Computed as a weighted average of percentile "
                    "ranks. Retained for backward compatibility and radar chart display."
                )
                cc_labels = {
                    "key_passes_p90":               "Key Passes / 90",
                    "passes_into_penalty_area_p90": "Into Box / 90",
                    "through_balls_p90":            "Through Balls / 90",
                    "assists_p90":                  "Assists / 90",
                    "half_space_passes_p90":        "Half-Space Passes / 90",
                    "successful_dribbles_p90":      "Dribbles / 90",
                }
                st.dataframe(
                    pd.DataFrame([
                        {"Metric": cc_labels.get(m, m), "Weight": f"{w * 100:.0f}%"}
                        for m, w in config.COMPOSITE_WEIGHTS.items()
                    ]),
                    use_container_width=False,
                    hide_index=True,
                )
                st.caption(
                    "SCA removed (derived from key passes + dribbles — would double-count both). "
                    "Passes into final third and progressive passes removed (ball progression, not chance creation). "
                    "Assists and half-space passes added."
                )
                st.markdown("---")

                st.markdown("### Limitations")
                st.markdown("""
- **Context blindness:** Per-90 stats do not capture game state, opponent quality, or tactical role constraints.
- **Opponent quality:** No adjustment for strength of opponents faced. Stats vs. bottom-half teams carry equal weight to stats vs. top-six sides. Opponent-adjusted metrics are planned for end of season 2025/26.
- **Carry inference:** Carries into the final third are inferred from coordinate transitions, not logged events. The heuristic handles most cases but may miss tight carries or flag a long-pass reception in edge cases.
- **SCA approximation:** Shot-creating actions (key passes + successful dribbles) undercount the true total. Excluded from all scoring formulas for this reason.
- **Positional classification:** WhoScored positions may not reflect a player's actual tactical role in a given match.
- **Sample size:** Single-season analysis — players with injuries or late transfers may not reach the minutes threshold.
- **Transfer data coverage:** Players who leave Serie A mid-season are not on Transfermarkt squad pages and require manual entry via `tm_manual_players.csv`.
                """)

            with col_right:
                st.markdown("### Spatial Thresholds")
                st.markdown(
                    "Pitch coordinates use a 0–100 scale "
                    "(x: own goal → opponent goal, y: left → right touchline)."
                )
                st.markdown("""
| Zone | Threshold |
|------|-----------|
| Final third | x ≥ 66.7 |
| Penalty area | x ≥ 83, 21.1 ≤ y ≤ 78.9 |
| Half-spaces | x ≥ 66 and (y < 37 or y > 63) |
| Progressive pass | (100 − endX) ≤ 0.75 × (100 − x) |
| Carry inference gap | ≤ 30 pitch units between events |
                """)

                st.markdown("### Assist Detection")
                st.markdown("""
Assists are derived from WhoScored's `satisfiedEventsTypes` field. A pass is counted as an
assist if **event-type 92** (goal) appears in its satisfied events, confirming a goal directly
followed that pass.

The `IntentionalAssist` qualifier is **not** used as the primary signal because it appears on
all passes leading to shots — effectively duplicating key passes rather than goals only.
                """)

                st.markdown("### Future Improvements")
                st.markdown("""
- Opponent-adjusted metrics (top-6 / mid-table / bottom-6)
- Expected assists model from pass end-locations
- Role fit score (how well a player fits a specific system)
- Video annotation layer for shortlisted players
                """)

        with about_tab_data:
            col_d1, col_d2 = st.columns([1, 1])

            with col_d1:
                st.markdown("### Data Sources")
                st.info(
                    "**Match events — WhoScored**\n\n"
                    "Extracted per-match for Serie A 2025/26 using a semi-automated "
                    "SeleniumBase (UC mode) pipeline. Match IDs are collected manually; "
                    "the extractor parses the `matchCentreData` JSON embedded in each match page.\n\n"
                    "**Transfer data — Transfermarkt**\n\n"
                    "Market value, contract expiry, and feasibility scraped from team squad pages "
                    "using the same UC-mode browser. Results are cached locally in "
                    "`data/enrichment/tm_squads_cache.csv`; players who transfer mid-season "
                    "can be added via `data/enrichment/tm_manual_players.csv`.\n\n"
                    "This project is for **personal educational and portfolio purposes only**."
                )

                st.markdown("### Transfer Feasibility Tiers")
                st.markdown("""
| Tier | Contract remaining |
|------|-------------------|
| **Expiring** | ≤ 1 year — out of contract or final year |
| **Mid-term** | 1–2 years — negotiable window |
| **Locked** | 2+ years — premium buy-out required |

Player names are matched between WhoScored and Transfermarkt using fuzzy string matching
(rapidfuzz WRatio). Matches above **85% confidence** are auto-verified; ambiguous matches
are flagged in `data/enrichment/tm_player_mapping.csv` for manual review.
                """)

            with col_d2:
                st.markdown("### Dataset Coverage")
                matches_path = config.DATA_PROCESSED / "matches.csv"
                final_path   = config.DATA_FINAL / "chance_creators.csv"
                if matches_path.exists():
                    m_df = pd.read_csv(matches_path)
                    teams_in_data = (
                        set(m_df["home_team_name"].dropna()) |
                        set(m_df["away_team_name"].dropna())
                    )
                    n_players = len(pd.read_csv(final_path)) if final_path.exists() else "—"
                    st.markdown(f"""
| | |
|---|---|
| Matches processed | **{len(m_df)}** |
| Teams | **{len(teams_in_data)}** |
| Eligible midfielders | **{n_players}** |
| Min. minutes threshold | **{config.MIN_MINUTES_PLAYED}** |
| Roles defined | **{len(config.ROLE_WEIGHTS)}** |
                    """)
                else:
                    st.caption("Run the pipeline to see coverage stats.")

                st.markdown("### Author")
                st.markdown("""
**R. Berk Karatas**
Aspiring Football Performance Analyst

[![GitHub](https://img.shields.io/badge/GitHub-rberkkaratas-181717?logo=github)](https://github.com/rberkkaratas)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-rberkkaratas-0A66C2?logo=linkedin)](https://www.linkedin.com/in/rberkkaratas/)

📧 rberkk@protonmail.com
                """)

        st.markdown("---")
        st.markdown(
            "Built by **R. Berk Karatas** · "
            "[GitHub](https://github.com/rberkkaratas) · "
            "[LinkedIn](https://www.linkedin.com/in/rberkkaratas/) · "
            "Data: WhoScored · Serie A 2025/26"
        )
