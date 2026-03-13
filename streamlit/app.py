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
from src.visualization.scatter_profiles import create_quadrant_scatter, get_best_quadrant_df

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
    "key_passes_p90":                   "Key Passes / 90",
    "through_balls_p90":                "Through Balls / 90",
    "passes_into_final_third_p90":      "Into Final Third / 90",
    "passes_into_penalty_area_p90":     "Into Box / 90",
    "shot_creating_actions_p90":        "Shot-Creating Actions / 90",
    "successful_dribbles_p90":          "Dribbles / 90",
    "progressive_passes_p90":           "Progressive Passes / 90",
    "assists_p90":                      "Assists / 90",
    "goals_p90":                        "Goals / 90",
    "shots_p90":                        "Shots / 90",
    "crosses_p90":                      "Crosses / 90",
    "half_space_passes_p90":            "Half-Space Passes / 90",
    "penalty_area_touches_p90":         "Box Touches / 90",
    "forward_pass_pct":                 "Forward Pass %",
    "carries_into_final_third_p90":     "Carries into Final Third / 90",
    "possession_won_final_third_p90":   "Poss. Won (Att. Third) / 90",
    "ball_winning_height":              "Ball-Winning Height",
    "pass_accuracy":                    "Pass Accuracy (%)",
    "dribble_success_rate":             "Dribble Success (%)",
    "tackle_success_rate":              "Tackle Success (%)",
    "aerial_win_rate":                  "Aerial Win Rate (%)",
    "cross_accuracy":                   "Cross Accuracy (%)",
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

def role_color(name: str) -> str:
    return config.ROLE_COLORS.get(name, "#888")

def role_score_col(role: str) -> str:
    return f"{config.ROLE_SCORE_COL_PREFIX}{role}"


# ─── Role Descriptions ────────────────────────────────────────────────
ROLE_DESCRIPTIONS = {
    "Playmaker":        "Directly creates goal-scoring opportunities — key passes, through balls, penalty area delivery.",
    "Ball Progressor":  "Advances the team up the pitch — progressive passes, carries into the final third, high forward-pass rate.",
    "Ball Winner":      "Recovers possession and disrupts opponents — tackles, interceptions, pressing high up the pitch.",
    "Defensive Shield": "Protects the defensive line — clearances, blocks, aerial dominance.",
    "Dribbler":         "Creates through individual ball-carrying — beating opponents, penetrating the box.",
    "Wide Creator":     "Delivers from wide areas — crosses, half-space passes, penalty area delivery.",
}


# ─── Match Log Helpers ────────────────────────────────────────────────

@st.cache_data
def load_raw_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load per-match player stats and match metadata for the match log."""
    raw_players_path = config.DATA_PROCESSED / "players.csv"
    matches_path     = config.DATA_PROCESSED / "matches.csv"
    raw_players = pd.read_csv(raw_players_path) if raw_players_path.exists() else pd.DataFrame()
    matches     = pd.read_csv(matches_path)     if matches_path.exists()     else pd.DataFrame()
    return raw_players, matches


def _parse_date(date_int):
    """Parse WhoScored date integer (DDMMYYYY, no leading zero) to datetime."""
    try:
        return pd.to_datetime(str(int(date_int)).zfill(8), format="%d%m%Y")
    except Exception:
        return pd.NaT


def build_match_log(
    player_id: float,
    team_id: int,
    matches_df: pd.DataFrame,
    raw_players_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a full-season match log for one player.
    Rows for matches the player didn't appear in are included with status='DNP'.
    """
    if matches_df.empty or raw_players_df.empty:
        return pd.DataFrame()

    # All matches where the player's club appeared
    team_matches = matches_df[
        (matches_df["home_team_id"] == team_id) |
        (matches_df["away_team_id"] == team_id)
    ].copy()
    team_matches["date"] = team_matches["date_str"].apply(_parse_date)
    team_matches = team_matches.sort_values("date").reset_index(drop=True)

    # Per-match player stats
    stat_cols = [
        "match_id", "minutes_played", "isFirstEleven", "rating",
        "goals", "assists", "key_passes", "through_balls",
        "successful_dribbles", "crosses", "progressive_passes",
        "shots", "tackles", "interceptions",
    ]
    pid = float(player_id)
    player_rows = raw_players_df[raw_players_df["player_id"] == pid].copy()
    available_stat_cols = [c for c in stat_cols if c in player_rows.columns]
    player_rows = player_rows[available_stat_cols]

    log = team_matches.merge(player_rows, on="match_id", how="left")

    log["is_home"] = log["home_team_id"] == team_id
    log["opponent"] = log.apply(
        lambda r: r["away_team_name"] if r["is_home"] else r["home_team_name"], axis=1
    )
    log["venue"] = log["is_home"].map({True: "H", False: "A"})

    def _score(r):
        if pd.isna(r["home_score"]):
            return "?–?"
        return f"{int(r['home_score'])}–{int(r['away_score'])}"

    def _result(r):
        if pd.isna(r["home_score"]):
            return "?"
        hs, as_ = int(r["home_score"]), int(r["away_score"])
        if r["is_home"]:
            return "W" if hs > as_ else ("D" if hs == as_ else "L")
        return "W" if as_ > hs else ("D" if as_ == hs else "L")

    def _status(r):
        if pd.isna(r.get("minutes_played")):
            return "DNP"
        return "Started" if r.get("isFirstEleven") else "Sub"

    log["score"]  = log.apply(_score, axis=1)
    log["result"] = log.apply(_result, axis=1)
    log["status"] = log.apply(_status, axis=1)

    # Fill counting stats with 0 for DNP rows
    count_cols = ["goals", "assists", "key_passes", "through_balls",
                  "successful_dribbles", "crosses", "progressive_passes",
                  "shots", "tackles", "interceptions"]
    for col in count_cols:
        if col in log.columns:
            log[col] = log[col].fillna(0).astype(int)
    log["minutes_played"] = log["minutes_played"].fillna(0).astype(int)

    return log


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
raw_players_df, matches_df = load_raw_data()

