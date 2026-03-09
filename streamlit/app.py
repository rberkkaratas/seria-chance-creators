"""
Serie A Chance Creators — Scouting Dashboard
----------------------------------------------
Interactive Streamlit app for exploring creative midfielder profiles.

Usage:
    streamlit run streamlit/app.py
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from streamlit_option_menu import option_menu

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.visualization.radar import create_radar_chart, create_comparison_radar, PLAYER_COLORS

# ── Dark theme constants (shared with radar.py) ───────────────────────
D_BG    = "#111827"
D_PAPER = "#111827"
D_GRID  = "rgba(255,255,255,0.08)"
D_LINE  = "rgba(255,255,255,0.15)"
D_TEXT  = "#cbd5e1"
D_TICK  = "#94a3b8"


def dark_layout(**extra) -> dict:
    """Base dark layout kwargs — merge with chart-specific overrides."""
    base = dict(
        plot_bgcolor=D_BG,
        paper_bgcolor=D_PAPER,
        font=dict(color=D_TEXT),
    )
    base.update(extra)
    return base


# ─── Page Config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Serie A Chance Creators 2025/26",
    page_icon="⚽",
    layout="wide",
)

# ─── CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #1e293b;
        border-radius: 8px;
        padding: 16px 20px;
        border-left: 4px solid #0095FF;
    }
    .metric-card h3 { margin: 0; font-size: 1.6rem; color: #0095FF; }
    .metric-card p  { margin: 4px 0 0; font-size: 0.85rem; color: #94a3b8; }
    .score-badge {
        display: inline-block;
        background: #0095FF;
        color: white;
        border-radius: 20px;
        padding: 4px 14px;
        font-weight: bold;
        font-size: 1.2rem;
    }
    .section-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #cbd5e1;
        border-bottom: 2px solid #0095FF;
        padding-bottom: 4px;
        margin-bottom: 12px;
    }
    div[data-testid="stTabs"] button { font-size: 0.95rem; }
</style>
""", unsafe_allow_html=True)


# ─── Metric Labels ────────────────────────────────────────────────────
METRIC_LABELS = {
    "key_passes_p90":               "Key Passes / 90",
    "through_balls_p90":            "Through Balls / 90",
    "passes_into_final_third_p90":  "Into Final Third / 90",
    "passes_into_penalty_area_p90": "Into Box / 90",
    "shot_creating_actions_p90":    "Shot-Creating Actions / 90",
    "successful_dribbles_p90":      "Dribbles / 90",
    "progressive_passes_p90":       "Progressive Passes / 90",
    "assists_p90":                  "Assists / 90",
    "goals_p90":                    "Goals / 90",
    "shots_p90":                    "Shots / 90",
    "crosses_p90":                  "Crosses / 90",
}

def label(col: str) -> str:
    return METRIC_LABELS.get(col, col.replace("_p90", "").replace("_", " ").title())

ARCHETYPE_COLORS = {
    "Final-Ball Specialist": "#007BFF",
    "Progressive Carrier":   "#FF5252",
    "Volume Creator":        "#00C896",
}

def archetype_color(name: str) -> str:
    return ARCHETYPE_COLORS.get(name, "#888")


# ─── Data Loading ─────────────────────────────────────────────────────
@st.cache_data
def load_data() -> pd.DataFrame:
    enriched  = config.DATA_FINAL / "chance_creators_enriched.csv"
    clustered = config.DATA_FINAL / "chance_creators_clustered.csv"
    base      = config.DATA_FINAL / "chance_creators.csv"
    if enriched.exists():
        return pd.read_csv(enriched)
    if clustered.exists():
        return pd.read_csv(clustered)
    if base.exists():
        return pd.read_csv(base)
    st.error(
        "**Data not found.** Run the pipeline first:\n\n"
        "```bash\n"
        "python -m src.processing.build_tables\n"
        "python -m src.features.chance_creation\n"
        "python -m src.features.clustering        # optional\n"
        "python -m src.enrichment.transfermarkt   # optional\n"
        "```"
    )
    st.stop()


df = load_data()

if "profile_player" not in st.session_state:
    st.session_state["profile_player"] = None

if "shot_creating_actions_p90" not in df.columns:
    if "key_passes_p90" in df.columns and "successful_dribbles_p90" in df.columns:
        df["shot_creating_actions_p90"] = df["key_passes_p90"] + df["successful_dribbles_p90"]

has_archetypes = "archetype" in df.columns
has_tm_data    = "market_value_eur" in df.columns
CORE_METRICS   = [m for m in config.CHANCE_CREATION_METRICS if m in df.columns]
PCT_COLS       = [f"{m}_pct" for m in CORE_METRICS if f"{m}_pct" in df.columns]
score_col      = "chance_creation_score"

rename_map = {
    "player_name": "Player", "team_name": "Team", "position": "Pos",
    "age": "Age", "minutes_played": "Mins", "archetype": "Archetype",
    score_col: "Score",
}
rename_map.update({m: label(m) for m in CORE_METRICS})


