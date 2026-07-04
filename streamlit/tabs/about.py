"""About tab — usage guide, methodology, and data coverage."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

import config
from tabs import TabRenderer
from core.models import AppState
from core.constants import label


class AboutTab(TabRenderer):
    def render(self, state: AppState) -> None:
        st.markdown("## About This Project")
        st.markdown(
            "SquadLens profiles outfield players and teams across ten European leagues "
            "using WhoScored match event data. Goalkeepers are intentionally excluded until GK-specific "
            "events such as saves, claims, and punches are parsed."
        )
        st.markdown("---")

        about_tab_usage, about_tab_method, about_tab_data = st.tabs([
            "How to Use", "Methodology", "Data & Coverage"
        ])

        with about_tab_usage:
            st.markdown("### Filters")
            st.markdown(f"""
| Filter | Description |
|--------|-------------|
| **Position group** | Defenders, Fullbacks, Midfielders, Wingers, or Forwards. Every tab is scoped to this selection. |
| **Min. minutes** | Group-specific visibility threshold. Default: {config.MIN_MINUTES_INCLUDED} min; {config.FULL_SAMPLE_MINUTES} min is full-sample confidence. |
| **Age range** | Restrict to an age window. |
| **Positions** | Narrow within the active WhoScored position group. |
| **Role** | Filter by primary role inside the selected group. |
| **Transfer filters** | Market value and feasibility when Transfermarkt enrichment is available. |
            """)

            st.markdown("### Tabs")
            st.markdown("""
| Tab | What it shows |
|-----|---------------|
| **Shortlist** | Ranked players by Overall or any active role score. |
| **Role Map** | Role definitions, distribution, DNA, league share, top players, and market-value scatter. |
| **Scout Report** | Individual profile with rank, radar, role bars, season totals, similar players, and match log. |
| **Compare** | Side-by-side comparison for 2–4 players inside the active group. |
| **Explore** | Group-specific scouting lenses plus statistical profile scatters. |
| **League Overview** | League identity cards, role-score heatmaps, top players, age, and market-value views. |
            """)

        with about_tab_method:
            st.markdown("### Pipeline")
            st.markdown("""
```text
WhoScored fixture pages
  -> fixture_scraper.py
  -> whoscored_extractor.py
  -> build_tables.py
  -> player_features.py
  -> merge_leagues.py   <- league_strength.py (ClubElo coefficients, cached)
  -> transfermarkt.py
  -> Streamlit dashboard
```
            """)

            st.markdown("### Player Selection")
            rows = []
            for group_key, group_cfg in config.POSITION_GROUPS.items():
                rows.append({
                    "Group": group_cfg["display_name"],
                    "WhoScored positions": ", ".join(group_cfg["positions"]),
                    "Minute rule": (
                        f"{config.MIN_MINUTES_INCLUDED}+ visible; "
                        f"{config.FULL_SAMPLE_MINUTES}+ full-sample confidence"
                    ),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption(
                "A player can qualify in more than one group. In that case the output has one row per "
                "(player_id, position_group), and each row aggregates only that group's appearances."
            )

            st.markdown("### Percentiles and Scores")
            st.markdown(
                "Counting stats are normalised to per-90 rates. Rate stats are used as-is. "
                "Before percentile ranking, low-sample metrics are shrunk toward the active pool median "
                "using minutes, appearances, starts, and start rate. "
                "Percentiles are computed within the active position group: per-league outputs write "
                "`{metric}_league_pct`, and the merge step converts each within-league percentile to a "
                "latent z-score (inverse normal CDF, clipped to 0.5–99.5), shifts it by a per-league "
                "strength offset, and reranks within the cross-league group to produce `{metric}_pct`. "
                f"Strength offsets come from ClubElo mean club Elo per league "
                f"({config.ELO_PER_SIGMA:.0f} Elo per standard deviation), so equal within-league "
                "standing counts for more in a stronger league. "
                "Role scores are weighted averages of those percentile ranks. "
                "Overall score is computed inside cleaner tactical pools: centre-backs, fullbacks, "
                "central midfielders, wingers, and forwards use separate role blends. "
                "Role and overall scores are also pulled toward 50 when score confidence is low."
            )

            for group_key, group_cfg in config.POSITION_GROUPS.items():
                st.markdown(f"### {group_cfg['display_name']} Roles")
                for role, weights in group_cfg["roles"].items():
                    rows = [
                        {"Metric": label(metric), "Weight": f"{weight * 100:.0f}%"}
                        for metric, weight in weights.items()
                    ]
                    with st.expander(f"{role}"):
                        st.caption(group_cfg["role_descriptions"][role])
                        st.dataframe(pd.DataFrame(rows), use_container_width=False, hide_index=True)

            st.markdown("### Limitations")
            st.markdown("""
- Goalkeepers are excluded because GK event parsing is not implemented yet.
- Substitute appearances are assigned to the player's primary known outfield position; sub-only players without a known outfield position remain excluded.
- WhoScored position labels can differ from a player's real tactical role.
- League strength offsets are league-wide constants: they correct the average level gap, not team-specific context inside a league.
- Existing processed data is enough for the new role scores, but event-level fixes require newly scraped raw events.
            """)

        with about_tab_data:
            st.markdown("### Data Sources")
            st.info(
                "**Match events — WhoScored**\n\n"
                "Extracted per match with SeleniumBase UC mode.\n\n"
                "**Transfer data — Transfermarkt**\n\n"
                "Market value, contract expiry, and feasibility from squad pages, cached locally."
            )

            st.markdown("### Dataset Coverage")
            coverage_rows = []
            for league_key, league_cfg in config.LEAGUES.items():
                processed_path = config.get_processed_path(league_key, config.SEASON)
                matches_path = processed_path / "matches.csv"
                final_path = config.get_final_path(league_key, config.SEASON)
                matches = pd.read_csv(matches_path) if matches_path.exists() else pd.DataFrame()
                final = pd.read_csv(final_path) if final_path.exists() else pd.DataFrame()
                row = {
                    "League": league_cfg["display_name"],
                    "Matches processed": len(matches) if not matches.empty else "—",
                    "Qualified rows": len(final) if not final.empty else "—",
                }
                if not final.empty and config.POSITION_GROUP_COL in final.columns:
                    for group_key in config.POSITION_GROUPS:
                        row[group_key] = int((final[config.POSITION_GROUP_COL] == group_key).sum())
                coverage_rows.append(row)
            st.dataframe(pd.DataFrame(coverage_rows), use_container_width=True, hide_index=True)

            st.markdown("### Transfer Feasibility Tiers")
            st.markdown("""
| Tier | Contract remaining |
|------|-------------------|
| **Expiring** | <= 1 year |
| **Mid-term** | 1-2 years |
| **Locked** | 2+ years |
            """)

        st.markdown("---")
        st.markdown(
            "Built by **R. Berk Karatas** · "
            "[GitHub](https://github.com/rberkkaratas) · "
            "[LinkedIn](https://www.linkedin.com/in/rberkkaratas/) · "
            "Data: WhoScored · Transfermarkt"
        )