if "profile_player" not in st.session_state:
    st.session_state["profile_player"] = None

if "shot_creating_actions_p90" not in df.columns:
    if "key_passes_p90" in df.columns and "successful_dribbles_p90" in df.columns:
        df["shot_creating_actions_p90"] = df["key_passes_p90"] + df["successful_dribbles_p90"]

has_archetypes  = "archetype" in df.columns
has_tm_data     = "market_value_eur" in df.columns
has_roles       = config.PRIMARY_ROLE_COL in df.columns
ALL_ROLES       = list(config.ROLE_WEIGHTS.keys())
ROLE_SCORE_COLS = [role_score_col(r) for r in ALL_ROLES if role_score_col(r) in df.columns]
CORE_METRICS    = [m for m in config.CHANCE_CREATION_METRICS if m in df.columns]
PCT_COLS        = [f"{m}_pct" for m in CORE_METRICS if f"{m}_pct" in df.columns]
score_col       = "chance_creation_score"

rename_map = {
    "player_name": "Player", "team_name": "Team", "position": "Pos",
    "age": "Age", "minutes_played": "Mins",
    "archetype": "Archetype",
    config.PRIMARY_ROLE_COL: "Role",
    score_col: "CC Score",
}
rename_map.update({m: label(m) for m in CORE_METRICS})
rename_map.update({role_score_col(r): r for r in ALL_ROLES})


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
                All filters apply across every tab.
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

        # ── Roles ──
        st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)
        st.markdown('<p style="font-size:0.72rem;font-weight:600;color:#64748b;'
                    'text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px">'
                    'Role</p>', unsafe_allow_html=True)
        selected_roles = st.multiselect(
            "Midfielder role", options=ALL_ROLES, default=ALL_ROLES,
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
    selected_roles = ALL_ROLES
    if has_tm_data:
        selected_feasibility = ["Expiring", "Mid-term", "Locked", "Unknown"]


# ─── About Page ───────────────────────────────────────────────────────
if selected_page == "About":
    st.markdown("## About This Project")
    st.markdown(
        "This dashboard profiles **Serie A midfielders** in 2025/26 across six tactical roles "
        "using raw match event data from WhoScored — built as a data-driven scouting tool "
        "a sporting director or head scout could act on."
    )
    st.markdown("---")

    about_tab_usage, about_tab_method, about_tab_data = st.tabs([
        "How to Use", "Methodology", "Data & Coverage"
    ])

    # ══════════════════════════════════════════════════════════════════
    # HOW TO USE
    # ══════════════════════════════════════════════════════════════════
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
- Rank all eligible midfielders by CC Score, any role score, or a specific per-90 metric.
- Top-25 horizontal bar chart, coloured by primary role. **Click a bar** to jump straight to that player's Scout Report.
- Full table with progress-bar columns for CC Score and all six role scores. When TM data is available, Market Value, Contract Until, and Feasibility are appended.
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
- Pick a player (sorted by CC Score). Pre-populated if you clicked a bar in Shortlist.
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
- Select 2–4 players (sorted by CC Score).
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
- Points coloured by primary role. Quadrant shading highlights the elite zone (top-right). Top-5 players by CC Score are labelled.

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

Each chart marks median dividers, corner labels (green = best quadrant), and blue pill-badge annotations for the top 8 players by CC Score.
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

    # ══════════════════════════════════════════════════════════════════
    # METHODOLOGY
    # ══════════════════════════════════════════════════════════════════
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

            # Build one expandable block per role
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

    # ══════════════════════════════════════════════════════════════════
    # DATA & COVERAGE
    # ══════════════════════════════════════════════════════════════════
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
    st.stop()


# ─── Apply Filters ────────────────────────────────────────────────────
mask = df["minutes_played"] >= min_mins
if "age" in df.columns:
    mask &= (df["age"] >= age_range[0]) & (df["age"] <= age_range[1])
if selected_positions:
    mask &= df["position"].isin(selected_positions)
if selected_teams:
    mask &= df["team_name"].isin(selected_teams)
if has_roles and selected_roles and len(selected_roles) < len(ALL_ROLES):
    mask &= df[config.PRIMARY_ROLE_COL].isin(selected_roles)
if has_tm_data and selected_feasibility:
    mask &= df["transfer_feasibility"].isin(selected_feasibility)

filtered = df[mask].copy()


# ─── Header & KPIs ────────────────────────────────────────────────────
st.title("⚽ Serie A Midfielders 2025/26")
st.markdown("A data-driven scouting tool profiling midfielders across 6 roles using WhoScored match event data.")

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f'<div class="metric-card"><h3>{len(filtered)}</h3><p>Players shown</p></div>',
                unsafe_allow_html=True)