# ─── Top Navbar ───────────────────────────────────────────────────────
selected_page = option_menu(
    menu_title=None,
    options=["Dashboard", "About"],
    icons=["bar-chart-fill", "info-circle-fill"],
    orientation="horizontal",
    styles={
        "container": {
            "padding": "0",
            "background-color": "#0f172a",
            "border-bottom": "1px solid #1e293b",
            "margin-bottom": "1rem",
        },
        "nav-link": {
            "font-size": "0.9rem",
            "font-weight": "500",
            "color": "#94a3b8",
            "padding": "12px 24px",
            "border-radius": "0",
        },
        "nav-link-selected": {
            "background-color": "transparent",
            "color": "#f1f5f9",
            "border-bottom": "2px solid #0095FF",
            "font-weight": "600",
        },
        "icon": {"font-size": "0.85rem"},
    },
)


# ─── Sidebar (Dashboard only) ─────────────────────────────────────────
if selected_page == "Dashboard":
    with st.sidebar:
        st.markdown("""
            <div style="padding:16px 4px 8px;text-align:center">
                <div style="font-size:2rem">⚽</div>
                <div style="font-size:1.1rem;font-weight:700;color:#f1f5f9;letter-spacing:0.5px">
                    Serie A Scouting
                </div>
                <div style="font-size:0.75rem;color:#64748b;margin-top:2px">2025 / 26</div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("""
            <div style="background:#1e293b;border-radius:8px;padding:10px 14px;
                        margin:8px 0 16px;font-size:0.78rem;color:#94a3b8;line-height:1.5">
                Filter players across all views using the controls below.
            </div>
        """, unsafe_allow_html=True)

        # ── Playing time ──
        st.markdown('<p style="font-size:0.72rem;font-weight:600;color:#64748b;'
                    'text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px">'
                    'Playing Time</p>', unsafe_allow_html=True)
        min_mins = st.slider(
            "Min. minutes played",
            min_value=0,
            max_value=int(df["minutes_played"].max()) if "minutes_played" in df.columns else 2000,
            value=config.MIN_MINUTES_PLAYED,
            step=90,
            label_visibility="collapsed",
        )
        st.caption(f"Min. minutes: **{min_mins}**")

        st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

        # ── Age ──
        if "age" in df.columns:
            st.markdown('<p style="font-size:0.72rem;font-weight:600;color:#64748b;'
                        'text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px">'
                        'Age Range</p>', unsafe_allow_html=True)
            age_min = int(df["age"].min())
            age_max = int(df["age"].max())
            age_range = st.slider(
                "Age range", age_min, age_max, (age_min, int(config.MAX_AGE)),
                label_visibility="collapsed",
            )
            st.caption(f"Age: **{age_range[0]} – {age_range[1]}**")
        else:
            age_range = (0, 99)

        st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

        # ── Positions ──
        if "position" in df.columns:
            st.markdown('<p style="font-size:0.72rem;font-weight:600;color:#64748b;'
                        'text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px">'
                        'Positions</p>', unsafe_allow_html=True)
            all_positions = sorted(df["position"].dropna().unique().tolist())
            selected_positions = st.multiselect(
                "Positions", options=all_positions, default=all_positions,
                label_visibility="collapsed",
            )
        else:
            selected_positions = []

        st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

        # ── Teams ──
        st.markdown('<p style="font-size:0.72rem;font-weight:600;color:#64748b;'
                    'text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px">'
                    'Teams</p>', unsafe_allow_html=True)
        all_teams = sorted(df["team_name"].dropna().unique().tolist())
        selected_teams = st.multiselect(
            "Teams", options=all_teams, default=[],
            label_visibility="collapsed",
            placeholder="All teams",
        )

        # ── Archetypes ──
        if has_archetypes:
            st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)
            st.markdown('<p style="font-size:0.72rem;font-weight:600;color:#64748b;'
                        'text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px">'
                        'Archetype</p>', unsafe_allow_html=True)
            all_archetypes = sorted(df["archetype"].dropna().unique().tolist())
            selected_archetypes = st.multiselect(
                "Creative archetype", options=all_archetypes, default=all_archetypes,
                label_visibility="collapsed",
            )

        # ── Transfer Feasibility ──
        if has_tm_data:
            st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)
            st.markdown('<p style="font-size:0.72rem;font-weight:600;color:#64748b;'
                        'text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px">'
                        'Transfer Feasibility</p>', unsafe_allow_html=True)
            all_feasibility = ["Expiring", "Mid-term", "Locked", "Unknown"]
            selected_feasibility = st.multiselect(
                "Transfer feasibility", options=all_feasibility, default=all_feasibility,
                label_visibility="collapsed",
            )

        # ── Footer ──
        st.markdown("<div style='margin:20px 0 0'></div>", unsafe_allow_html=True)
        st.markdown("""
            <div style="border-top:1px solid #1e293b;padding-top:12px;
                        font-size:0.72rem;color:#475569;text-align:center;line-height:1.8">
                Data: WhoScored · Transfermarkt<br>
                Serie A 2025/26<br>
                <span style="color:#334155">Built by R. Berk Karatas</span>
            </div>
        """, unsafe_allow_html=True)

else:
    # Provide defaults so filter variables always exist
    min_mins = config.MIN_MINUTES_PLAYED
    age_range = (0, 99)
    selected_positions = config.POSITIONS
    selected_teams = []
    if has_archetypes:
        selected_archetypes = sorted(df["archetype"].dropna().unique().tolist())
    if has_tm_data:
        selected_feasibility = ["Expiring", "Mid-term", "Locked", "Unknown"]


# ─── About Page ───────────────────────────────────────────────────────
if selected_page == "About":
    ABOUT_METRIC_LABELS = {
        "key_passes_p90":               "Key Passes / 90",
        "through_balls_p90":            "Through Balls / 90",
        "passes_into_final_third_p90":  "Passes into Final Third / 90",
        "passes_into_penalty_area_p90": "Passes into Box / 90",
        "shot_creating_actions_p90":    "Shot-Creating Actions / 90",
        "successful_dribbles_p90":      "Successful Dribbles / 90",
        "progressive_passes_p90":       "Progressive Passes / 90",
    }

    st.markdown("## About This Project")
    st.markdown(
        "This dashboard identifies and profiles **elite chance-creating midfielders** "
        "in Serie A 2025/26 using raw match event data — built as a data-driven scouting "
        "tool that a sporting director or head scout could act on."
    )
    st.markdown("---")

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown("### Pipeline")
        st.markdown("""
```
Match IDs (manual input)
  → WhoScored Extractor   (SeleniumBase UC mode)
  → Per-match Event CSVs
  → Build Tables          (matches / players / teams)
  → Feature Engineering   (per-90, percentiles, composite score)
  → Clustering            (K-Means creative archetypes)   [optional]
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
| Minimum minutes (midfield) | {config.MIN_MINUTES_PLAYED}+ |
| League | Serie A 2025/26 |

Minutes are counted **only from midfield appearances** — a player who logs 600 minutes as a
centre-back and 50 minutes as a midfielder does not qualify.
        """)
        st.markdown("---")

        st.markdown("### Chance-Creation Metrics")
        st.markdown("""
All counting stats are normalised to **per-90-minute rates** for fair comparison across
players with different playing time.

| Metric | What it captures |
|--------|-----------------|
| Key Passes | Direct chance creation — passes leading to a shot |
| Through Balls | Ability to break defensive lines |
| Passes into Final Third | Ball progression into dangerous areas |
| Passes into Box | High-value delivery into the penalty area |
| Shot-Creating Actions | Key passes + successful dribbles (proxy SCA) |
| Successful Dribbles | Chance creation through individual ball-carrying |
| Progressive Passes | Forward-moving passes (≥25% closer to goal) |
        """)
        st.markdown("---")

        st.markdown("### Composite Score")
        st.markdown(
            "A **weighted composite score** combines percentile ranks across all metrics. "
            "Weights prioritise direct chance creation (key passes, SCA, penalty-area delivery) "
            "over volume progression."
        )
        weight_df = pd.DataFrame([
            {"Metric": ABOUT_METRIC_LABELS.get(m, m), "Weight": f"{w * 100:.0f}%"}
            for m, w in config.COMPOSITE_WEIGHTS.items()
        ])
        st.dataframe(weight_df, use_container_width=False, hide_index=True)
        st.markdown("---")

        st.markdown("### Archetype Clustering")
        st.markdown("""
**K-Means (k=3)** is applied to standardised per-90 metrics to identify distinct creative
profiles. The number of clusters reflects three broadly recognised midfielder types in
football analytics, validated using the elbow method.

| Archetype | Characteristics |
|-----------|----------------|
| **Final-Ball Specialist** | High key passes, through balls, assists — the classic #10 |
| **Progressive Carrier** | High dribbles, progressive carries — creates by driving with the ball |
| **Volume Creator** | High pass volume, progressive passes — creates through tempo & orchestration |

*Actual labels are assigned after inspecting cluster centroids and representative players.*
        """)
        st.markdown("---")

        st.markdown("### Limitations")
        st.markdown("""
- **Data completeness:** WhoScored event data lacks some event types available in commercial
  feeds (e.g. Opta, StatsBomb). Some metrics are approximated.
- **Context blindness:** Per-90 stats don't account for game state, opponent quality, or
  tactical role constraints.
- **Sample size:** Single-season analysis — players with injuries or late transfers may have
  insufficient data.
- **Positional classification:** WhoScored positions may not perfectly reflect a player's
  actual tactical role.
- **Transfer data coverage:** Players who leave Serie A mid-season are not on any team's
  Transfermarkt squad page and require manual entry via `tm_manual_players.csv`.
        """)

    with col_right:
        st.markdown("### Data Sources")
        st.info(
            "**Match events — WhoScored**\n\n"
            "Extracted per-match for Serie A 2025/26 using a semi-automated SeleniumBase pipeline.\n\n"
            "**Transfer data — Transfermarkt**\n\n"
            "Market value, contract expiry, and feasibility scraped from team squad pages "
            "using the same UC-mode browser. Results are cached locally; "
            "players who transfer mid-season can be added via a manual override CSV.\n\n"
            "This project is for **personal educational and portfolio purposes only**."
        )

        st.markdown("### Dataset Coverage")
        matches_path = config.DATA_PROCESSED / "matches.csv"
        final_path   = config.DATA_FINAL / "chance_creators.csv"
        if matches_path.exists():
            m_df = pd.read_csv(matches_path)
            teams_in_data = set(m_df["home_team_name"].dropna()) | set(m_df["away_team_name"].dropna())
            n_players = len(pd.read_csv(final_path)) if final_path.exists() else "—"
            st.markdown(f"""
| | |
|---|---|
| Matches processed | **{len(m_df)}** |
| Teams | **{len(teams_in_data)}** |
| Eligible midfielders | **{n_players}** |
| Min. minutes threshold | **{config.MIN_MINUTES_PLAYED}** |
            """)
        else:
            st.caption("Run the pipeline to see coverage stats.")

        st.markdown("### Future Improvements")
        st.markdown("""
- Opponent-adjusted metrics (performance vs. top-6 vs. bottom-6)
- Expected assists model from pass end-locations
- Video analysis notes for shortlisted players
        """)

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
    st.stop()


# ─── Apply Filters ────────────────────────────────────────────────────
mask = df["minutes_played"] >= min_mins
if "age" in df.columns:
    mask &= (df["age"] >= age_range[0]) & (df["age"] <= age_range[1])
if selected_positions:
    mask &= df["position"].isin(selected_positions)
if selected_teams:
    mask &= df["team_name"].isin(selected_teams)
if has_archetypes and selected_archetypes:
    mask &= df["archetype"].isin(selected_archetypes)
if has_tm_data and selected_feasibility:
    mask &= df["transfer_feasibility"].isin(selected_feasibility)

filtered = df[mask].copy()


# ─── Header & KPIs ────────────────────────────────────────────────────
st.title("⚽ Serie A Chance Creators 2025/26")
st.markdown("A data-driven scouting tool identifying creative midfielders using WhoScored match event data.")

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f'<div class="metric-card"><h3>{len(filtered)}</h3><p>Players shown</p></div>',
                unsafe_allow_html=True)
with k2:
    top = filtered.nlargest(1, score_col)["player_name"].values[0] if len(filtered) else "—"
    st.markdown(f'<div class="metric-card"><h3 style="font-size:1.1rem">{top}</h3><p>Top ranked player</p></div>',
                unsafe_allow_html=True)
with k3:
    avg = filtered[score_col].mean() if len(filtered) else 0
    st.markdown(f'<div class="metric-card"><h3>{avg:.1f}</h3><p>Avg. score (filtered)</p></div>',
                unsafe_allow_html=True)
with k4:
    n_teams = filtered["team_name"].nunique() if len(filtered) else 0
    st.markdown(f'<div class="metric-card"><h3>{n_teams}</h3><p>Teams represented</p></div>',
                unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# ─── Tabs ─────────────────────────────────────────────────────────────
tab_ranking, tab_profile, tab_compare, tab_scatter, tab_archetypes = st.tabs([
    "📊 Rankings", "👤 Player Profile", "🔍 Compare", "📈 Scatter Explorer", "🧬 Archetypes"
])


# ══════════════════════════════════════════════════════════════════════
# TAB 1 — RANKINGS
# ══════════════════════════════════════════════════════════════════════
with tab_ranking:
    st.markdown('<p class="section-title">Top Chance Creators</p>', unsafe_allow_html=True)

    sort_options   = {label(c): c for c in [score_col] + CORE_METRICS if c in filtered.columns}
    sort_by_label  = st.selectbox("Sort by", list(sort_options.keys()), index=0)
    sort_col       = sort_options[sort_by_label]

    ranked = (
        filtered.sort_values(sort_col, ascending=False)
        .reset_index(drop=True)
    )

    # ── Horizontal bar chart – top 20 ──
    top_n = ranked.head(20).copy()
    top_n["rank_label"] = top_n["player_name"] + "  ·  " + top_n["team_name"]

    bar_color = (
        top_n["archetype"].map(archetype_color)
        if has_archetypes and "archetype" in top_n.columns
        else "#007BFF"
    )

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=top_n[sort_col],
        y=top_n["rank_label"],
        orientation="h",
        marker_color=bar_color,
        marker_line_width=0,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Team: %{customdata[1]}<br>"
            f"{sort_by_label}: %{{x:.2f}}<br>"
            "Score: %{customdata[2]:.1f}<extra></extra>"
        ),
        customdata=top_n[["player_name", "team_name", score_col]].values,
    ))

    fig_bar.update_layout(**dark_layout(
        height=max(360, len(top_n) * 26),
        yaxis=dict(autorange="reversed", tickfont=dict(size=11, color=D_TEXT)),
        xaxis=dict(title=sort_by_label, gridcolor=D_GRID, color=D_TEXT),
        margin=dict(l=10, r=30, t=10, b=40),
    ))
    bar_event = st.plotly_chart(fig_bar, use_container_width=True, on_select="rerun")

    if bar_event.selection.points:
        clicked_player = bar_event.selection.points[0]["customdata"][0]
        st.session_state["profile_player"] = clicked_player
        components.html("""
            <script>
                const tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
                for (const tab of tabs) {
                    if (tab.innerText.includes('Player Profile')) {
                        tab.click();
                        break;
                    }
                }
            </script>
        """, height=0)

    # ── Full table ──
    display_cols   = ["player_name", "team_name", "position", "age", "minutes_played"]
    if has_archetypes:
        display_cols.append("archetype")
    display_cols  += [score_col] + [m for m in CORE_METRICS if m in filtered.columns]
    if has_tm_data:
        display_cols += ["market_value_eur", "contract_expires", "transfer_feasibility"]
    available_cols = [c for c in display_cols if c in ranked.columns]

    tbl = ranked[available_cols].copy()
    tbl.index = range(1, len(tbl) + 1)
    tbl_rename = {
        **rename_map,
        "market_value_eur":    "Market Value (€)",
        "contract_expires":    "Contract Until",
        "transfer_feasibility": "Feasibility",
    }
    tbl_display = tbl.rename(columns=tbl_rename)

    col_cfg = {
        "Score":           st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
        "Mins":            st.column_config.NumberColumn("Mins", format="%d"),
        "Age":             st.column_config.NumberColumn("Age",  format="%d"),
        "Market Value (€)": st.column_config.NumberColumn("Market Value (€)", format="€%,.0f"),
        "Contract Until":  st.column_config.NumberColumn("Contract Until", format="%d"),
    }
    st.dataframe(tbl_display, use_container_width=True, height=420, column_config=col_cfg)



# ══════════════════════════════════════════════════════════════════════
# TAB 2 — PLAYER PROFILE
# ══════════════════════════════════════════════════════════════════════
with tab_profile:
    st.markdown('<p class="section-title">Player Profile</p>', unsafe_allow_html=True)

    player_options = (
        filtered.sort_values(score_col, ascending=False)["player_name"].tolist()
        if len(filtered) else []
    )
    profile_default = st.session_state.get("profile_player")
    default_idx = (
        player_options.index(profile_default)
        if profile_default in player_options
        else 0
    )
    selected_player = st.selectbox(
        "Select a player", options=player_options,
        index=default_idx,
        help="Players sorted by chance-creation score",
    )

    if selected_player:
        row       = filtered[filtered["player_name"] == selected_player].iloc[0]
        score_val = float(row.get(score_col, 0) or 0)
        arch      = row.get("archetype", "") if has_archetypes else ""
        bar_col   = archetype_color(arch) if arch else "#0095FF"

        age_str  = f"{int(row['age'])}"      if "age"      in row and pd.notna(row["age"])      else "—"
        pos_str  = str(row["position"])      if "position" in row and pd.notna(row["position"]) else "—"
        mins_val = int(row["minutes_played"]) if "minutes_played" in row and pd.notna(row["minutes_played"]) else 0
        apps_val = int(row["appearances"])    if "appearances"    in row and pd.notna(row["appearances"])    else 0

        # ── Header banner ──
        # Build TM row only when enriched data is available
        if has_tm_data:
            mv_raw  = row.get("market_value_eur")
            ct_raw  = row.get("contract_expires")
            feasib  = row.get("transfer_feasibility", "Unknown")
            mv_str  = (
                f"€{mv_raw / 1_000_000:.1f}M" if pd.notna(mv_raw) and mv_raw >= 1_000_000
                else f"€{mv_raw / 1_000:.0f}K" if pd.notna(mv_raw) and mv_raw >= 1_000
                else "—"
            )
            ct_str  = str(int(ct_raw)) if pd.notna(ct_raw) else "—"
            feasib_colors = {
                "Expiring": "#22c55e", "Mid-term": "#f59e0b",
                "Locked": "#ef4444",   "Unknown": "#64748b",
            }
            fc = feasib_colors.get(feasib, "#64748b")
            tm_html = (
                f'<p style="margin:8px 0 0;font-size:0.82rem;display:flex;align-items:center;gap:10px">'
                f'<span style="color:#64748b">Market Value</span>'
                f'<span style="color:#f1f5f9;font-weight:600">{mv_str}</span>'
                f'<span style="color:#334155">·</span>'
                f'<span style="color:#64748b">Contract Until</span>'
                f'<span style="color:#f1f5f9;font-weight:600">{ct_str}</span>'
                f'<span style="color:#334155">·</span>'
                f'<span style="background:{fc}22;color:{fc};border:1px solid {fc}55;'
                f'border-radius:4px;padding:1px 8px;font-size:0.76rem;font-weight:600">'
                f'{feasib}</span>'
                f'</p>'
            )
        else:
            tm_html = ""

        st.markdown(
            f"""<div style="background:#1e293b;border-radius:10px;padding:18px 24px;
                            border-left:5px solid {bar_col};margin-bottom:16px;">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
                  <div>
                    <h2 style="margin:0;color:#f1f5f9">{selected_player}</h2>
                    <p style="margin:4px 0 0;color:#94a3b8;font-size:0.95rem">
                      {row['team_name']} &nbsp;·&nbsp; {pos_str} &nbsp;·&nbsp; Age {age_str}
                      {"&nbsp;·&nbsp;<em>" + arch + "</em>" if arch else ""}
                    </p>
                    <p style="margin:6px 0 0;color:#64748b;font-size:0.82rem">
                      {mins_val:,} minutes played &nbsp;·&nbsp; {apps_val} appearances
                    </p>
                    {tm_html}
                  </div>
                  <div style="text-align:center">
                    <div style="background:{bar_col};color:white;border-radius:50%;
                                width:68px;height:68px;display:flex;align-items:center;
                                justify-content:center;font-size:1.5rem;font-weight:bold">
                      {score_val:.0f}
                    </div>
                    <p style="margin:4px 0 0;color:#64748b;font-size:0.75rem">Score</p>
                  </div>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        # ── Radar  |  Per-90 bar chart ──
        col_radar, col_bars = st.columns([1, 1])

        with col_radar:
            if PCT_COLS:
                fig_radar = create_radar_chart(row.to_dict(), metrics=CORE_METRICS, title="")
                st.plotly_chart(fig_radar, use_container_width=True)

        with col_bars:
            metrics_in_row = [m for m in CORE_METRICS if m in row and pd.notna(row[m])]
            player_vals    = [float(row[m]) for m in metrics_in_row]
            dataset_maxes  = [float(filtered[m].max()) for m in metrics_in_row]
            pct_vals       = [float(row.get(f"{m}_pct", 0) or 0) for m in metrics_in_row]
            display_labels = [label(m) for m in metrics_in_row]

            fig_bars = go.Figure()
            fig_bars.add_trace(go.Bar(
                x=dataset_maxes, y=display_labels, orientation="h",
                marker_color="rgba(255,255,255,0.08)", marker_line_width=0,
                showlegend=False, hoverinfo="skip",
            ))
            fig_bars.add_trace(go.Bar(
                x=player_vals, y=display_labels, orientation="h",
                marker_color=bar_col, marker_line_width=0, showlegend=False,
                hovertemplate="<b>%{y}</b><br>Value / 90: %{x:.2f}<br>Percentile: %{customdata:.0f}th<extra></extra>",
                customdata=pct_vals,
            ))
            fig_bars.update_layout(**dark_layout(
                barmode="overlay", height=320,
                margin=dict(l=10, r=20, t=36, b=10),
                xaxis=dict(visible=False),
                yaxis=dict(tickfont=dict(size=11, color=D_TEXT), autorange="reversed"),
                title=dict(text="Per-90 vs. league max", font=dict(size=12, color=D_TICK), x=0),
            ))
            st.plotly_chart(fig_bars, use_container_width=True)

        st.markdown("---")

        # ── Season totals — styled cards ──
        st.markdown('<p class="section-title">Season Totals</p>', unsafe_allow_html=True)

        TOTAL_META = {
            "goals":                   ("⚽", "Goals"),
            "assists":                 ("🎯", "Assists"),
            "key_passes":              ("🔑", "Key Passes"),
            "shot_creating_actions":   ("💥", "Shot-Creating"),
            "through_balls":           ("🎳", "Through Balls"),
            "passes_into_penalty_area":("📦", "Passes into Box"),
            "passes_into_final_third": ("➡️", "Into Final Third"),
            "successful_dribbles":     ("🏃", "Dribbles Won"),
            "progressive_passes":      ("📈", "Progressive Passes"),
        }

        totals = [
            (icon, lbl, int(row[col]))
            for col, (icon, lbl) in TOTAL_META.items()
            if col in row and pd.notna(row[col])
        ]

        if totals:
            cols_per_row = 5
            for chunk_start in range(0, len(totals), cols_per_row):
                chunk = totals[chunk_start: chunk_start + cols_per_row]
                card_cols = st.columns(len(chunk))
                for ci, (icon, lbl, val) in enumerate(chunk):
                    with card_cols[ci]:
                        st.markdown(
                            f"""<div style="background:#1e293b;border-radius:8px;padding:14px 10px;
                                            text-align:center;border-top:3px solid {bar_col}">
                                  <div style="font-size:1.5rem">{icon}</div>
                                  <div style="font-size:1.6rem;font-weight:700;color:#f1f5f9;
                                              line-height:1.2">{val}</div>
                                  <div style="font-size:0.75rem;color:#94a3b8;margin-top:2px">{lbl}</div>
                                </div>""",
                            unsafe_allow_html=True,
                        )
                st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)
    else:
        st.info("No players match the current filters.")


# ══════════════════════════════════════════════════════════════════════
# TAB 3 — COMPARE
# ══════════════════════════════════════════════════════════════════════
with tab_compare:
    st.markdown('<p class="section-title">Compare Players</p>', unsafe_allow_html=True)

    player_list = (
        filtered.sort_values(score_col, ascending=False)["player_name"].tolist()
        if len(filtered) else []
    )
    selected_players = st.multiselect(
        "Select up to 4 players to compare",
        options=player_list,
        max_selections=4,
        help="Players are sorted by chance-creation score",
    )

    if len(selected_players) >= 2:
        compare_df = filtered[filtered["player_name"].isin(selected_players)].copy()

        # ── Radar ──
        fig_radar = create_comparison_radar(
            compare_df.to_dict("records"),
            compare_df["player_name"].tolist(),
            metrics=CORE_METRICS,
        )
        st.plotly_chart(fig_radar, use_container_width=True)

        st.markdown("---")

        # ── Grouped bar chart — actual per-90 values ──
        p90_cols = [m for m in CORE_METRICS if m in compare_df.columns]
        melted = compare_df[["player_name"] + p90_cols].melt(
            id_vars="player_name", var_name="metric", value_name="value"
        )
        melted["metric_label"] = melted["metric"].map(label)

        player_color_map = {
            name: PLAYER_COLORS[i % len(PLAYER_COLORS)][1]
            for i, name in enumerate(compare_df["player_name"].tolist())
        }

        fig_grouped = go.Figure()
        for pname in compare_df["player_name"].tolist():
            sub = melted[melted["player_name"] == pname]
            fig_grouped.add_trace(go.Bar(
                name=pname,
                x=sub["metric_label"],
                y=sub["value"],
                marker_color=player_color_map[pname],
                hovertemplate=f"<b>{pname}</b><br>%{{x}}: %{{y:.2f}}<extra></extra>",
            ))

        fig_grouped.update_layout(**dark_layout(
            barmode="group",
            height=360,
            xaxis=dict(tickangle=-25, tickfont=dict(size=11, color=D_TEXT)),
            yaxis=dict(title="Value / 90", gridcolor=D_GRID, color=D_TEXT),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                        font=dict(color=D_TEXT), bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=10, r=10, t=40, b=80),
        ))
        st.plotly_chart(fig_grouped, use_container_width=True)

        # ── Stats table ──
        show_cols = ["player_name", "team_name", "age", score_col] + p90_cols
        available = [c for c in show_cols if c in compare_df.columns]
        tbl = compare_df[available].set_index("player_name").copy()
        # Round all numeric columns to 2 decimal places
        tbl = tbl.apply(lambda col: col.round(2) if pd.api.types.is_float_dtype(col) else col)
        tbl.columns = [rename_map.get(c, label(c)) for c in tbl.columns]
        st.dataframe(tbl.T, use_container_width=True)

    elif len(selected_players) == 1:
        st.info("Select at least 2 players to compare.")
    else:
        st.info("Select players above to compare their creative profiles.")


# ══════════════════════════════════════════════════════════════════════
# TAB 4 — SCATTER EXPLORER
# ══════════════════════════════════════════════════════════════════════
with tab_scatter:
    st.markdown('<p class="section-title">Metric Explorer</p>', unsafe_allow_html=True)

    p90_options = [m for m in CORE_METRICS if m in filtered.columns]

    if len(p90_options) >= 2:
        c1, c2, c3 = st.columns(3)
        default_x = "key_passes_p90"           if "key_passes_p90"           in p90_options else p90_options[0]
        default_y = "shot_creating_actions_p90" if "shot_creating_actions_p90" in p90_options else p90_options[min(2, len(p90_options) - 1)]

        x_col = c1.selectbox("X axis", options=p90_options, index=p90_options.index(default_x), format_func=label)
        y_col = c2.selectbox("Y axis", options=p90_options, index=p90_options.index(default_y), format_func=label)

        size_options  = ["(none)"] + p90_options
        size_label    = c3.selectbox("Bubble size", options=size_options,
                                     format_func=lambda x: "None" if x == "(none)" else label(x))
        size_col      = None if size_label == "(none)" else size_label

        color_col     = "archetype" if has_archetypes else "team_name"
        color_map     = ARCHETYPE_COLORS if has_archetypes else None

        # ── Build scatter ──
        plot_df = filtered.copy()
        plot_df["_label_top"] = ""  # will fill top-N below

        x_med = filtered[x_col].median()
        y_med = filtered[y_col].median()

        # Top 5 by score get name labels
        top5_names = set(filtered.nlargest(5, score_col)["player_name"])

        fig_sc = go.Figure()

        # Quadrant shading
        x_max = filtered[x_col].max() * 1.05
        y_max = filtered[y_col].max() * 1.05

        for (x0, x1, y0, y1, color, label_text) in [
            (x_med, x_max, y_med, y_max, "rgba(0,230,120,0.07)",  "Elite"),
            (0,     x_med, y_med, y_max, "rgba(255,200,0,0.06)",   "High output"),
            (x_med, x_max, 0,     y_med, "rgba(0,149,255,0.06)",   ""),
            (0,     x_med, 0,     y_med, "rgba(255,255,255,0.02)", ""),
        ]:
            fig_sc.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                             fillcolor=color, line_width=0, layer="below")

        # Median reference lines
        fig_sc.add_vline(x=x_med, line_dash="dot", line_color="rgba(255,255,255,0.25)", line_width=1)
        fig_sc.add_hline(y=y_med, line_dash="dot", line_color="rgba(255,255,255,0.25)", line_width=1)

        # Scatter points per group
        groups = filtered[color_col].dropna().unique() if color_col in filtered.columns else ["all"]
        palette = list(ARCHETYPE_COLORS.values()) if has_archetypes else px.colors.qualitative.Set2

        for gi, group in enumerate(sorted(groups)):
            sub = filtered[filtered[color_col] == group] if color_col in filtered.columns else filtered
            marker_sizes = (sub[size_col] / filtered[size_col].max() * 30 + 8).clip(lower=8).tolist() \
                           if size_col else [10] * len(sub)

            fig_sc.add_trace(go.Scatter(
                x=sub[x_col],
                y=sub[y_col],
                mode="markers",
                name=str(group),
                marker=dict(
                    size=marker_sizes,
                    color=ARCHETYPE_COLORS.get(group, palette[gi % len(palette)]),
                    opacity=0.85,
                    line=dict(width=0.8, color=D_BG),
                ),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    f"{label(x_col)}: %{{x:.2f}}<br>"
                    f"{label(y_col)}: %{{y:.2f}}<br>"
                    "Score: %{customdata[1]:.1f}<br>"
                    "Team: %{customdata[2]}<extra></extra>"
                ),
                customdata=sub[["player_name", score_col, "team_name"]].values,
            ))

        # Annotate top-5 players
        top5_df = filtered.nlargest(5, score_col)
        for _, r in top5_df.iterrows():
            fig_sc.add_annotation(
                x=r[x_col], y=r[y_col],
                text=r["player_name"].split()[-1],
                showarrow=True, arrowhead=2, arrowsize=0.8,
                arrowcolor=D_TICK, ax=15, ay=-18,
                font=dict(size=10, color=D_TEXT),
                bgcolor="rgba(17,24,39,0.80)",
                borderpad=2,
            )

        # Median labels
        fig_sc.add_annotation(x=x_max * 0.98, y=y_med,
                               text=f"median {label(y_col)}", showarrow=False,
                               font=dict(size=9, color=D_TICK), yshift=8)
        fig_sc.add_annotation(x=x_med, y=y_max * 0.98,
                               text=f"median {label(x_col)}", showarrow=False,
                               font=dict(size=9, color=D_TICK), xshift=50)

        fig_sc.update_layout(**dark_layout(
            height=580,
            xaxis=dict(title=label(x_col), gridcolor=D_GRID, zeroline=False, color=D_TEXT),
            yaxis=dict(title=label(y_col), gridcolor=D_GRID, zeroline=False, color=D_TEXT),
            legend=dict(title=color_col.replace("_", " ").title(),
                        orientation="v", yanchor="top", y=1, xanchor="left", x=1.01,
                        font=dict(color=D_TEXT), bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=10, r=130, t=20, b=50),
        ))
        st.plotly_chart(fig_sc, use_container_width=True)

        # ── Top 5 table ──
        st.markdown(f"**Top 5 by {label(y_col)}**")
        top5_tbl = (
            filtered[["player_name", "team_name", "position", x_col, y_col, score_col]]
            .nlargest(5, y_col)
            .rename(columns={"player_name": "Player", "team_name": "Team", "position": "Pos",
                             x_col: label(x_col), y_col: label(y_col), score_col: "Score"})
            .reset_index(drop=True)
        )
        top5_tbl.index += 1
        st.dataframe(top5_tbl, use_container_width=True)

    else:
        st.warning("Not enough per-90 metrics available.")


# ══════════════════════════════════════════════════════════════════════
# TAB 5 — ARCHETYPES
# ══════════════════════════════════════════════════════════════════════
with tab_archetypes:
    st.markdown('<p class="section-title">Creative Archetypes</p>', unsafe_allow_html=True)

    if has_archetypes and len(filtered):
        archetypes = sorted(filtered["archetype"].dropna().unique().tolist())

        # ── Distribution donut + score box ──
        col_donut, col_scores = st.columns([1, 2])

        with col_donut:
            counts = filtered["archetype"].value_counts()
            fig_donut = go.Figure(go.Pie(
                labels=counts.index,
                values=counts.values,
                hole=0.55,
                marker_colors=[archetype_color(a) for a in counts.index],
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>%{value} players (%{percent})<extra></extra>",
            ))
            fig_donut.update_layout(**dark_layout(
                height=280, showlegend=False,
                margin=dict(l=10, r=10, t=10, b=10),
            ))
            st.plotly_chart(fig_donut, use_container_width=True)

        with col_scores:
            # Score distribution violin per archetype
            fig_violin = go.Figure()
            for arch in archetypes:
                sub = filtered[filtered["archetype"] == arch][score_col]
                fig_violin.add_trace(go.Violin(
                    y=sub,
                    name=arch,
                    box_visible=True,
                    meanline_visible=True,
                    fillcolor=archetype_color(arch),
                    line_color=archetype_color(arch),
                    opacity=0.7,
                ))
            fig_violin.update_layout(**dark_layout(
                height=280,
                yaxis=dict(title="Chance Creation Score", gridcolor=D_GRID, color=D_TEXT),
                xaxis=dict(color=D_TEXT),
                margin=dict(l=10, r=10, t=10, b=10),
                showlegend=False,
            ))
            st.plotly_chart(fig_violin, use_container_width=True)

        st.markdown("---")

        # ── Archetype average radar comparison ──
        st.markdown("**Average creative profile per archetype**")
        arch_avg_data = []
        arch_avg_names = []
        for arch in archetypes:
            sub = filtered[filtered["archetype"] == arch]
            avg_row = sub[CORE_METRICS + PCT_COLS].mean().to_dict()
            arch_avg_data.append(avg_row)
            arch_avg_names.append(arch)

        fig_arch_radar = create_comparison_radar(arch_avg_data, arch_avg_names, metrics=CORE_METRICS,
                                                  title="Archetype Average Profiles")
        st.plotly_chart(fig_arch_radar, use_container_width=True)

        st.markdown("---")

        # ── Per-archetype player tables ──
        for archetype in archetypes:
            arch_players = filtered[filtered["archetype"] == archetype].sort_values(
                score_col, ascending=False
            )
            avg_score = arch_players[score_col].mean()

            with st.expander(
                f"**{archetype}** — {len(arch_players)} players · avg score {avg_score:.1f}",
                expanded=False,
            ):
                show_cols  = ["player_name", "team_name", "position", "age", "minutes_played", score_col]
                available  = [c for c in show_cols if c in arch_players.columns]
                tbl        = arch_players[available].head(20).reset_index(drop=True)
                tbl.index += 1
                tbl.columns = [rename_map.get(c, c) for c in tbl.columns]
                st.dataframe(
                    tbl, use_container_width=True,
                    column_config={
                        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
                    },
                )
    else:
        st.info(
            "Archetypes are not available yet. Run the clustering step:\n\n"
            "```bash\npython -m src.features.clustering\n```"
        )


# ─── Footer ───────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "Built by **R. Berk Karatas** · "
    "[GitHub](https://github.com/rberkkaratas) · "
    "[LinkedIn](https://www.linkedin.com/in/rberkkaratas/) · "
    "Data: WhoScored · Serie A 2025/26"
)