with k2:
    n_teams = filtered["team_name"].nunique() if len(filtered) else 0
    st.markdown(f'<div class="metric-card"><h3>{n_teams}</h3><p>Teams represented</p></div>',
                unsafe_allow_html=True)
with k3:
    if has_roles and len(filtered) and config.PRIMARY_ROLE_COL in filtered.columns:
        mode_role = filtered[config.PRIMARY_ROLE_COL].mode()
        most_common_role = mode_role[0] if len(mode_role) else "—"
    else:
        most_common_role = "—"
    st.markdown(f'<div class="metric-card"><h3 style="font-size:1.0rem">{most_common_role}</h3><p>Most common role</p></div>',
                unsafe_allow_html=True)
with k4:
    top_cc = filtered.nlargest(1, score_col)["player_name"].values[0] if len(filtered) else "—"
    st.markdown(f'<div class="metric-card"><h3 style="font-size:1.0rem">{top_cc}</h3><p>Top CC creator</p></div>',
                unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# ─── Tabs ─────────────────────────────────────────────────────────────
tab_shortlist, tab_role_map, tab_scout, tab_compare, tab_explore = st.tabs([
    "📊 Shortlist", "⚡ Role Map", "👤 Scout Report", "🔍 Compare", "📈 Explore"
])


# ══════════════════════════════════════════════════════════════════════
# TAB 1 — SHORTLIST (was Rankings)
# ══════════════════════════════════════════════════════════════════════
with tab_shortlist:
    st.markdown('<p class="section-title">Midfielder Shortlist</p>', unsafe_allow_html=True)
    st.caption("Midfielders ranked by chance-creation output. Sort by role score or individual metric. Click a bar to open the Scout Report.")

    role_sort_opts  = {f"{r}": role_score_col(r) for r in ALL_ROLES if role_score_col(r) in filtered.columns}
    metric_sort_opts = {label(c): c for c in CORE_METRICS if c in filtered.columns}
    sort_options    = {"CC Score": score_col, **role_sort_opts, **metric_sort_opts}
    sort_by_label   = st.selectbox("Rank by", list(sort_options.keys()), index=0)
    sort_col        = sort_options[sort_by_label]

    ranked = (
        filtered.sort_values(sort_col, ascending=False)
        .reset_index(drop=True)
    )

    # ── Horizontal bar chart – top 25 ──
    top_n = ranked.head(25).copy()
    top_n["rank_label"] = top_n["player_name"] + "  ·  " + top_n["team_name"]

    bar_color = (
        top_n[config.PRIMARY_ROLE_COL].map(role_color)
        if has_roles and config.PRIMARY_ROLE_COL in top_n.columns
        else (top_n["archetype"].map(archetype_color) if has_archetypes and "archetype" in top_n.columns else "#007BFF")
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
                    if (tab.innerText.includes('Scout Report')) {
                        tab.click();
                        break;
                    }
                }
            </script>
        """, height=0)

    # ── Full table ──
    display_cols = ["player_name", "team_name", "position", "age", "minutes_played"]
    if has_roles:
        display_cols.append(config.PRIMARY_ROLE_COL)
    elif has_archetypes:
        display_cols.append("archetype")
    display_cols += [score_col] + [c for c in ROLE_SCORE_COLS if c in ranked.columns]
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
        "CC Score":        st.column_config.ProgressColumn("CC Score", min_value=0, max_value=100, format="%.1f"),
        "Mins":            st.column_config.NumberColumn("Mins", format="%d"),
        "Age":             st.column_config.NumberColumn("Age",  format="%d"),
        "Market Value (€)": st.column_config.NumberColumn("Market Value (€)", format="€%,.0f"),
        "Contract Until":  st.column_config.NumberColumn("Contract Until", format="%d"),
    }
    for r in ALL_ROLES:
        col_cfg[r] = st.column_config.ProgressColumn(r, min_value=0, max_value=100, format="%.0f")
    st.dataframe(tbl_display, use_container_width=True, height=420, column_config=col_cfg)


# ══════════════════════════════════════════════════════════════════════
# TAB 2 — ROLE MAP (was Roles)
# ══════════════════════════════════════════════════════════════════════
with tab_role_map:
    st.markdown('<p class="section-title">Midfielder Roles</p>', unsafe_allow_html=True)

    # ── Role description pills ──
    pills_html = '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px">'
    for r in ALL_ROLES:
        rc = role_color(r)
        desc = ROLE_DESCRIPTIONS.get(r, "")
        pills_html += (
            f'<div style="background:{rc}18;border:1px solid {rc}55;border-radius:8px;'
            f'padding:10px 14px;flex:1;min-width:260px">'
            f'<span style="color:{rc};font-weight:700;font-size:0.88rem">{r}</span>'
            f'<p style="margin:4px 0 0;font-size:0.78rem;color:#94a3b8;line-height:1.4">{desc}</p>'
            f'</div>'
        )
    pills_html += '</div>'
    st.markdown(pills_html, unsafe_allow_html=True)

    if has_roles and ROLE_SCORE_COLS and len(filtered):

        # ── Distribution donut + role score heatmap ──
        col_donut, col_heat = st.columns([1, 2])

        with col_donut:
            counts = filtered[config.PRIMARY_ROLE_COL].value_counts().reindex(ALL_ROLES, fill_value=0)
            fig_donut = go.Figure(go.Pie(
                labels=counts.index,
                values=counts.values,
                hole=0.55,
                marker_colors=[role_color(r) for r in counts.index],
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>%{value} players (%{percent})<extra></extra>",
            ))
            fig_donut.update_layout(**dark_layout(
                height=300, showlegend=False,
                margin=dict(l=10, r=10, t=10, b=10),
            ))
            st.plotly_chart(fig_donut, use_container_width=True)

        with col_heat:
            # Average role scores per primary-role group → 6×6 identity-like heatmap
            heat_rows = []
            for role in ALL_ROLES:
                sub = filtered[filtered[config.PRIMARY_ROLE_COL] == role]
                if len(sub):
                    avgs = [sub[c].mean() for c in ROLE_SCORE_COLS]
                else:
                    avgs = [0.0] * len(ROLE_SCORE_COLS)
                heat_rows.append(avgs)

            role_short = [r.replace("Ball ", "").replace("Defensive ", "Def. ") for r in ALL_ROLES]
            fig_heat = go.Figure(go.Heatmap(
                z=heat_rows,
                x=role_short,
                y=role_short,
                colorscale=[[0, "#0d0f14"], [0.4, "#1d4ed8"], [1.0, "#00d4aa"]],
                zmin=0, zmax=100,
                text=[[f"{v:.0f}" for v in row] for row in heat_rows],
                texttemplate="%{text}",
                textfont=dict(size=11),
                hovertemplate="Primary: %{y}<br>Score as %{x}: %{z:.1f}<extra></extra>",
            ))
            fig_heat.update_layout(**dark_layout(
                height=300,
                xaxis=dict(title="Role score", tickfont=dict(size=10, color=D_TEXT)),
                yaxis=dict(title="Primary role", tickfont=dict(size=10, color=D_TEXT), autorange="reversed"),
                margin=dict(l=10, r=10, t=30, b=10),
                title=dict(text="Average role scores by primary role", font=dict(size=12, color=D_TICK), x=0),
            ))
            st.plotly_chart(fig_heat, use_container_width=True)

        st.markdown("---")

        # ── Per-role expanders ──
        for role in ALL_ROLES:
            role_players = (
                filtered[filtered[config.PRIMARY_ROLE_COL] == role]
                .sort_values(role_score_col(role), ascending=False)
            )
            if len(role_players) == 0:
                continue
            avg = role_players[role_score_col(role)].mean()
            rc  = role_color(role)

            with st.expander(
                f"**{role}** — {len(role_players)} players · avg score {avg:.0f}",
                expanded=False,
            ):
                # Role description text
                role_metric_labels = [label(m) for m in config.ROLE_WEIGHTS[role]]
                st.caption(f"Key metrics: {', '.join(role_metric_labels)}")

                show_cols = (
                    ["player_name", "team_name", "position", "age", "minutes_played",
                     role_score_col(role)]
                    + [m for m in config.ROLE_WEIGHTS[role] if m in role_players.columns]
                )
                avail = [c for c in show_cols if c in role_players.columns]
                tbl = role_players[avail].head(20).reset_index(drop=True)
                tbl.index += 1
                col_rename = {**rename_map, role_score_col(role): f"{role} Score"}
                tbl.columns = [col_rename.get(c, label(c)) for c in tbl.columns]
                st.dataframe(
                    tbl, use_container_width=True,
                    column_config={
                        f"{role} Score": st.column_config.ProgressColumn(
                            f"{role} Score", min_value=0, max_value=100, format="%.0f"
                        ),
                    },
                )
    else:
        st.info(
            "Role scores are not available yet. Re-run the pipeline:\n\n"
            "```bash\n"
            "python -m src.features.chance_creation\n"
            "python -m src.features.clustering  # optional\n"
            "```"
        )


# ══════════════════════════════════════════════════════════════════════
# TAB 3 — SCOUT REPORT (was Player Profile)
# ══════════════════════════════════════════════════════════════════════
with tab_scout:
    st.markdown('<p class="section-title">Scout Report</p>', unsafe_allow_html=True)

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
        help="Players sorted by CC score",
    )
    st.caption("Radar shows percentile ranks within the filtered midfielder group.")

    if selected_player:
        row       = filtered[filtered["player_name"] == selected_player].iloc[0]
        score_val = float(row.get(score_col, 0) or 0)
        arch      = row.get("archetype", "") if has_archetypes else ""
        prim_role = row.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
        bar_col   = role_color(prim_role) if prim_role else (archetype_color(arch) if arch else "#0095FF")

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
                      {"&nbsp;·&nbsp;<em>" + (prim_role or arch) + "</em>" if (prim_role or arch) else ""}
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

        # ── Role ratings ──
        if has_roles and ROLE_SCORE_COLS:
            st.markdown("---")
            st.markdown('<p class="section-title">Role Ratings</p>', unsafe_allow_html=True)

            role_vals  = [float(row.get(c, 0) or 0) for c in ROLE_SCORE_COLS]
            role_names = [c.replace(config.ROLE_SCORE_COL_PREFIX, "") for c in ROLE_SCORE_COLS]
            r_colors   = [role_color(r) for r in role_names]

            fig_roles = go.Figure()
            # Background bar (full 100)
            fig_roles.add_trace(go.Bar(
                x=[100] * len(role_names), y=role_names, orientation="h",
                marker_color="rgba(255,255,255,0.06)", marker_line_width=0,
                showlegend=False, hoverinfo="skip",
            ))
            # Actual role score bar
            fig_roles.add_trace(go.Bar(
                x=role_vals, y=role_names, orientation="h",
                marker_color=r_colors, marker_line_width=0,
                showlegend=False,
                text=[f"{v:.0f}" for v in role_vals],
                textposition="outside",
                textfont=dict(color=D_TEXT, size=11),
                hovertemplate="<b>%{y}</b>: %{x:.1f}<extra></extra>",
            ))
            fig_roles.update_layout(**dark_layout(
                barmode="overlay", height=260,
                margin=dict(l=10, r=60, t=10, b=10),
                xaxis=dict(range=[0, 115], visible=False),
                yaxis=dict(tickfont=dict(size=12, color=D_TEXT), autorange="reversed"),
            ))
            st.plotly_chart(fig_roles, use_container_width=True)

        st.markdown("---")

        # ── Season totals — styled cards ──
        st.markdown('<p class="section-title">Season Totals</p>', unsafe_allow_html=True)

        TOTAL_META = {
            "goals":                    ("⚽", "Goals"),
            "assists":                  ("🎯", "Assists"),
            "key_passes":               ("🔑", "Key Passes"),
            "through_balls":            ("⬆️", "Through Balls"),
            "passes_into_penalty_area": ("📦", "Passes into Box"),
            "half_space_passes":        ("↗️", "Half-Space Passes"),
            "penalty_area_touches":     ("🎯", "Box Touches"),
            "successful_dribbles":      ("🏃", "Dribbles Won"),
            "progressive_passes":       ("📈", "Progressive Passes"),
            "crosses":                  ("🔄", "Crosses"),
        }

        totals = [
            (icon, lbl, col)
            for col, (icon, lbl) in TOTAL_META.items()
            if col in row and pd.notna(row[col])
        ]

        if totals and apps_val > 0:
            cols_per_row = 5
            for chunk_start in range(0, len(totals), cols_per_row):
                chunk = totals[chunk_start: chunk_start + cols_per_row]
                card_cols = st.columns(len(chunk))
                for ci, (icon, lbl, col) in enumerate(chunk):
                    total_val = int(row[col])
                    avg_val   = row[col] / apps_val
                    with card_cols[ci]:
                        st.markdown(
                            f"""<div style="background:#1e293b;border-radius:8px;padding:14px 10px;
                                            text-align:center;border-top:3px solid {bar_col}">
                                  <div style="font-size:1.5rem">{icon}</div>
                                  <div style="font-size:1.6rem;font-weight:700;color:#f1f5f9;
                                              line-height:1.2">{total_val}</div>
                                  <div style="font-size:0.75rem;color:#94a3b8;margin-top:2px">{lbl}</div>
                                  <div style="font-size:0.72rem;color:#64748b;margin-top:3px">{avg_val:.2f} / match</div>
                                </div>""",
                            unsafe_allow_html=True,
                        )
                st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

        # ── Match Log ──────────────────────────────────────────────────
        st.markdown("---")
        st.markdown('<p class="section-title">Match Log</p>', unsafe_allow_html=True)
        st.caption("All fixtures this season. DNP = did not appear in the match.")

        player_id_val = row.get("player_id")
        team_id_val   = row.get("team_id")

        if (
            player_id_val is not None
            and team_id_val is not None
            and not matches_df.empty
            and not raw_players_df.empty
        ):
            match_log = build_match_log(
                player_id  = float(player_id_val),
                team_id    = int(team_id_val),
                matches_df = matches_df,
                raw_players_df = raw_players_df,
            )

            if not match_log.empty:
                # ── Timeline bar chart ──
                RESULT_COLORS = {"W": "#22c55e", "D": "#94a3b8", "L": "#ef4444", "?": "#334155"}
                DNP_COLOR = "#1e293b"

                match_log["bar_color"] = match_log.apply(
                    lambda r: DNP_COLOR if r["status"] == "DNP" else RESULT_COLORS.get(r["result"], "#334155"),
                    axis=1,
                )
                # Use date + opponent so duplicate opponents (home + away)
                # get unique labels and Plotly preserves chronological order.
                match_log["x_label"] = match_log.apply(
                    lambda r: f"{r['date'].strftime('%d %b')} {r['venue']} {r['opponent']}", axis=1
                )
                match_log["hover_text"] = match_log.apply(
                    lambda r: (
                        f"<b>{r['opponent']}</b> ({r['venue']})<br>"
                        f"Score: {r['score']} · {r['result']}<br>"
                        f"Status: {r['status']} · {r['minutes_played']}'"
                        + (f"<br>⚽ {r['goals']}  🎯 {r['assists']}  🔑 {r['key_passes']}"
                           if r["status"] != "DNP" else "")
                    ),
                    axis=1,
                )

                # Annotation text on bars: goals and assists markers
                def _bar_label(r):
                    if r["status"] == "DNP":
                        return ""
                    parts = []
                    if r.get("goals", 0) > 0:
                        parts.extend(["⚽"] * int(r["goals"]))
                    if r.get("assists", 0) > 0:
                        parts.extend(["🎯"] * int(r["assists"]))
                    return " ".join(parts)

                match_log["bar_label"] = match_log.apply(_bar_label, axis=1)

                fig_log = go.Figure()
                fig_log.add_trace(go.Bar(
                    x=match_log["x_label"],
                    y=match_log["minutes_played"],
                    marker_color=match_log["bar_color"].tolist(),
                    marker_line_width=0,
                    text=match_log["bar_label"],
                    textposition="inside",
                    textfont=dict(size=11),
                    hovertext=match_log["hover_text"],
                    hoverinfo="text",
                    showlegend=False,
                ))

                # Dummy traces for the legend
                for result_lbl, color in [("Win", "#22c55e"), ("Draw", "#94a3b8"), ("Loss", "#ef4444"), ("DNP", "#1e293b")]:
                    fig_log.add_trace(go.Bar(
                        x=[None], y=[None],
                        marker_color=color,
                        marker_line_color="#334155",
                        marker_line_width=1,
                        name=result_lbl,
                        showlegend=True,
                    ))

                fig_log.add_hline(
                    y=90, line_dash="dot",
                    line_color="rgba(255,255,255,0.15)", line_width=1,
                )
                fig_log.update_layout(**dark_layout(
                    height=280,
                    barmode="overlay",
                    xaxis=dict(
                        tickangle=-40,
                        tickfont=dict(size=10, color=D_TICK),
                        showgrid=False,
                        categoryorder="array",
                        categoryarray=match_log["x_label"].tolist(),
                    ),
                    yaxis=dict(
                        title="Minutes",
                        range=[0, 105],
                        gridcolor=D_GRID,
                        color=D_TICK,
                        dtick=30,
                    ),
                    legend=dict(
                        orientation="h", yanchor="bottom", y=1.02,
                        xanchor="right", x=1,
                        font=dict(size=11, color=D_TEXT),
                        bgcolor="rgba(0,0,0,0)",
                    ),
                    margin=dict(l=10, r=10, t=30, b=90),
                ))
                st.plotly_chart(fig_log, use_container_width=True)

                # ── Per-match stats table ──
                tbl_cols = ["date", "venue", "opponent", "score", "result", "status",
                            "minutes_played", "goals", "assists", "key_passes",
                            "through_balls", "successful_dribbles", "progressive_passes",
                            "shots", "tackles", "interceptions"]
                avail_tbl = [c for c in tbl_cols if c in match_log.columns]
                tbl_log = match_log[avail_tbl].copy()

                tbl_log["date"] = tbl_log["date"].dt.strftime("%d %b %Y")

                tbl_log.columns = [
                    {"date": "Date", "venue": "H/A", "opponent": "Opponent",
                     "score": "Score", "result": "Result", "status": "Status",
                     "minutes_played": "Mins", "goals": "G", "assists": "A",
                     "key_passes": "KP", "through_balls": "TB",
                     "successful_dribbles": "Drb", "progressive_passes": "PrgP",
                     "shots": "Sh", "tackles": "Tkl", "interceptions": "Int",
                    }.get(c, c)
                    for c in avail_tbl
                ]

                st.dataframe(
                    tbl_log,
                    use_container_width=True,
                    hide_index=True,
                    height=min(35 * len(tbl_log) + 38, 520),
                    column_config={
                        "Mins": st.column_config.ProgressColumn(
                            "Mins", min_value=0, max_value=95, format="%d"
                        ),
                    },
                )
            else:
                st.caption("Match log unavailable — run the pipeline to generate processed data.")
        else:
            st.caption("Match log unavailable — processed data not found.")

    else:
        st.info("No players match the current filters.")


# ══════════════════════════════════════════════════════════════════════
# TAB 4 — COMPARE
# ══════════════════════════════════════════════════════════════════════
with tab_compare:
    st.markdown('<p class="section-title">Compare Players</p>', unsafe_allow_html=True)
    st.caption("Overlay up to 4 players on the same radar to compare their creative profiles.")

    player_list = (
        filtered.sort_values(score_col, ascending=False)["player_name"].tolist()
        if len(filtered) else []
    )
    selected_players = st.multiselect(
        "Select up to 4 players to compare",
        options=player_list,
        max_selections=4,
        help="Players sorted by CC score",
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
# TAB 5 — EXPLORE (merge of Scatter Explorer + Statistical Profiles)
# ══════════════════════════════════════════════════════════════════════
with tab_explore:
    st.markdown('<p class="section-title">Explore</p>', unsafe_allow_html=True)

    explore_mode = st.radio("View", ["Free Explore", "Statistical Profiles"], horizontal=True)

    # ── FREE EXPLORE ──────────────────────────────────────────────────
    if explore_mode == "Free Explore":
        st.caption("Plot any two metrics against each other. Points are colored by primary role.")

        # Dynamically build axis options: all _p90 cols + rate cols present in filtered
        _rate_cols = [
            "pass_accuracy", "dribble_success_rate", "tackle_success_rate",
            "aerial_win_rate", "cross_accuracy", "forward_pass_pct",
        ]
        _p90_cols_dynamic = [c for c in filtered.columns if c.endswith("_p90")]
        _rate_cols_dynamic = [c for c in _rate_cols if c in filtered.columns]
        p90_options = sorted(set(_p90_cols_dynamic + _rate_cols_dynamic))

        if len(p90_options) >= 2:
            c1, c2, c3 = st.columns(3)
            default_x = "key_passes_p90"                if "key_passes_p90"                in p90_options else p90_options[0]
            default_y = "passes_into_penalty_area_p90"  if "passes_into_penalty_area_p90"  in p90_options else p90_options[min(1, len(p90_options) - 1)]

            x_col = c1.selectbox("X axis", options=p90_options, index=p90_options.index(default_x), format_func=label)
            y_col = c2.selectbox("Y axis", options=p90_options, index=p90_options.index(default_y), format_func=label)

            size_options  = ["(none)"] + p90_options
            size_label_sel = c3.selectbox("Bubble size", options=size_options,
                                          format_func=lambda x: "None" if x == "(none)" else label(x))
            size_col      = None if size_label_sel == "(none)" else size_label_sel

            color_col     = config.PRIMARY_ROLE_COL if has_roles else ("archetype" if has_archetypes else "team_name")
            color_map     = config.ROLE_COLORS if has_roles else (ARCHETYPE_COLORS if has_archetypes else None)

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
            _pal   = list((color_map or {}).values()) or px.colors.qualitative.Set2

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
                        color=(color_map or {}).get(group, _pal[gi % len(_pal)]),
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

    # ── STATISTICAL PROFILES ──────────────────────────────────────────
    else:
        st.caption(
            "Fixed quadrant views across 7 dimensions. Solid lines show the median. "
            "Labelled players have the highest CC Score."
        )

        # ── Plot definitions ──────────────────────────────────────────
        SCATTER_PLOTS = [
            dict(
                x_col="pass_accuracy",
                y_col="total_passes_p90",
                x_label="Pass Accuracy (%)",
                y_label="Pass Attempts / 90",
                title="Passing",
                quadrant_labels={
                    "top_left":    "High volume,\nlow accuracy",
                    "top_right":   "High volume,\nhigh accuracy",
                    "bottom_left": "Low volume,\nlow accuracy",
                    "bottom_right":"Low volume,\nhigh accuracy",
                },
                best_quadrant="top_right",
            ),
            dict(
                x_col="progressive_passes_p90",
                y_col="pass_accuracy",
                x_label="Progressive Passes / 90",
                y_label="Pass Accuracy (%)",
                title="Pass Patterns",
                quadrant_labels={
                    "top_left":    "Accurate but\nnot progressive",
                    "top_right":   "Accurate and\nprogressive",
                    "bottom_left": "Inaccurate,\nnot progressive",
                    "bottom_right":"Progressive but\ninaccurate",
                },
                best_quadrant="top_right",
            ),
            dict(
                x_col="aerial_win_rate",
                y_col="aerials_total_p90",
                x_label="Aerial Win Rate (%)",
                y_label="Aerial Attempts / 90",
                title="Aerial Duels",
                quadrant_labels={
                    "top_left":    "High volume,\nlow win rate",
                    "top_right":   "High volume,\nhigh win rate",
                    "bottom_left": "Low volume,\nlow win rate",
                    "bottom_right":"Low volume,\nhigh win rate",
                },
                best_quadrant="top_right",
            ),
            dict(
                x_col="clearances_p90",
                y_col="shots_blocked_p90",
                x_label="Clearances / 90",
                y_label="Blocks / 90",
                title="Defence",
                quadrant_labels={
                    "top_left":    "Shot blocking,\nfew clearances",
                    "top_right":   "Active defender",
                    "bottom_left": "Low defensive\noutput",
                    "bottom_right":"Clearing,\nfew blocks",
                },
                best_quadrant="top_right",
            ),
            dict(
                x_col="possession_lost_p90",
                y_col="possession_won_p90",
                x_label="Possession Lost / 90",
                y_label="Possession Won / 90",
                title="Possession",
                quadrant_labels={
                    "top_left":    "Wins ball often,\nrarely loses it",
                    "top_right":   "High involvement\nboth ways",
                    "bottom_left": "Low\ninvolvement",
                    "bottom_right":"Loses ball often,\nrarely wins it",
                },
                best_quadrant="top_left",
            ),
            dict(
                x_col="tackle_success_rate",
                y_col="tackles_p90",
                x_label="Tackle Success Rate (%)",
                y_label="Tackle Attempts / 90",
                title="Tackling",
                quadrant_labels={
                    "top_left":    "High volume,\nlow success",
                    "top_right":   "High volume,\nhigh success",
                    "bottom_left": "Low volume,\nlow success",
                    "bottom_right":"Low volume,\nhigh success",
                },
                best_quadrant="top_right",
            ),
            dict(
                x_col="cross_accuracy",
                y_col="crosses_p90",
                x_label="Cross Accuracy (%)",
                y_label="Cross Attempts / 90",
                title="Crossing",
                quadrant_labels={
                    "top_left":    "Crossing often,\ninaccurate",
                    "top_right":   "Crossing often,\naccurate",
                    "bottom_left": "Rarely crossing,\ninaccurate",
                    "bottom_right":"Rarely crossing,\naccurate",
                },
                best_quadrant="top_right",
            ),
        ]

        # ── 2-column grid — all plots visible, each expandable ────────
        _pipeline_warning_shown = False
        for row_start in range(0, len(SCATTER_PLOTS), 2):
            col_left, col_right = st.columns(2, gap="small")
            for col_widget, cfg in zip(
                [col_left, col_right],
                SCATTER_PLOTS[row_start : row_start + 2],
            ):
                with col_widget:
                    missing = [
                        c for c in [cfg["x_col"], cfg["y_col"]]
                        if c not in filtered.columns
                    ]
                    if missing:
                        if not _pipeline_warning_shown:
                            st.warning(
                                f"Some columns are missing ({missing}). "
                                "Re-run the pipeline:\n\n"
                                "```bash\n"
                                "python -m src.processing.build_tables\n"
                                "python -m src.features.chance_creation\n"
                                "python -m src.features.clustering\n"
                                "```"
                            )
                            _pipeline_warning_shown = True
                    else:
                        fig = create_quadrant_scatter(
                            df=filtered,
                            x_col=cfg["x_col"],
                            y_col=cfg["y_col"],
                            x_label=cfg["x_label"],
                            y_label=cfg["y_label"],
                            title=cfg["title"],
                            quadrant_labels=cfg["quadrant_labels"],
                            best_quadrant=cfg["best_quadrant"],
                            top_n_annotate=6,
                            highlight_col=score_col,
                            subtitle="Serie A, 2025/26",
                            height=420,
                        )
                        st.plotly_chart(fig, use_container_width=True)


# ─── Footer ───────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "Built by **R. Berk Karatas** · "
    "[GitHub](https://github.com/rberkkaratas) · "
    "[LinkedIn](https://www.linkedin.com/in/rberkkaratas/) · "
    "Data: WhoScored · Serie A 2025/26"
)
