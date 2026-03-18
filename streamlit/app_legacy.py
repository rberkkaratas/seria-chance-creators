"""
Serie A Chance Creators — Scouting Dashboard
----------------------------------------------
Interactive Streamlit app for exploring creative midfielder profiles.

Usage:
    streamlit run streamlit/app.py
"""

import re
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

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
    page_title="Midfielder Scout 2025/26",
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
    .narrative-card {
        background: #1e293b;
        border-radius: 10px;
        padding: 16px 20px;
        line-height: 1.7;
        font-size: 0.92rem;
        color: #cbd5e1;
        height: 100%;
    }
    .strength-pill {
        display: inline-block;
        background: rgba(34,197,94,0.12);
        color: #4ade80;
        border: 1px solid rgba(34,197,94,0.3);
        border-radius: 20px;
        padding: 3px 12px;
        font-size: 0.8rem;
        font-weight: 600;
        margin: 3px 3px 3px 0;
        white-space: nowrap;
    }
    .concern-pill {
        display: inline-block;
        background: rgba(239,68,68,0.12);
        color: #f87171;
        border: 1px solid rgba(239,68,68,0.3);
        border-radius: 20px;
        padding: 3px 12px;
        font-size: 0.8rem;
        font-weight: 600;
        margin: 3px 3px 3px 0;
        white-space: nowrap;
    }
    .peer-rank-bar {
        background: #1a2535;
        border-radius: 8px;
        padding: 10px 16px;
        display: flex;
        align-items: center;
        gap: 12px;
        margin-top: 8px;
    }
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
    "def_actions_p90":                  "Def. Actions / 90",
    "direct_creation_p90":              "Direct Creation / 90",
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

LEAGUE_DISPLAY = {k: v["display_name"] for k, v in config.LEAGUES.items()}
LEAGUE_FLAGS = {
    "Serie_A":        "🇮🇹",
    "Premier_League": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "La_Liga":        "🇪🇸",
    "Bundesliga":     "🇩🇪",
    "Ligue_1":        "🇫🇷",
}

def league_badge(league_key: str) -> str:
    flag = LEAGUE_FLAGS.get(league_key, "")
    name = LEAGUE_DISPLAY.get(league_key, league_key.replace("_", " "))
    return f"{flag} {name}"

def role_color(name: str) -> str:
    return config.ROLE_COLORS.get(name, "#888")

def role_score_col(role: str) -> str:
    return f"{config.ROLE_SCORE_COL_PREFIX}{role}"


# ─── Role Descriptions ────────────────────────────────────────────────
ROLE_ICONS: dict[str, str] = {}   # icons removed — kept for API compatibility

ROLE_DESCRIPTIONS = {
    "Creator":         "Delivers the ball into dangerous areas — through key passes, through balls, crosses, or cut-backs. Creates chances regardless of whether they operate centrally or from wide.",
    "Ball Progressor": "Drives the team forward through carrying and dribbling. Gets the ball into dangerous areas through athletic, direct progression.",
    "Box Threat":      "Lives in the penalty area, shoots often, and creates from proximity. High box-touch volume combined with direct shooting makes them a constant goal threat.",
    "Deep Builder":    "Enables the team through high-volume, accurate, forward-oriented passing. Controls tempo and moves the ball efficiently from deep areas.",
}


# ─── Match Log Helpers ────────────────────────────────────────────────

@st.cache_data
def load_raw_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load per-match player stats and match metadata from all available leagues."""
    processed_root = config.ROOT_DIR / "data" / "processed"
    all_players: list[pd.DataFrame] = []
    all_matches: list[pd.DataFrame] = []

    if processed_root.exists():
        for league_dir in sorted(processed_root.iterdir()):
            if not league_dir.is_dir():
                continue
            for season_dir in sorted(league_dir.iterdir()):
                if not season_dir.is_dir():
                    continue
                p_path = season_dir / "players.csv"
                m_path = season_dir / "matches.csv"
                if p_path.exists():
                    all_players.append(pd.read_csv(p_path))
                if m_path.exists():
                    all_matches.append(pd.read_csv(m_path))

    raw_players = pd.concat(all_players, ignore_index=True) if all_players else pd.DataFrame()
    matches = (
        pd.concat(all_matches, ignore_index=True).drop_duplicates(subset="match_id")
        if all_matches else pd.DataFrame()
    )
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
    all_leagues = config.DATA_FINAL / f"all_leagues_{config.SEASON}.csv"
    enriched    = config.DATA_FINAL / "chance_creators_enriched.csv"
    clustered   = config.DATA_FINAL / "chance_creators_clustered.csv"
    base        = config.DATA_FINAL / "chance_creators.csv"
    if all_leagues.exists():
        return pd.read_csv(all_leagues)
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

has_archetypes      = "archetype" in df.columns
has_tm_data         = "market_value_eur" in df.columns
has_roles           = config.PRIMARY_ROLE_COL in df.columns
has_league_col      = "league" in df.columns
ALL_ROLES           = list(config.ROLE_WEIGHTS.keys())
ROLE_SCORE_COLS     = [role_score_col(r) for r in ALL_ROLES if role_score_col(r) in df.columns]
ROLE_SCORE_COLS_LEAGUE = [f"{config.ROLE_SCORE_COL_PREFIX}{r}_league" for r in ALL_ROLES
                           if f"{config.ROLE_SCORE_COL_PREFIX}{r}_league" in df.columns]
has_league_scores   = bool(ROLE_SCORE_COLS_LEAGUE)
CORE_METRICS        = [m for m in config.CHANCE_CREATION_METRICS if m in df.columns]
PCT_COLS            = [f"{m}_pct" for m in CORE_METRICS if f"{m}_pct" in df.columns]
PCT_COLS_LEAGUE     = [f"{m}_league_pct" for m in CORE_METRICS if f"{m}_league_pct" in df.columns]
score_col           = "chance_creation_score"
ALL_LEAGUES         = sorted(df["league"].dropna().unique().tolist()) if has_league_col else []

rename_map = {
    "player_name": "Player", "team_name": "Team", "position": "Pos",
    "age": "Age", "minutes_played": "Mins",
    "league": "League",
    "archetype": "Archetype",
    config.PRIMARY_ROLE_COL: "Role",
    score_col: "Overall Score",
}
rename_map.update({m: label(m) for m in CORE_METRICS})
rename_map.update({role_score_col(r): r for r in ALL_ROLES})


def player_view_dict(row: pd.Series, pct_suffix: str) -> dict:
    """Returns player dict with {m}_pct remapped to the correct percentile column."""
    d = row.to_dict()
    if pct_suffix != "_pct":
        for m in CORE_METRICS:
            key = f"{m}{pct_suffix}"
            if key in d:
                d[f"{m}_pct"] = d[key]
    return d


# ─── Header placeholder (filled after filters are applied) ────────────
_header_placeholder = st.empty()

st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

# ─── Inline Filters ───────────────────────────────────────────────────
if True:  # always visible
    _fc1, _fc2, _fc3, _fc4 = st.columns(4)

    with _fc1:
        st.caption("Playing Time")
        min_mins = st.slider(
            "Min. minutes played",
            min_value=0,
            max_value=int(df["minutes_played"].max()) if "minutes_played" in df.columns else 2000,
            value=config.MIN_MINUTES_PLAYED,
            step=90,
            label_visibility="collapsed",
        )
        st.caption(f"Min. **{min_mins}** min")

        if "age" in df.columns:
            st.caption("Age Range")
            age_min = int(df["age"].min())
            age_max = int(df["age"].max())
            age_range = st.slider(
                "Age range", age_min, age_max, (age_min, int(config.MAX_AGE)),
                label_visibility="collapsed",
            )
            st.caption(f"**{age_range[0]} – {age_range[1]}** yrs")
        else:
            age_range = (0, 99)

    with _fc2:
        if "position" in df.columns:
            st.caption("Positions")
            all_positions = sorted(df["position"].dropna().unique().tolist())
            selected_positions = st.multiselect(
                "Positions", options=all_positions, default=all_positions,
                label_visibility="collapsed",
            )
        else:
            selected_positions = []

        if has_league_col:
            st.caption("Leagues")
            selected_leagues = st.multiselect(
                "Leagues", options=ALL_LEAGUES, default=ALL_LEAGUES,
                label_visibility="collapsed",
                format_func=league_badge,
            )
        else:
            selected_leagues = []

    with _fc3:
        st.caption("Teams")
        _league_mask_teams = (
            df["league"].isin(selected_leagues) if has_league_col and selected_leagues else pd.Series(True, index=df.index)
        )
        all_teams = sorted(df.loc[_league_mask_teams, "team_name"].dropna().unique().tolist())
        selected_teams = st.multiselect(
            "Teams", options=all_teams, default=[],
            label_visibility="collapsed",
            placeholder="All teams",
        )

        st.caption("Role")
        selected_roles = st.multiselect(
            "Midfielder role", options=ALL_ROLES, default=ALL_ROLES,
            label_visibility="collapsed",
        )

    with _fc4:
        if has_league_col and len(ALL_LEAGUES) > 1:
            st.caption("Percentile Mode")
            percentile_mode = st.radio(
                "Percentile mode",
                options=["All leagues", "Within league"],
                index=0,
                label_visibility="collapsed",
                help="Controls how role scores and radar percentiles are computed.",
            )
        else:
            percentile_mode = "All leagues"

        if has_tm_data:
            st.caption("Transfer Feasibility")
            all_feasibility = ["Expiring", "Mid-term", "Locked", "Unknown"]
            selected_feasibility = st.multiselect(
                "Transfer feasibility", options=all_feasibility, default=all_feasibility,
                label_visibility="collapsed",
            )

if not has_tm_data:
    selected_feasibility = ["Expiring", "Mid-term", "Locked", "Unknown"]





# ─── Apply Filters ────────────────────────────────────────────────────
mask = df["minutes_played"] >= min_mins
if "age" in df.columns:
    mask &= (df["age"] >= age_range[0]) & (df["age"] <= age_range[1])
if selected_positions:
    mask &= df["position"].isin(selected_positions)
if has_league_col and selected_leagues and len(selected_leagues) < len(ALL_LEAGUES):
    mask &= df["league"].isin(selected_leagues)
if selected_teams:
    mask &= df["team_name"].isin(selected_teams)
if has_roles and selected_roles and len(selected_roles) < len(ALL_ROLES):
    mask &= df[config.PRIMARY_ROLE_COL].isin(selected_roles)
if has_tm_data and selected_feasibility:
    mask &= df["transfer_feasibility"].isin(selected_feasibility)

filtered = df[mask].copy()

# ── Active columns based on percentile mode ───────────────────────────
_league_mode = (percentile_mode == "Within league") and has_league_scores
active_pct_suffix        = "_league_pct" if _league_mode else "_pct"
active_role_score_cols   = ROLE_SCORE_COLS_LEAGUE if _league_mode else ROLE_SCORE_COLS
active_primary_role_col  = (
    "primary_role_league"
    if _league_mode and "primary_role_league" in df.columns
    else config.PRIMARY_ROLE_COL
)


# ─── Header & KPIs ────────────────────────────────────────────────────
n_leagues_shown = filtered["league"].nunique() if has_league_col and len(filtered) else 1
_league_label   = "Top 5 Leagues" if n_leagues_shown > 1 else (
    league_badge(filtered["league"].iloc[0]) if has_league_col and len(filtered) else "Serie A"
)

_hdr_n_teams     = filtered["team_name"].nunique() if len(filtered) else 0
_hdr_top_row     = filtered.nlargest(1, score_col) if len(filtered) else filtered
_hdr_top_player  = _hdr_top_row["player_name"].values[0] if len(_hdr_top_row) else "—"
_hdr_top_score   = float(_hdr_top_row[score_col].values[0]) if len(_hdr_top_row) else 0.0
_hdr_top_role    = _hdr_top_row[config.PRIMARY_ROLE_COL].values[0] if has_roles and len(_hdr_top_row) else ""
_hdr_top_rc      = role_color(_hdr_top_role) if _hdr_top_role else "#0095FF"

if has_roles and len(filtered) and config.PRIMARY_ROLE_COL in filtered.columns:
    _hdr_mode_role = filtered[config.PRIMARY_ROLE_COL].mode()
    _hdr_common_role = _hdr_mode_role[0] if len(_hdr_mode_role) else "—"
else:
    _hdr_common_role = "—"
_hdr_common_rc = role_color(_hdr_common_role) if _hdr_common_role != "—" else "#94a3b8"

_header_placeholder.markdown(
    # Title block
    f'<div style="padding:12px 0 28px">'
    f'<div style="font-size:0.75rem;font-weight:600;color:#0095FF;letter-spacing:2px;'
    f'text-transform:uppercase;margin-bottom:12px">Midfielder Scout</div>'
    f'<div style="font-size:2.8rem;font-weight:800;color:#f1f5f9;letter-spacing:-1px;'
    f'line-height:1.1;margin-bottom:12px">{_league_label} · 2025/26</div>'
    f'<div style="font-size:0.95rem;color:#64748b;line-height:1.7;max-width:600px;margin-bottom:28px">'
    f'A data-driven scouting tool profiling qualified midfielders across four tactical roles — '
    f'Creator, Ball Progressor, Box Threat, and Deep Builder — using WhoScored match event data.'
    f'</div>'
    # KPI row
    f'<div style="display:flex;gap:36px;flex-wrap:wrap;padding-top:20px;'
    f'border-top:1px solid #1e293b">'

    f'<div>'
    f'<div style="font-size:2rem;font-weight:800;color:#f1f5f9;line-height:1">{len(filtered)}</div>'
    f'<div style="font-size:0.75rem;color:#94a3b8;margin-top:4px">Players</div>'
    f'</div>'

    f'<div style="width:1px;background:#1e293b;align-self:stretch"></div>'

    f'<div>'
    f'<div style="font-size:2rem;font-weight:800;color:#f1f5f9;line-height:1">{_hdr_n_teams}</div>'
    f'<div style="font-size:0.75rem;color:#94a3b8;margin-top:4px">Teams</div>'
    f'</div>'

    f'<div style="width:1px;background:#1e293b;align-self:stretch"></div>'

    f'<div>'
    f'<div style="font-size:1.3rem;font-weight:700;color:{_hdr_common_rc};line-height:1.2">{_hdr_common_role}</div>'
    f'<div style="font-size:0.75rem;color:#94a3b8;margin-top:4px">Most common role</div>'
    f'</div>'

    f'<div style="width:1px;background:#1e293b;align-self:stretch"></div>'

    f'<div>'
    f'<div style="font-size:1.3rem;font-weight:700;color:{_hdr_top_rc};line-height:1.2">{_hdr_top_player}</div>'
    f'<div style="font-size:0.75rem;color:#94a3b8;margin-top:4px">Top ranked &nbsp;·&nbsp; {_hdr_top_score:.0f}</div>'
    f'</div>'

    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)


# ─── Tabs ─────────────────────────────────────────────────────────────
tab_shortlist, tab_role_map, tab_scout, tab_compare, tab_explore, tab_league, tab_about = st.tabs([
    "📊 Shortlist", "⚡ Role Map", "👤 Scout Report", "🔍 Compare", "📈 Explore", "🌍 League Overview", "ℹ️ About"
])


# ══════════════════════════════════════════════════════════════════════
# TAB 1 — SHORTLIST
# ══════════════════════════════════════════════════════════════════════
with tab_shortlist:
    st.markdown('<p class="section-title">Midfielder Shortlist</p>', unsafe_allow_html=True)

    _active_rsc = active_role_score_cols

    # ── Sort pill buttons — Overall + per-role ─────────────────────────
    _sort_labels = ["Overall"] + [
        r for r in ALL_ROLES
        if role_score_col(r) in filtered.columns
    ]
    _sort_keys = [score_col] + [
        role_score_col(r) for r in ALL_ROLES
        if role_score_col(r) in filtered.columns
    ]
    _prev_label = st.session_state.get("sl_sort_label")
    _default_label = _prev_label if _prev_label in _sort_labels else _sort_labels[0]

    _selected_label = st.pills(
        "Sort shortlist by",
        options=_sort_labels,
        default=_default_label,
        key="sl_sort_pills",
        label_visibility="collapsed",
    )
    _sel = _selected_label if _selected_label in _sort_labels else _sort_labels[0]
    st.session_state["sl_sort_label"] = _sel
    sort_col = _sort_keys[_sort_labels.index(_sel)]
    # Strip leading emoji+space for chart hover labels ("🎯 Creative Playmaker" → "Creative Playmaker")
    sort_label_clean = _sel.split(" ", 1)[-1] if " " in _sel else _sel

    ranked = (
        filtered.sort_values(sort_col, ascending=False)
        .reset_index(drop=True)
    )

    # ── Top 3 podium cards ──
    if len(ranked) >= 1:
        podium = ranked.head(3)
        medals = ["🥇", "🥈", "🥉"]
        pod_cols = st.columns(3)
        for ci, (_, pr) in enumerate(podium.iterrows()):
            pr_role  = pr.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
            pr_rc    = role_color(pr_role) if pr_role else "#0095FF"
            pr_score = pr.get(sort_col, 0)
            pr_lg    = LEAGUE_FLAGS.get(pr.get("league", ""), "") if has_league_col else ""
            with pod_cols[ci]:
                st.markdown(
                    f'<div style="background:#1e293b;border-radius:10px;padding:14px 16px;'
                    f'border-top:3px solid {pr_rc};text-align:center">'
                    f'<div style="font-size:1.4rem">{medals[ci]}</div>'
                    f'<div style="font-size:0.95rem;font-weight:700;color:#f1f5f9;margin-top:6px;'
                    f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                    f'{pr["player_name"]}</div>'
                    f'<div style="font-size:0.78rem;color:#64748b;margin-top:2px">'
                    f'{pr_lg} {pr["team_name"]}</div>'
                    f'<div style="margin-top:8px">'
                    f'<span style="background:{pr_rc};color:white;border-radius:6px;'
                    f'padding:3px 10px;font-size:1.05rem;font-weight:700">{pr_score:.1f}</span>'
                    f'</div>'
                    f'<div style="font-size:0.75rem;color:{pr_rc};margin-top:5px">'
                    f'{pr_role}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        st.markdown("<div style='margin:12px 0'></div>", unsafe_allow_html=True)

    # ── Horizontal bar chart – top 25 ──
    top_n = ranked.head(25).copy()
    top_n["_rank"] = range(1, len(top_n) + 1)
    if has_league_col:
        top_n["rank_label"] = (
            "#" + top_n["_rank"].astype(str) + "  "
            + top_n["league"].map(lambda l: LEAGUE_FLAGS.get(l, "")) + " "
            + top_n["player_name"] + "  ·  " + top_n["team_name"]
        )
    else:
        top_n["rank_label"] = (
            "#" + top_n["_rank"].astype(str) + "  "
            + top_n["player_name"] + "  ·  " + top_n["team_name"]
        )

    bar_color = (
        top_n[config.PRIMARY_ROLE_COL].map(role_color)
        if has_roles and config.PRIMARY_ROLE_COL in top_n.columns
        else (top_n["archetype"].map(archetype_color) if has_archetypes and "archetype" in top_n.columns else "#007BFF")
    )

    # Background track at the axis max so bars read as fills
    _x_max  = float(top_n[sort_col].max()) * 1.18
    _x_avg  = float(ranked[sort_col].mean())
    _is_score = sort_col == score_col or sort_col in [role_score_col(r) for r in ALL_ROLES]
    _track_max = 100.0 if _is_score else _x_max

    fig_bar = go.Figure()

    # Grey background tracks
    fig_bar.add_trace(go.Bar(
        x=[_track_max] * len(top_n),
        y=top_n["rank_label"],
        orientation="h",
        marker_color="rgba(255,255,255,0.05)",
        marker_line_width=0,
        showlegend=False,
        hoverinfo="skip",
    ))

    # Colored value bars
    fig_bar.add_trace(go.Bar(
        x=top_n[sort_col],
        y=top_n["rank_label"],
        orientation="h",
        marker_color=bar_color,
        marker_line_width=0,
        text=[f"{v:.1f}" for v in top_n[sort_col]],
        textposition="outside",
        textfont=dict(size=11, color=D_TEXT),
        cliponaxis=False,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Team: %{customdata[1]}<br>"
            "League: %{customdata[3]}<br>"
            f"{sort_label_clean}: %{{x:.2f}}<br>"
            "Overall Score: %{customdata[2]:.1f}<extra></extra>"
        ),
        customdata=top_n[["player_name", "team_name", score_col,
                           "league" if has_league_col else "team_name"]].values,
        showlegend=False,
    ))

    # Average reference line
    fig_bar.add_vline(
        x=_x_avg,
        line_dash="dot",
        line_color="rgba(255,255,255,0.30)",
        line_width=1.5,
        annotation_text=f"avg {_x_avg:.1f}",
        annotation_position="top",
        annotation_font=dict(size=10, color=D_TICK),
    )

    fig_bar.update_layout(**dark_layout(
        barmode="overlay",
        height=max(400, len(top_n) * 32),
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(size=11, color=D_TEXT),
            ticklabeloverflow="allow",
        ),
        xaxis=dict(
            title=sort_label_clean,
            gridcolor=D_GRID,
            color=D_TEXT,
            range=[0, _track_max * 1.12],
            showgrid=False,
        ),
        margin=dict(l=10, r=60, t=20, b=30),
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
    st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)
    st.caption(f"Showing {len(ranked)} players · sorted by {sort_label_clean} · click a bar above to open the Scout Report")

    display_cols = ["player_name", "team_name"]
    if has_league_col:
        display_cols.append("league")
    display_cols += ["position", "age", "minutes_played"]
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
    if has_league_col:
        tbl["league"] = tbl["league"].map(lambda l: f"{LEAGUE_FLAGS.get(l,'')} {LEAGUE_DISPLAY.get(l, l.replace('_',' '))}")
    if has_roles and config.PRIMARY_ROLE_COL in tbl.columns:
        tbl[config.PRIMARY_ROLE_COL] = tbl[config.PRIMARY_ROLE_COL].map(
            lambda r: r if pd.notna(r) else r
        )
    tbl_rename = {
        **rename_map,
        "market_value_eur":    "Market Value (€)",
        "contract_expires":    "Contract Until",
        "transfer_feasibility": "Feasibility",
    }
    tbl_display = tbl.rename(columns=tbl_rename)

    col_cfg = {
        "Overall Score":          st.column_config.NumberColumn("Overall Score", format="%.1f"),
        "Mins":              st.column_config.NumberColumn("Mins", format="%d"),
        "Age":               st.column_config.NumberColumn("Age",  format="%d"),
        "Market Value (€)":  st.column_config.NumberColumn("Market Value (€)", format="€%,.0f"),
        "Contract Until":    st.column_config.NumberColumn("Contract Until", format="%d"),
    }
    for r in ALL_ROLES:
        col_cfg[r] = st.column_config.NumberColumn(r, format="%.0f")
    st.dataframe(tbl_display, use_container_width=True, height=440, column_config=col_cfg)


# ══════════════════════════════════════════════════════════════════════
# TAB 2 — ROLE MAP (was Roles)
# ══════════════════════════════════════════════════════════════════════
with tab_role_map:

    # ── Zone taxonomy ──────────────────────────────────────────────────
    _PITCH_ZONES = {
        "Deep Builder":    "Deep",
        "Ball Progressor": "Dynamic",
        "Creator":         "Advanced",
        "Box Threat":      "Advanced",
    }
    _ZONE_COLORS = {
        "Deep":     "#FF9800",
        "Dynamic":  "#00C896",
        "Advanced": "#0095FF",
    }
    _ZONE_LABELS = {
        "Deep":     "Deep — builds from the back third",
        "Dynamic":  "Dynamic — drives through midfield",
        "Advanced": "Advanced — creates and threatens in the final third",
    }
    _ZONE_ORDER  = ["Deep", "Dynamic", "Advanced"]
    _ROLE_ABBREV = {
        "Creator":         "Creator",
        "Ball Progressor": "Progressor",
        "Box Threat":      "Box Threat",
        "Deep Builder":    "Deep Builder",
    }

    # ── Header ──────────────────────────────────────────────────────────
    st.markdown('<p class="section-title">Creation Role Taxonomy</p>', unsafe_allow_html=True)
    st.markdown(
        "Four creation-focused roles cover every way a midfielder can generate chances — "
        "from the deep builder to the box threat. Each player is scored 0–100 "
        "per role based on weighted percentile ranks of its defining metrics, and assigned "
        "a **primary role** where they score highest."
    )
    st.markdown("<div style='margin:20px 0 4px'></div>", unsafe_allow_html=True)

    # ── Role cards grouped by pitch zone ────────────────────────────────
    for _zone in _ZONE_ORDER:
        _zone_roles = [r for r in ALL_ROLES if _PITCH_ZONES.get(r) == _zone]
        if not _zone_roles:
            continue
        _zc = _ZONE_COLORS[_zone]
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;margin:18px 0 10px">'
            f'<span style="background:{_zc}22;color:{_zc};border:1px solid {_zc}55;'
            f'border-radius:6px;padding:3px 12px;font-size:0.72rem;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.8px">{_zone}</span>'
            f'<span style="color:#94a3b8;font-size:0.82rem">{_ZONE_LABELS[_zone]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        _card_cols = st.columns(len(_zone_roles))
        for _ci, _role in enumerate(_zone_roles):
            _rc   = role_color(_role)
            _desc = ROLE_DESCRIPTIONS.get(_role, "")
            _key_metrics = [label(m) for m in list(config.ROLE_WEIGHTS.get(_role, {}).keys())[:3]]
            _n = int((filtered[config.PRIMARY_ROLE_COL] == _role).sum()) \
                 if has_roles and config.PRIMARY_ROLE_COL in filtered.columns else 0
            _avg = filtered.loc[
                filtered[config.PRIMARY_ROLE_COL] == _role, role_score_col(_role)
            ].mean() if _n > 0 and role_score_col(_role) in filtered.columns else 0
            with _card_cols[_ci]:
                st.markdown(
                    f'<div style="background:#1e293b;border-radius:10px;padding:16px;'
                    f'border-top:3px solid {_rc};height:100%">'
                    f'<div style="margin-bottom:8px">'
                    f'<span style="font-weight:700;color:#f1f5f9;font-size:0.88rem">{_role}</span>'
                    f'</div>'
                    f'<p style="margin:0 0 12px;font-size:0.78rem;color:#94a3b8;line-height:1.5">{_desc}</p>'
                    f'<div style="border-top:1px solid #334155;padding-top:8px">'
                    f'<p style="margin:0 0 3px;font-size:0.67rem;color:#94a3b8;'
                    f'text-transform:uppercase;letter-spacing:0.6px">Key metrics</p>'
                    f'<p style="margin:0;font-size:0.74rem;color:{_rc}">'
                    f'{" · ".join(_key_metrics)}</p>'
                    f'</div>'
                    f'<div style="margin-top:10px;display:flex;justify-content:space-between">'
                    f'<span style="font-size:0.72rem;color:#64748b">{_n} players</span>'
                    f'<span style="font-size:0.72rem;color:{_rc};font-weight:600">'
                    f'avg {_avg:.0f}</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    if has_roles and ROLE_SCORE_COLS and len(filtered):

        st.markdown("---")

        # ── Distribution + Versatility Matrix ──────────────────────────
        st.markdown('<p class="section-title">Who plays what?</p>', unsafe_allow_html=True)
        st.caption("Role distribution across the filtered player pool, and how specialised each group is.")

        col_donut, col_heat = st.columns([1, 2])

        with col_donut:
            _counts = filtered[config.PRIMARY_ROLE_COL].value_counts().reindex(ALL_ROLES, fill_value=0)
            _total  = int(_counts.sum())
            fig_donut = go.Figure(go.Pie(
                labels=_counts.index,
                values=_counts.values,
                hole=0.6,
                marker_colors=[role_color(r) for r in _counts.index],
                textinfo="percent",
                textposition="outside",
                hovertemplate="<b>%{label}</b><br>%{value} players · %{percent}<extra></extra>",
                pull=[0.05 if v == _counts.max() else 0 for v in _counts.values],
            ))
            fig_donut.add_annotation(
                text=f"<b>{_total}</b><br><span style='font-size:10px;color:#64748b'>players</span>",
                x=0.5, y=0.5, xref="paper", yref="paper",
                showarrow=False, font=dict(color="#f1f5f9", size=20), align="center",
            )
            fig_donut.update_layout(**dark_layout(
                height=360, showlegend=True,
                legend=dict(
                    orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02,
                    font=dict(size=9, color=D_TEXT), bgcolor="rgba(0,0,0,0)",
                ),
                margin=dict(l=10, r=150, t=20, b=20),
                title=dict(text="Role Distribution", font=dict(size=12, color=D_TICK), x=0),
            ))
            st.plotly_chart(fig_donut, use_container_width=True)

        with col_heat:
            # Versatility matrix: each row = a primary role group, each column = role score
            # Diagonal-dominant → specialised. Off-diagonal hot → versatile
            _active_roles = [r for r in ALL_ROLES if (filtered[config.PRIMARY_ROLE_COL] == r).any()]
            _heat_z, _heat_text = [], []
            for _r in _active_roles:
                _sub  = filtered[filtered[config.PRIMARY_ROLE_COL] == _r]
                _vals = [
                    round(_sub[role_score_col(r2)].mean(), 1)
                    if role_score_col(r2) in _sub.columns else 0.0
                    for r2 in _active_roles
                ]
                _heat_z.append(_vals)
                _heat_text.append([f"{v:.0f}" for v in _vals])
            _abbrevs = [_ROLE_ABBREV.get(r, r) for r in _active_roles]
            fig_matrix = go.Figure(go.Heatmap(
                z=_heat_z, x=_abbrevs, y=_abbrevs,
                colorscale=[[0,"#0d1117"],[0.35,"#1e3a5f"],[0.7,"#0095FF"],[1.0,"#00d4aa"]],
                zmin=0, zmax=100,
                text=_heat_text, texttemplate="%{text}",
                textfont=dict(size=10, color="#f1f5f9"),
                hovertemplate="<b>%{y}</b> players avg <b>%{x}</b> score: %{z:.1f}<extra></extra>",
                showscale=False,
            ))
            fig_matrix.update_layout(**dark_layout(
                height=360,
                xaxis=dict(
                    title="Scored as →", tickfont=dict(size=9, color=D_TEXT), tickangle=-30,
                ),
                yaxis=dict(
                    title="Primary role ↓", tickfont=dict(size=9, color=D_TEXT), autorange="reversed",
                ),
                margin=dict(l=10, r=10, t=44, b=10),
                title=dict(
                    text="Role Versatility Matrix — bright diagonal = highly specialised",
                    font=dict(size=11, color=D_TICK), x=0,
                ),
            ))
            st.plotly_chart(fig_matrix, use_container_width=True)

        st.markdown("---")

        # ── Role DNA heatmap ────────────────────────────────────────────
        st.markdown('<p class="section-title">Role DNA — what makes each role tick?</p>', unsafe_allow_html=True)
        st.caption(
            "Average percentile rank of every metric used across all 9 roles, grouped by primary role. "
            "Bright cells show where each archetype genuinely excels — dark cells reveal where they don't."
        )

        # Collect every metric used by any role, deduplicated
        _all_dna_metrics = list(dict.fromkeys(
            m for weights in config.ROLE_WEIGHTS.values() for m in weights
        ))
        _dna_labels = [label(m) for m in _all_dna_metrics]
        _dna_z, _dna_y = [], []
        for _role in ALL_ROLES:
            _rp = filtered[filtered[config.PRIMARY_ROLE_COL] == _role]
            if len(_rp) == 0:
                continue
            _dna_y.append(_role)
            _dna_z.append([
                round(_rp[f"{m}{active_pct_suffix}"].mean(), 1)
                if f"{m}{active_pct_suffix}" in _rp.columns else 0.0
                for m in _all_dna_metrics
            ])

        fig_dna = go.Figure(go.Heatmap(
            z=_dna_z, x=_dna_labels, y=_dna_y,
            colorscale=[[0,"#0d1117"],[0.3,"#0c2a4a"],[0.6,"#0095FF"],[1.0,"#00d4aa"]],
            zmin=0, zmax=100,
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:.0f}th pct<extra></extra>",
            colorbar=dict(
                thickness=12, len=0.85,
                tickfont=dict(color=D_TICK, size=9),
                title=dict(text="Pct", font=dict(color=D_TICK, size=10), side="right"),
            ),
        ))
        fig_dna.update_layout(**dark_layout(
            height=max(300, len(_dna_y) * 36),
            xaxis=dict(tickfont=dict(size=9, color=D_TEXT), tickangle=-40),
            yaxis=dict(tickfont=dict(size=10, color=D_TEXT), autorange="reversed"),
            margin=dict(l=10, r=80, t=44, b=100),
            title=dict(
                text="Role DNA — avg metric percentile among players assigned to each role",
                font=dict(size=11, color=D_TICK), x=0,
            ),
        ))
        st.plotly_chart(fig_dna, use_container_width=True)

        st.markdown("---")

        # ── Role share by league (% stacked bar) ───────────────────────
        if has_league_col and filtered["league"].nunique() > 1:
            st.markdown('<p class="section-title">Role Share by League</p>', unsafe_allow_html=True)
            st.caption("What percentage of each league's midfielders fall into each role? Reveals each league's tactical identity.")

            _lr_rows = []
            for _lg in ALL_LEAGUES:
                _lg_df   = filtered[filtered["league"] == _lg]
                _lg_tot  = max(len(_lg_df), 1)
                for _role in ALL_ROLES:
                    _n_role = int((_lg_df[config.PRIMARY_ROLE_COL] == _role).sum())
                    _lr_rows.append({
                        "league_badge": league_badge(_lg),
                        "role": _role,
                        "pct": round(_n_role / _lg_tot * 100, 1),
                        "count": _n_role,
                    })
            _lr_df = pd.DataFrame(_lr_rows)

            fig_lr = go.Figure()
            for _role in ALL_ROLES:
                _rs = _lr_df[_lr_df["role"] == _role]
                fig_lr.add_trace(go.Bar(
                    name=_role,
                    x=_rs["league_badge"].tolist(),
                    y=_rs["pct"].tolist(),
                    marker_color=role_color(_role),
                    text=[f"{v:.0f}%" if v >= 5 else "" for v in _rs["pct"]],
                    textposition="inside",
                    textfont=dict(size=9),
                    hovertemplate=(
                        f"<b>{_role}</b><br>%{{x}}: %{{y:.1f}}% · %{{customdata}} players<extra></extra>"
                    ),
                    customdata=_rs["count"].tolist(),
                ))
            fig_lr.update_layout(**dark_layout(
                barmode="stack", height=340,
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=9, color=D_TEXT), bgcolor="rgba(0,0,0,0)",
                ),
                xaxis=dict(tickfont=dict(size=12, color=D_TEXT)),
                yaxis=dict(
                    title="% of league midfielders", ticksuffix="%",
                    gridcolor=D_GRID, color=D_TEXT, range=[0, 101],
                ),
                margin=dict(l=10, r=10, t=50, b=10),
                title=dict(
                    text="Which leagues over-index on each role?",
                    font=dict(size=11, color=D_TICK), x=0,
                ),
            ))
            st.plotly_chart(fig_lr, use_container_width=True)
            st.markdown("---")

        # ── Top players per role, grouped by zone ──────────────────────
        st.markdown('<p class="section-title">Top Players by Role</p>', unsafe_allow_html=True)

        for _zone in _ZONE_ORDER:
            _zr = [r for r in ALL_ROLES
                   if _PITCH_ZONES.get(r) == _zone
                   and has_roles
                   and (filtered[config.PRIMARY_ROLE_COL] == r).any()]
            if not _zr:
                continue
            _zc = _ZONE_COLORS[_zone]
            st.markdown(
                f'<div style="margin:16px 0 8px">'
                f'<span style="background:{_zc}22;color:{_zc};border:1px solid {_zc}44;'
                f'border-radius:6px;padding:2px 10px;font-size:0.72rem;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.8px">{_zone}</span>'
                f'<span style="color:#94a3b8;font-size:0.8rem;margin-left:8px">'
                f'{_ZONE_LABELS[_zone]}</span></div>',
                unsafe_allow_html=True,
            )
            _zcols = st.columns(len(_zr))
            for _ci, _role in enumerate(_zr):
                _rc      = role_color(_role)
                _sc_col  = role_score_col(_role)
                _rp_top  = (
                    filtered[filtered[config.PRIMARY_ROLE_COL] == _role]
                    .sort_values(_sc_col, ascending=False)
                    .head(8)
                )
                with _zcols[_ci]:
                    st.markdown(
                        f'<p style="margin:0 0 8px;font-size:0.85rem;font-weight:700;color:{_rc}">'
                        f'{_role}</p>',
                        unsafe_allow_html=True,
                    )
                    for _, _pr in _rp_top.iterrows():
                        _ps   = float(_pr.get(_sc_col, 0) or 0)
                        _flag = LEAGUE_FLAGS.get(_pr.get("league", ""), "") if has_league_col else ""
                        st.markdown(
                            f'<div style="margin-bottom:7px">'
                            f'<div style="display:flex;justify-content:space-between;'
                            f'align-items:baseline;margin-bottom:2px">'
                            f'<span style="font-size:0.78rem;color:#e2e8f0;white-space:nowrap;'
                            f'overflow:hidden;text-overflow:ellipsis;max-width:74%">'
                            f'{_flag} {_pr["player_name"]}</span>'
                            f'<span style="font-size:0.74rem;color:{_rc};font-weight:600">'
                            f'{_ps:.0f}</span></div>'
                            f'<div style="background:#1e293b;border-radius:3px;height:3px">'
                            f'<div style="background:{_rc};border-radius:3px;height:3px;'
                            f'width:{int(_ps)}%"></div></div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
            st.markdown("<div style='margin-bottom:4px'></div>", unsafe_allow_html=True)

    else:
        st.info(
            "Role scores are not available yet. Re-run the pipeline:\n\n"
            "```bash\n"
            "python -m src.features.chance_creation\n"
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

        # League and global ranks
        _global_all = df.sort_values(score_col, ascending=False).reset_index(drop=True)
        global_rank = _global_all[_global_all["player_name"] == selected_player].index[0] + 1 \
                      if selected_player in _global_all["player_name"].values else "—"
        global_total = len(_global_all)
        if has_league_col and "league" in row and pd.notna(row["league"]):
            _league_all = df[df["league"] == row["league"]].sort_values(score_col, ascending=False).reset_index(drop=True)
            league_rank = _league_all[_league_all["player_name"] == selected_player].index[0] + 1 \
                          if selected_player in _league_all["player_name"].values else "—"
            league_total = len(_league_all)
            player_league = row["league"]
        else:
            league_rank = None
            league_total = None
            player_league = None

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
                f'<span style="color:#64748b">·</span>'
                f'<span style="color:#64748b">Contract Until</span>'
                f'<span style="color:#f1f5f9;font-weight:600">{ct_str}</span>'
                f'<span style="color:#64748b">·</span>'
                f'<span style="background:{fc}22;color:{fc};border:1px solid {fc}55;'
                f'border-radius:4px;padding:1px 8px;font-size:0.76rem;font-weight:600">'
                f'{feasib}</span>'
                f'</p>'
            )
        else:
            tm_html = ""

        _league_badge_str = (
            f'{LEAGUE_FLAGS.get(player_league,"")} {LEAGUE_DISPLAY.get(player_league, player_league.replace("_"," "))}'
            if player_league else ""
        )
        _role_arch_str = "&nbsp;·&nbsp;<em>" + (prim_role or arch) + "</em>" if (prim_role or arch) else ""
        _league_str    = "&nbsp;·&nbsp;" + _league_badge_str if _league_badge_str else ""

        _league_rank_html = ""
        if league_rank and league_rank != "—":
            _league_rank_html = (
                f'<div style="text-align:center">'
                f'<div style="background:#1e3a5f;color:#93c5fd;border-radius:8px;'
                f'padding:6px 14px;font-size:1.1rem;font-weight:bold">'
                f'#{league_rank}<span style="font-size:0.75rem;color:#64748b"> / {league_total}</span>'
                f'</div>'
                f'<p style="margin:4px 0 0;color:#64748b;font-size:0.72rem">League Rank</p>'
                f'</div>'
            )
        _global_rank_html = (
            f'<div style="text-align:center">'
            f'<div style="background:#1a2535;color:#94a3b8;border-radius:8px;'
            f'padding:6px 14px;font-size:1.1rem;font-weight:bold">'
            f'#{global_rank}<span style="font-size:0.75rem;color:#64748b"> / {global_total}</span>'
            f'</div>'
            f'<p style="margin:4px 0 0;color:#64748b;font-size:0.72rem">Global Rank</p>'
            f'</div>'
        )

        st.markdown(
            f'<div style="background:#1e293b;border-radius:10px;padding:18px 24px;'
            f'border-left:5px solid {bar_col};margin-bottom:16px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">'
            f'<div>'
            f'<h2 style="margin:0;color:#f1f5f9">{selected_player}</h2>'
            f'<p style="margin:4px 0 0;color:#94a3b8;font-size:0.95rem">'
            f'{row["team_name"]} &nbsp;·&nbsp; {pos_str} &nbsp;·&nbsp; Age {age_str}'
            f'{_role_arch_str}{_league_str}'
            f'</p>'
            f'<p style="margin:6px 0 0;color:#64748b;font-size:0.82rem">'
            f'{mins_val:,} minutes played &nbsp;·&nbsp; {apps_val} appearances'
            f'</p>'
            f'{tm_html}'
            f'</div>'
            f'<div style="display:flex;gap:16px;align-items:center">'
            f'{_league_rank_html}'
            f'{_global_rank_html}'
            f'<div style="text-align:center">'
            f'<div style="background:{bar_col};color:white;border-radius:50%;'
            f'width:68px;height:68px;display:flex;align-items:center;'
            f'justify-content:center;font-size:1.5rem;font-weight:bold">'
            f'{score_val:.0f}'
            f'</div>'
            f'<p style="margin:4px 0 0;color:#64748b;font-size:0.75rem">Overall Score</p>'
            f'</div>'
            f'</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Build narrative & strength data (used in right column) ──────
        _narrative_intros = {
            "Creator":         "unlocks defences through dangerous deliveries into the box — whether centrally through key passes and through balls or from wide through crosses",
            "Ball Progressor": "drives the team forward through direct carrying and dribbling, turning possession into penetration",
            "Box Threat":      "constantly arrives in the penalty area, combining relentless box presence with a direct shooting threat",
            "Deep Builder":    "controls the tempo from deep with high-volume, accurate, forward-oriented passing",
        }
        _role_score_val = float(row.get(f"{config.ROLE_SCORE_COL_PREFIX}{prim_role}", 0) or 0) if prim_role else 0.0
        _surname = selected_player.split()[-1]

        _role_met_list = list(config.ROLE_WEIGHTS.get(prim_role, {}).keys()) if prim_role else []
        _role_mpcts = sorted(
            [(label(m), float(row.get(f"{m}{active_pct_suffix}", 0) or 0))
             for m in _role_met_list if f"{m}{active_pct_suffix}" in row.index],
            key=lambda x: x[1], reverse=True,
        )
        _narrative = ""
        if prim_role:
            _intro = _narrative_intros.get(prim_role, "contributes across the midfield")
            _narrative = f"Rated **{_role_score_val:.0f}/100** as a **{prim_role}**, {_surname} {_intro}."
            if len(_role_mpcts) >= 2:
                _narrative += (
                    f" Standout metrics: **{_role_mpcts[0][0]}** ({_role_mpcts[0][1]:.0f}th pct) "
                    f"and **{_role_mpcts[1][0]}** ({_role_mpcts[1][1]:.0f}th pct)."
                )
            elif _role_mpcts:
                _narrative += f" Standout metric: **{_role_mpcts[0][0]}** ({_role_mpcts[0][1]:.0f}th pct)."
            if _role_mpcts and _role_mpcts[-1][1] < 35:
                _narrative += f" Development area: **{_role_mpcts[-1][0]}** ({_role_mpcts[-1][1]:.0f}th pct)."
        _narr_html = re.sub(r'\*\*(.+?)\*\*', r'<b style="color:#f1f5f9">\1</b>', _narrative)

        _all_mpcts: list[tuple[str, float, str]] = []
        _seen_m: set[str] = set()
        for _m in list({m2 for w in config.ROLE_WEIGHTS.values() for m2 in w} | set(config.CHANCE_CREATION_METRICS)):
            _pc = f"{_m}{active_pct_suffix}"
            if _pc in row.index and pd.notna(row[_pc]) and _m not in _seen_m:
                _all_mpcts.append((label(_m), float(row[_pc]), _m))
                _seen_m.add(_m)
        _all_mpcts.sort(key=lambda x: x[1], reverse=True)
        _strengths = _all_mpcts[:3]
        _concerns  = _all_mpcts[-3:]

        # ── Two-column layout: Radar | Right panel ─────────────────────
        col_radar, col_right = st.columns([5, 4])

        with col_radar:
            if PCT_COLS:
                _pct_label = "Within league" if _league_mode else "All leagues"
                st.caption(f"Radar percentiles: {_pct_label}")
                fig_radar = create_radar_chart(
                    player_view_dict(row, active_pct_suffix),
                    metrics=CORE_METRICS, title="",
                )
                st.plotly_chart(fig_radar, use_container_width=True)

        with col_right:
            # ── Role scores — compact HTML bars ────────────────────────
            if has_roles and ROLE_SCORE_COLS:
                def _hex_to_rgba(hex_color: str, alpha: float) -> str:
                    h = hex_color.lstrip("#")
                    rv, gv, bv = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                    return f"rgba({rv},{gv},{bv},{alpha})"

                _role_bars_html = ""
                for _rc in ROLE_SCORE_COLS:
                    _rn  = _rc.replace(config.ROLE_SCORE_COL_PREFIX, "")
                    _rv  = float(row.get(_rc, 0) or 0)
                    _rc2 = role_color(_rn)
                    _is_prim = (_rn == prim_role)
                    _bar_c = _rc2 if _is_prim else _hex_to_rgba(_rc2, 0.35)
                    _label_c = "#f1f5f9" if _is_prim else "#64748b"
                    _star = ' <span style="color:#f59e0b;font-size:0.65rem">★ primary</span>' if _is_prim else ""
                    _role_bars_html += (
                        f'<div style="margin-bottom:10px">'
                        f'<div style="display:flex;justify-content:space-between;'
                        f'align-items:center;margin-bottom:4px">'
                        f'<span style="font-size:0.75rem;font-weight:{"700" if _is_prim else "400"};'
                        f'color:{_label_c}">{_rn}{_star}</span>'
                        f'<span style="font-size:0.78rem;font-weight:700;color:{_bar_c}">{_rv:.0f}</span>'
                        f'</div>'
                        f'<div style="background:#0f172a;border-radius:3px;height:6px">'
                        f'<div style="background:{_bar_c};border-radius:3px;height:6px;'
                        f'width:{_rv:.0f}%"></div>'
                        f'</div>'
                        f'</div>'
                    )

                # Peer rank
                _peer_rank_html = ""
                if prim_role:
                    _role_col = f"{config.ROLE_SCORE_COL_PREFIX}{prim_role}"
                    if _role_col in filtered.columns:
                        _sorted_peers = filtered.sort_values(_role_col, ascending=False).reset_index(drop=True)
                        _peer_match   = _sorted_peers[_sorted_peers["player_name"] == selected_player]
                        if len(_peer_match) > 0:
                            _peer_rank    = int(_peer_match.index[0]) + 1
                            _peer_total   = len(_sorted_peers)
                            _peer_top_pct = int((_peer_rank / _peer_total) * 100)
                            _peer_rank_html = (
                                f'<div style="margin-top:4px;padding:8px 0;border-top:1px solid #1e293b;'
                                f'font-size:0.72rem;color:#64748b">'
                                f'Ranked <b style="color:{bar_col}">#{_peer_rank}</b> of {_peer_total} '
                                f'{prim_role}s · top {_peer_top_pct}%'
                                f'</div>'
                            )

                st.markdown(
                    f'<div style="background:#1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px">'
                    f'<p style="margin:0 0 12px;font-size:0.72rem;font-weight:600;color:#64748b;'
                    f'text-transform:uppercase;letter-spacing:0.8px">Role Ratings</p>'
                    f'{_role_bars_html}'
                    f'{_peer_rank_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # ── Narrative + Strengths/Development ──────────────────────
            _str_pills = " ".join(
                f'<span class="strength-pill">↑ {lbl}</span>' for lbl, _, _ in _strengths
            )
            _con_pills = " ".join(
                f'<span class="concern-pill">↓ {lbl}</span>' for lbl, _, _ in _concerns
            )
            st.markdown(
                f'<div style="background:#1e293b;border-radius:10px;padding:16px 18px;'
                f'border-left:4px solid {bar_col}">'
                f'<p style="margin:0 0 8px;font-size:0.72rem;font-weight:600;color:#64748b;'
                f'text-transform:uppercase;letter-spacing:0.8px">Scouting Narrative</p>'
                f'<p style="margin:0 0 14px;color:#cbd5e1;font-size:0.88rem;line-height:1.6">'
                f'{_narr_html}</p>'
                f'<p style="margin:0 0 6px;font-size:0.68rem;font-weight:600;color:#64748b;'
                f'text-transform:uppercase;letter-spacing:0.7px">Strengths</p>'
                f'<div style="margin-bottom:12px">{_str_pills}</div>'
                f'<p style="margin:0 0 6px;font-size:0.68rem;font-weight:600;color:#64748b;'
                f'text-transform:uppercase;letter-spacing:0.7px">Development Areas</p>'
                f'<div>{_con_pills}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # ── Season totals — styled cards ──
        st.markdown('<p class="section-title">Season Totals</p>', unsafe_allow_html=True)

        # (col, label, p90_col)
        TOTAL_META = [
            ("key_passes",               "Key Passes",           "key_passes_p90"),
            ("assists",                  "Assists",              "assists_p90"),
            ("passes_into_penalty_area", "Passes into Box",      "passes_into_penalty_area_p90"),
            ("through_balls",            "Through Balls",        "through_balls_p90"),
            ("crosses",                  "Crosses",              "crosses_p90"),
            ("progressive_passes",       "Progressive Passes",   "progressive_passes_p90"),
            ("carries_into_final_third", "Carries F3",           "carries_into_final_third_p90"),
            ("successful_dribbles",      "Dribbles Won",         "successful_dribbles_p90"),
            ("shots",                    "Shots",                "shots_p90"),
            ("penalty_area_touches",     "Box Touches",          "penalty_area_touches_p90"),
            ("half_space_passes",        "Half-Space Passes",    "half_space_passes_p90"),
        ]

        totals = [
            (lbl, col, p90c)
            for col, lbl, p90c in TOTAL_META
            if col in row and pd.notna(row.get(col))
        ]

        if totals and apps_val > 0:
            cols_per_row = 6
            for chunk_start in range(0, len(totals), cols_per_row):
                chunk = totals[chunk_start: chunk_start + cols_per_row]
                card_cols = st.columns(len(chunk))
                for ci, (lbl, col, p90c) in enumerate(chunk):
                    total_val = int(row[col])
                    # Per-90 is more meaningful than per-appearance
                    p90_val   = row.get(p90c)
                    p90_str   = f"{float(p90_val):.2f}" if p90_val is not None and pd.notna(p90_val) else "—"
                    # Percentile for context bar — pipeline creates {p90c}_pct for role metrics.
                    # For metrics not in ROLE_WEIGHTS (e.g. half_space_passes_p90), compute on the fly.
                    pct_col = f"{p90c}_pct"
                    pct_val = row.get(pct_col)
                    if (pct_val is None or pd.isna(pct_val)) and p90c in df.columns:
                        _col_series = df[p90c].dropna()
                        if len(_col_series) > 0:
                            _player_p90 = row.get(p90c)
                            if _player_p90 is not None and pd.notna(_player_p90):
                                pct_val = (_col_series < float(_player_p90)).sum() / len(_col_series) * 100
                    pct = float(pct_val) if pct_val is not None and pd.notna(pct_val) else None
                    pct_str   = f"{pct:.0f}th" if pct is not None else ""
                    bar_pct_w = f"{pct:.0f}%" if pct is not None else "0%"
                    bar_pct_c = (
                        "#22c55e" if pct is not None and pct >= 75 else
                        "#f59e0b" if pct is not None and pct >= 50 else
                        "#ef4444" if pct is not None else "#334155"
                    )
                    with card_cols[ci]:
                        st.markdown(
                            f'<div style="background:#1e293b;border-radius:8px;padding:12px 10px;'
                            f'border-top:3px solid {bar_pct_c}">'

                            f'<div style="font-size:0.60rem;font-weight:600;color:#64748b;'
                            f'text-transform:uppercase;letter-spacing:0.7px;margin-bottom:4px">'
                            f'{lbl}</div>'

                            f'<div style="font-size:1.5rem;font-weight:800;color:#f1f5f9;'
                            f'line-height:1.1">{p90_str}</div>'
                            f'<div style="font-size:0.62rem;color:#64748b;margin-bottom:8px">per 90</div>'

                            f'<div style="background:#0f172a;border-radius:3px;height:4px;margin-bottom:6px">'
                            f'<div style="background:{bar_pct_c};border-radius:3px;height:4px;'
                            f'width:{bar_pct_w}"></div></div>'

                            f'<div style="display:flex;justify-content:space-between;align-items:center">'
                            f'<span style="font-size:0.62rem;color:#94a3b8">{total_val} total</span>'
                            f'<span style="font-size:0.65rem;font-weight:700;color:{bar_pct_c}">'
                            f'{pct_str}</span>'
                            f'</div>'

                            f'</div>',
                            unsafe_allow_html=True,
                        )
                st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

        # ── Similar Players ────────────────────────────────────────────
        st.markdown("---")
        st.markdown('<p class="section-title">Similar Players</p>', unsafe_allow_html=True)
        st.caption(
            "Ranked by profile similarity across all creation metrics. "
            "Method: equal-weight mean absolute difference in percentile ranks — "
            "same approach as FBRef. Age shown relative to selected player."
        )

        # FBRef-equivalent L1 similarity: all unique role metrics, equal weights.
        # Similarity = 100 − mean_absolute_difference(percentile ranks).
        # Expected realistic range: ~55–90%. Much more discriminating than cosine.
        # Always use global _pct — league percentiles are league-relative and cannot
        # be compared across leagues (90th pct in Ligue 1 ≠ 90th pct in PL).
        _SIM_SUFFIX = "_pct"
        _all_sim_metrics = list(dict.fromkeys(
            m for _rw in config.ROLE_WEIGHTS.values() for m in _rw
        ))
        _sim_metrics_sr = [m for m in _all_sim_metrics if f"{m}{_SIM_SUFFIX}" in df.columns]
        _n_sim          = len(_sim_metrics_sr) or 1

        def _safe_pct(r, m):
            v = r.get(f"{m}{_SIM_SUFFIX}")
            return float(v) if v is not None and pd.notna(v) else 0.0

        _ref_age_val = row.get("age")
        _ref_age     = int(_ref_age_val) if pd.notna(_ref_age_val) else None

        if _sim_metrics_sr and len(df) > 1:
            _ref_vec = [_safe_pct(row, m) for m in _sim_metrics_sr]

            _sim_scores: list[tuple] = []
            for _, _other_row in df.iterrows():
                if _other_row["player_name"] == selected_player:
                    continue
                _ov  = [_safe_pct(_other_row, m) for m in _sim_metrics_sr]
                _mad = sum(abs(a - b) for a, b in zip(_ref_vec, _ov)) / _n_sim
                _sim_scores.append((_other_row, max(0.0, 100.0 - _mad), _ov))

            _sim_scores.sort(key=lambda x: x[1], reverse=True)
            _top_similar = _sim_scores[:5]

            _sim_cols = st.columns(len(_top_similar))
            for _si, (_srow, _ssim, _sov) in enumerate(_top_similar):
                _sname     = _srow["player_name"]
                _steam     = _srow.get("team_name", "")
                _srole     = _srow.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
                _src       = role_color(_srole) if _srole else "#334155"
                _sscore    = float(_srow.get(score_col, 0) or 0)
                _sage_raw  = _srow.get("age")
                _sage      = int(_sage_raw) if pd.notna(_sage_raw) else None
                _sflag     = LEAGUE_FLAGS.get(_srow.get("league", ""), "") if has_league_col else ""
                _same_role = bool(_srole and _srole == prim_role)

                # Age delta — younger is better for recruitment
                if _ref_age and _sage:
                    _age_diff  = _sage - _ref_age
                    _age_col   = "#22c55e" if _age_diff < 0 else "#f59e0b" if _age_diff <= 2 else "#ef4444"
                    _age_str   = f"+{_age_diff}" if _age_diff > 0 else str(_age_diff)
                    _age_html  = (f'<span style="color:{_age_col};font-weight:600">'
                                  f'{_sage} yrs ({_age_str})</span>')
                else:
                    _age_html  = f'<span style="color:#64748b">{_sage or "—"} yrs</span>'

                # Same-role badge vs generic "match" label
                if _same_role:
                    _header_right = (
                        f'<span style="background:{_src}22;color:{_src};'
                        f'border:1px solid {_src}44;border-radius:20px;'
                        f'padding:1px 7px;font-size:0.62rem;font-weight:700">Same role</span>'
                    )
                else:
                    _header_right = '<span style="font-size:0.68rem;color:#94a3b8">match</span>'

                # Per-metric diffs: sorted to find top-2 edges and top-2 gaps
                _all_diffs = sorted(
                    [(m, ov - rv) for m, rv, ov in zip(_sim_metrics_sr, _ref_vec, _sov)],
                    key=lambda x: x[1], reverse=True,
                )
                _edges = [(m, d) for m, d in _all_diffs if d >= 6][:2]
                _gaps  = [(m, d) for m, d in reversed(_all_diffs) if d <= -6][:2]

                _delta_rows = ""
                for _dm, _diff in _edges:
                    _delta_rows += (
                        f'<div style="display:flex;justify-content:space-between;'
                        f'align-items:center;padding:2px 0">'
                        f'<span style="font-size:0.65rem;color:#64748b;max-width:76%;'
                        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                        f'{label(_dm)}</span>'
                        f'<span style="font-size:0.67rem;font-weight:700;color:#22c55e">'
                        f'+{_diff:.0f}</span></div>'
                    )
                for _dm, _diff in _gaps:
                    _delta_rows += (
                        f'<div style="display:flex;justify-content:space-between;'
                        f'align-items:center;padding:2px 0">'
                        f'<span style="font-size:0.65rem;color:#64748b;max-width:76%;'
                        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                        f'{label(_dm)}</span>'
                        f'<span style="font-size:0.67rem;font-weight:700;color:#ef4444">'
                        f'{_diff:.0f}</span></div>'
                    )
                if not _delta_rows:
                    _delta_rows = '<div style="font-size:0.65rem;color:#94a3b8">Nearly identical profiles</div>'

                # Colour scale for realistic L1 range (~55–90%)
                _sim_color = (
                    "#22c55e" if _ssim >= 80 else
                    "#f59e0b" if _ssim >= 70 else
                    "#94a3b8"
                )

                with _sim_cols[_si]:
                    st.markdown(
                        f'<div style="background:#1e293b;border-radius:10px;padding:14px 12px;'
                        f'border-top:3px solid {_sim_color}">'

                        f'<div style="display:flex;align-items:center;'
                        f'justify-content:space-between;margin-bottom:6px">'
                        f'<span style="font-size:1.4rem;font-weight:800;color:{_sim_color}">'
                        f'{_ssim:.0f}%</span>'
                        f'{_header_right}'
                        f'</div>'

                        f'<div style="background:#0f172a;border-radius:4px;height:4px;margin-bottom:10px">'
                        f'<div style="background:{_sim_color};border-radius:4px;height:4px;'
                        f'width:{min(_ssim,100):.0f}%"></div>'
                        f'</div>'

                        f'<div style="font-weight:700;color:#f1f5f9;font-size:0.88rem;'
                        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:2px">'
                        f'{_sname}</div>'

                        f'<div style="font-size:0.70rem;color:#64748b;margin-bottom:8px">'
                        f'{_sflag} {_steam} · {_age_html}</div>'

                        f'<div style="margin-bottom:10px">'
                        f'<span style="background:{_src}22;color:{_src};border:1px solid {_src}44;'
                        f'border-radius:20px;padding:2px 8px;font-size:0.68rem;font-weight:600">'
                        f'{_srole}</span>'
                        f'<span style="float:right;font-size:0.70rem;color:#94a3b8;'
                        f'font-weight:600">{_sscore:.0f}</span>'
                        f'</div>'

                        f'<div style="border-top:1px solid #334155;padding-top:8px">'
                        f'<div style="font-size:0.60rem;color:#94a3b8;margin-bottom:4px;'
                        f'text-transform:uppercase;letter-spacing:0.6px">'
                        f'vs {selected_player.split()[-1]}</div>'
                        f'{_delta_rows}'
                        f'</div>'

                        f'</div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.caption("Not enough players in the current filter to compute similarity. "
                       "Broaden the sidebar filters to include more players.")

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
                RESULT_COLORS = {"W": "#22c55e", "D": "#94a3b8", "L": "#ef4444", "?": "#64748b"}
                DNP_COLOR = "#253347"

                _played = match_log[match_log["status"] != "DNP"].copy().reset_index(drop=True)
                _dnp_count   = (match_log["status"] == "DNP").sum()
                _w = (match_log["result"] == "W").sum()
                _d = (match_log["result"] == "D").sum()
                _l = (match_log["result"] == "L").sum()
                _avg_mins    = _played["minutes_played"].mean() if len(_played) else 0
                _starts      = (_played["status"] == "Started").sum() if "status" in _played.columns else len(_played)
                _subs        = len(_played) - _starts
                _total_goals = int(_played["goals"].sum()) if "goals" in _played.columns else 0
                _total_assts = int(_played["assists"].sum()) if "assists" in _played.columns else 0
                _total_kp    = int(_played["key_passes"].sum()) if "key_passes" in _played.columns else 0

                # ── Contributions badges ───────────────────────────────
                _contrib_badges = (
                    f'<span style="background:#22c55e22;color:#22c55e;border:1px solid #22c55e44;'
                    f'border-radius:5px;padding:1px 7px;font-size:0.72rem;font-weight:700;margin-right:4px">'
                    f'⚽ {_total_goals}</span>'
                    f'<span style="background:#0095ff22;color:#60a5fa;border:1px solid #0095ff44;'
                    f'border-radius:5px;padding:1px 7px;font-size:0.72rem;font-weight:700;margin-right:4px">'
                    f'A {_total_assts}</span>'
                    f'<span style="background:#f59e0b22;color:#fbbf24;border:1px solid #f59e0b44;'
                    f'border-radius:5px;padding:1px 7px;font-size:0.72rem;font-weight:700">'
                    f'KP {_total_kp}</span>'
                )

                # ── Last-5 form strip + narrative ──────────────────────
                _last5 = match_log[match_log["status"] != "DNP"].tail(5)
                _form_metric_candidates = {
                    "Creator":         "key_passes",
                    "Ball Progressor": "successful_dribbles",
                    "Box Threat":      "shots",
                    "Deep Builder":    "progressive_passes",
                }
                _form_col = _form_metric_candidates.get(prim_role, "key_passes")
                _form_col = _form_col if _form_col in _played.columns else (
                    "key_passes" if "key_passes" in _played.columns else None
                )
                _form_label = METRIC_LABELS.get(f"{_form_col}_p90", (_form_col or "").replace("_", " ").title())

                # Last-5 form squares — compact tiles with score line
                _l5_html = ""
                for _, _fr in _last5.iterrows():
                    _fc   = RESULT_COLORS.get(_fr["result"], "#334155")
                    _opp  = str(_fr["opponent"])[:7]
                    _scr  = str(_fr.get("score", ""))
                    _l5_html += (
                        f'<div style="text-align:center;flex:1">'
                        f'<div style="background:{_fc};border-radius:5px;height:28px;'
                        f'display:flex;align-items:center;justify-content:center;'
                        f'font-size:0.78rem;font-weight:800;color:#0f172a">{_fr["result"]}</div>'
                        f'<div style="font-size:0.58rem;color:#64748b;margin-top:3px;'
                        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{_opp}</div>'
                        f'<div style="font-size:0.56rem;color:#94a3b8">{_scr}</div>'
                        f'</div>'
                    )

                # Auto-narrative
                _l5_wins = (_last5["result"] == "W").sum()
                _form_phrase = (
                    "in excellent recent form" if _l5_wins >= 4 else
                    "in good recent form"      if _l5_wins >= 3 else
                    "in mixed form"            if _l5_wins >= 2 else
                    "in poor recent form"
                )
                _form_color = (
                    "#22c55e" if _l5_wins >= 4 else
                    "#22c55e" if _l5_wins >= 3 else
                    "#f59e0b" if _l5_wins >= 2 else
                    "#ef4444"
                )
                _starter_phrase = (
                    f"a regular starter — {_starts} starts"
                    if _starts >= len(_played) * 0.7
                    else f"mainly from the bench — {_starts} starts, {_subs} subs"
                )

                # Best single game by creation metric
                _narr_extra = ""
                if _form_col and len(_played) > 0 and _form_col in _played.columns:
                    _best_idx   = _played[_form_col].idxmax()
                    _best_row   = _played.loc[_best_idx]
                    _best_val   = int(_best_row[_form_col])
                    _best_opp   = _best_row.get("opponent", "")
                    _season_avg = _played[_form_col].mean()
                    if _best_val > 0:
                        _narr_extra = (
                            f" Peak game: <b style='color:#f1f5f9'>{_best_val} {_form_label}</b>"
                            f" vs {_best_opp}."
                        )
                    _consistent_pct = (_played[_form_col] >= _season_avg).mean() * 100
                    if _consistent_pct >= 60:
                        _narr_extra += (
                            f" Hits season avg in <b style='color:#f1f5f9'>"
                            f"{_consistent_pct:.0f}%</b> of games."
                        )

                _narrative_log = (
                    f'<b style="color:#f1f5f9">{_surname}</b> is {_starter_phrase}, '
                    f'averaging <b style="color:#f1f5f9">{_avg_mins:.0f} min</b> per appearance. '
                    f'Currently <b style="color:{_form_color}">{_form_phrase}</b> '
                    f'<span style="color:#64748b">({_l5_wins}W from last 5)</span>.'
                    f'{_narr_extra}'
                )

                _l5_label = "Last 5" if len(_last5) == 5 else f"Last {len(_last5)}"

                _record_v = (
                    f'<span style="color:#22c55e;font-weight:700">{_w}W</span>'
                    f'<span style="color:#94a3b8"> · </span>'
                    f'<span style="color:#94a3b8;font-weight:700">{_d}D</span>'
                    f'<span style="color:#94a3b8"> · </span>'
                    f'<span style="color:#ef4444;font-weight:700">{_l}L</span>'
                )

                def _stat_row(label, value_html):
                    return (
                        f'<div style="display:flex;justify-content:space-between;'
                        f'align-items:center;padding:9px 0;border-bottom:1px solid #0f172a">'
                        f'<span style="font-size:0.78rem;color:#64748b">{label}</span>'
                        f'<span style="font-size:0.92rem;font-weight:700;color:#f1f5f9">{value_html}</span>'
                        f'</div>'
                    )

                _stats_rows = (
                    _stat_row("Appearances", f"{len(_played)}")
                    + _stat_row("Usage", f"{_starts} starts · {_subs} sub")
                    + _stat_row("Avg Minutes", f"{_avg_mins:.0f}′")
                    + _stat_row("Record", _record_v)
                    + _stat_row("Contributions", _contrib_badges)
                    + (_stat_row("DNP", f'<span style="color:#94a3b8">{_dnp_count}</span>') if _dnp_count else "")
                )

                st.markdown(
                    f'<div style="display:flex;gap:12px;align-items:stretch;margin-bottom:14px">'

                    # Left: stats
                    f'<div style="flex:2;background:#1e293b;border-radius:12px;'
                    f'border:1px solid #334155;padding:14px 18px">'
                    f'<p style="margin:0 0 4px;font-size:0.60rem;font-weight:600;color:#94a3b8;'
                    f'text-transform:uppercase;letter-spacing:0.8px">Season Stats</p>'
                    f'{_stats_rows}'
                    f'</div>'

                    # Right: last 5 + narrative
                    f'<div style="flex:3;background:#1e293b;border-radius:12px;'
                    f'border:1px solid #334155;overflow:hidden;display:flex;flex-direction:column">'

                    f'<div style="padding:14px 18px;border-bottom:1px solid #334155">'
                    f'<p style="margin:0 0 10px;font-size:0.60rem;font-weight:600;color:#94a3b8;'
                    f'text-transform:uppercase;letter-spacing:0.8px">{_l5_label} Results</p>'
                    f'<div style="display:flex;gap:6px">{_l5_html}</div>'
                    f'</div>'

                    f'<div style="padding:14px 18px;border-left:4px solid {bar_col};flex:1">'
                    f'<p style="margin:0 0 6px;font-size:0.60rem;font-weight:600;color:#94a3b8;'
                    f'text-transform:uppercase;letter-spacing:0.8px">Season Narrative</p>'
                    f'<p style="margin:0;font-size:0.86rem;color:#cbd5e1;line-height:1.65">'
                    f'{_narrative_log}</p>'
                    f'</div>'

                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # ── Timeline bar chart + creation overlay ──────────────
                match_log["bar_color"] = match_log.apply(
                    lambda r: DNP_COLOR if r["status"] == "DNP"
                              else RESULT_COLORS.get(r["result"], "#334155"),
                    axis=1,
                )
                # Short x-labels: "H Inter" / "A Napoli"
                match_log["x_label"] = match_log.apply(
                    lambda r: f"{r['venue']} {str(r['opponent'])[:10]}", axis=1
                )
                # Make labels unique when same opponent appears twice
                _seen_labels: dict[str, int] = {}
                _unique_labels = []
                for _xl in match_log["x_label"]:
                    _seen_labels[_xl] = _seen_labels.get(_xl, 0) + 1
                    _unique_labels.append(_xl if _seen_labels[_xl] == 1 else f"{_xl} ({_seen_labels[_xl]})")
                match_log["x_label"] = _unique_labels

                match_log["hover_text"] = match_log.apply(
                    lambda r: (
                        f"<b>{r['opponent']}</b> ({r['venue']})<br>"
                        f"{r['date'].strftime('%d %b')} · {r['score']} · {r['result']}<br>"
                        f"{r['status']} · {r['minutes_played']}'"
                        + (
                            f"<br>Goals: {int(r.get('goals',0))}  Assists: {int(r.get('assists',0))}"
                            f"  Key passes: {int(r.get('key_passes',0))}"
                            if r["status"] != "DNP" else ""
                        )
                    ),
                    axis=1,
                )

                # Bar label: emoji icons for goals and assists
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

                # ── Chart 1: Minutes timeline ──────────────────────────
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
                for _rl, _rc in [("Win","#22c55e"),("Draw","#94a3b8"),("Loss","#ef4444"),("DNP",DNP_COLOR)]:
                    fig_log.add_trace(go.Bar(
                        x=[None], y=[None], marker_color=_rc,
                        marker_line_color="#334155", marker_line_width=1,
                        name=_rl, showlegend=True,
                    ))
                fig_log.add_hline(y=90, line_dash="dot",
                                  line_color="rgba(255,255,255,0.12)", line_width=1)
                fig_log.update_layout(**dark_layout(
                    height=240,
                    barmode="overlay",
                    xaxis=dict(
                        tickangle=-35, tickfont=dict(size=9, color=D_TICK),
                        showgrid=False, categoryorder="array",
                        categoryarray=match_log["x_label"].tolist(),
                    ),
                    yaxis=dict(title="Minutes", range=[0, 105], gridcolor=D_GRID, color=D_TICK, dtick=30),
                    legend=dict(
                        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                        font=dict(size=10, color=D_TEXT), bgcolor="rgba(0,0,0,0)",
                    ),
                    margin=dict(l=10, r=10, t=30, b=70),
                ))
                st.plotly_chart(fig_log, use_container_width=True)

                # ── Chart 2: Per-match bars + 3-game avg lines ─────────
                # Only columns present in match_log (built by build_match_log):
                # goals, assists, key_passes, through_balls, successful_dribbles,
                # crosses, progressive_passes, shots, tackles, interceptions
                _form_col2_candidates = {
                    "Creator":         "assists",
                    "Ball Progressor": "progressive_passes",
                    "Box Threat":      "key_passes",
                    "Deep Builder":    "key_passes",
                }
                _form_col2 = _form_col2_candidates.get(prim_role, "assists")
                _form_col2 = (
                    _form_col2
                    if (_form_col2 and _form_col2 in _played.columns and _form_col2 != _form_col)
                    else None
                )
                _form_label2 = METRIC_LABELS.get(
                    f"{_form_col2}_p90", (_form_col2 or "").replace("_", " ").title()
                ) if _form_col2 else None

                if _form_col and len(_played) >= 3:
                    # Use only played matches for the metric charts
                    _played_log = match_log[match_log["status"] != "DNP"].copy()
                    _x = _played_log["x_label"].tolist()

                    def _metric_chart(col, lbl, color):
                        _vals  = _played_log[col]
                        _roll  = _vals.rolling(3, min_periods=1).mean()
                        _fig   = go.Figure()
                        _fig.add_trace(go.Bar(
                            x=_x, y=_vals, name=lbl,
                            marker_color=color, opacity=0.45, marker_line_width=0,
                            hovertemplate="%{x}<br>" + lbl + ": %{y}<extra></extra>",
                        ))
                        _fig.add_trace(go.Scatter(
                            x=_x, y=_roll, name="3-game avg",
                            mode="lines+markers",
                            line=dict(color=color, width=2),
                            marker=dict(size=4, color=color),
                            hovertemplate="%{x}<br>3-game avg: %{y:.1f}<extra></extra>",
                            connectgaps=False,
                        ))
                        _fig.update_layout(**dark_layout(
                            height=200,
                            margin=dict(l=10, r=10, t=34, b=70),
                            xaxis=dict(
                                tickangle=-35, tickfont=dict(size=9, color=D_TICK),
                                showgrid=False, categoryorder="array", categoryarray=_x,
                            ),
                            yaxis=dict(gridcolor=D_GRID, color=D_TICK, rangemode="tozero", dtick=1),
                            legend=dict(
                                orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                                font=dict(size=10, color=D_TEXT), bgcolor="rgba(0,0,0,0)",
                            ),
                            title=dict(text=lbl, font=dict(size=11, color=D_TICK), x=0),
                        ))
                        return _fig

                    col_f1, col_f2 = st.columns(2)
                    with col_f1:
                        st.plotly_chart(
                            _metric_chart(_form_col, _form_label, bar_col),
                            use_container_width=True,
                        )
                    with col_f2:
                        if _form_col2:
                            st.plotly_chart(
                                _metric_chart(_form_col2, _form_label2, "#f59e0b"),
                                use_container_width=True,
                            )

                # ── Per-match stats table (creation-focused) ───────────
                tbl_cols = ["date", "venue", "opponent", "score", "result", "status",
                            "minutes_played", "goals", "assists", "key_passes",
                            "through_balls", "successful_dribbles", "crosses",
                            "progressive_passes", "shots"]
                avail_tbl = [c for c in tbl_cols if c in match_log.columns]
                tbl_log = match_log[avail_tbl].copy()
                tbl_log["date"] = tbl_log["date"].dt.strftime("%d %b")

                col_rename = {
                    "date": "Date", "venue": "H/A", "opponent": "Opponent",
                    "score": "Score", "result": "Result", "status": "Status",
                    "minutes_played": "Mins", "goals": "G", "assists": "A",
                    "key_passes": "KP", "through_balls": "TB",
                    "successful_dribbles": "Drb", "crosses": "Crs",
                    "progressive_passes": "PrgP", "shots": "Sh",
                }
                tbl_log.columns = [col_rename.get(c, c) for c in avail_tbl]

                st.dataframe(
                    tbl_log,
                    use_container_width=True,
                    hide_index=True,
                    height=min(35 * len(tbl_log) + 38, 480),
                    column_config={
                        "Mins": st.column_config.ProgressColumn(
                            "Mins", min_value=0, max_value=95, format="%d'"
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

    # ── Selector ──────────────────────────────────────────────────────
    st.markdown('<p class="section-title">Scouting Dossier</p>', unsafe_allow_html=True)
    st.markdown(
        "Side-by-side tactical breakdown — role fit, key battlegrounds, and where each player "
        "gives you something the other can't."
    )

    # Pool from full df so sidebar filters don't restrict who can be compared
    _cmp_list = df.sort_values(score_col, ascending=False)["player_name"].tolist()
    selected_players = st.multiselect(
        "Select players",
        options=_cmp_list,
        max_selections=4,
        placeholder="Choose 2–4 players...",
        label_visibility="collapsed",
    )

    if len(selected_players) < 2:
        st.markdown(
            '<div style="background:#1e293b;border-radius:10px;padding:40px;text-align:center;'
            'border:1px dashed #334155;margin-top:24px">'
            '<p style="margin:0;color:#64748b;font-size:0.95rem">'
            'Select 2–4 players from the dropdown above to begin the comparison.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        # Always pull from full df regardless of sidebar filters
        compare_df = df[df["player_name"].isin(selected_players)].copy()
        # Preserve selection order
        _order_idx = {p: i for i, p in enumerate(selected_players)}
        compare_df = compare_df.sort_values("player_name", key=lambda s: s.map(_order_idx))

        _cmp_colors = {
            p: PLAYER_COLORS[i % len(PLAYER_COLORS)][1]
            for i, p in enumerate(selected_players)
        }

        # ── Player header cards ────────────────────────────────────────
        st.markdown("<div style='margin:16px 0 4px'></div>", unsafe_allow_html=True)
        _hdr_cols = st.columns(len(selected_players))
        for _ci, _pn in enumerate(selected_players):
            _pr      = compare_df[compare_df["player_name"] == _pn].iloc[0]
            _pc      = _cmp_colors[_pn]
            _pr_role = _pr.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
            _rc      = role_color(_pr_role) if _pr_role else _pc
            _pr_sc   = float(_pr.get(score_col, 0) or 0)
            _pr_age  = int(_pr["age"]) if "age" in _pr and pd.notna(_pr["age"]) else "—"
            _pr_mins = int(_pr.get("minutes_played", 0) or 0)
            _pr_flag = LEAGUE_FLAGS.get(_pr.get("league", ""), "") if has_league_col else ""
            _pr_rank = int((df[score_col] > _pr_sc).sum()) + 1
            with _hdr_cols[_ci]:
                st.markdown(
                    f'<div style="background:#1e293b;border-radius:10px;padding:18px;'
                    f'border-top:4px solid {_pc};text-align:center">'
                    f'<div style="width:52px;height:52px;border-radius:50%;background:{_pc};'
                    f'display:flex;align-items:center;justify-content:center;'
                    f'font-size:1.3rem;font-weight:700;color:#fff;margin:0 auto 10px">'
                    f'{_pr_sc:.0f}</div>'
                    f'<div style="font-weight:700;color:#f1f5f9;font-size:0.92rem;'
                    f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{_pn}</div>'
                    f'<div style="font-size:0.78rem;color:#64748b;margin-top:3px">'
                    f'{_pr_flag} {_pr["team_name"]} · Age {_pr_age}</div>'
                    f'<div style="margin-top:10px">'
                    f'<span style="background:{_rc}22;color:{_rc};border:1px solid {_rc}44;'
                    f'border-radius:20px;padding:3px 10px;font-size:0.74rem;font-weight:600">'
                    f'{_pr_role}</span></div>'
                    f'<div style="font-size:0.72rem;color:#94a3b8;margin-top:8px">'
                    f'{_pr_mins:,} mins · <span style="color:#64748b">#{_pr_rank} overall</span></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")

        # ── Similarity helper (reused for 2-player card and pairwise matrix) ──
        _sim_metrics_cmp = list(dict.fromkeys(
            list(config.CHANCE_CREATION_METRICS) +
            [m for w in config.ROLE_WEIGHTS.values() for m in w]
        ))
        _sim_metrics_cmp = [m for m in _sim_metrics_cmp if f"{m}_pct" in compare_df.columns]

        def _get_vec(player_name):
            return [
                float(v) if (v := compare_df.loc[compare_df["player_name"] == player_name, f"{m}_pct"].values[0] if len(compare_df.loc[compare_df["player_name"] == player_name]) else None) is not None and pd.notna(v) else 0.0
                for m in _sim_metrics_cmp
            ]

        def _pairwise_sim(p1, p2):
            v1, v2 = _get_vec(p1), _get_vec(p2)
            n = len(v1) or 1
            return max(0.0, 100.0 - sum(abs(a - b) for a, b in zip(v1, v2)) / n)

        # ── Scout Brief ────────────────────────────────────────────────
        if len(selected_players) == 2:
            _sb_p1, _sb_p2 = selected_players
            _sb_r1 = compare_df[compare_df["player_name"] == _sb_p1].iloc[0].get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
            _sb_r2 = compare_df[compare_df["player_name"] == _sb_p2].iloc[0].get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
            _sb_sim = _pairwise_sim(_sb_p1, _sb_p2)
            if _sb_r1 == _sb_r2 and _sb_r1:
                _sb_role_line = (
                    f'Both profile as <b style="color:{role_color(_sb_r1)}">{_sb_r1}s</b> — '
                    f"this comparison reveals how they execute the same tactical mandate through different skill-sets."
                )
            elif _sb_r1 and _sb_r2:
                _sb_role_line = (
                    f'<b style="color:{_cmp_colors[_sb_p1]}">{_sb_p1.split()[-1]}</b> operates as a '
                    f'<b style="color:{role_color(_sb_r1)}">{_sb_r1}</b> while '
                    f'<b style="color:{_cmp_colors[_sb_p2]}">{_sb_p2.split()[-1]}</b> is a '
                    f'<b style="color:{role_color(_sb_r2)}">{_sb_r2}</b> — two different routes to progressing the team.'
                )
            else:
                _sb_role_line = "Two profiles matched head-to-head."
            _sb_sim_note = (
                "Their metrics sit remarkably close — nearly a drop-in tactical swap." if _sb_sim >= 80 else
                "Strong stylistic overlap, though clear divergence on a handful of key metrics." if _sb_sim >= 70 else
                "Partial overlap — useful in some systems, but these are clearly different players." if _sb_sim >= 55 else
                "Contrasting archetypes that would complement rather than replace each other."
            )
            st.markdown(
                f'<div style="background:#1e293b;border-radius:10px;padding:18px 22px;'
                f'border-left:4px solid #334155;margin-bottom:4px">'
                f'<p style="margin:0 0 4px;font-size:0.68rem;font-weight:600;color:#94a3b8;'
                f'text-transform:uppercase;letter-spacing:0.8px">Scout Brief</p>'
                f'<p style="margin:0;font-size:0.92rem;color:#cbd5e1;line-height:1.8">'
                f'{_sb_role_line} {_sb_sim_note}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            _sb_roles_ranked = sorted(
                selected_players,
                key=lambda p: float(compare_df[compare_df["player_name"] == p].iloc[0].get(score_col, 0) or 0),
                reverse=True,
            )
            _sb_ranked_html = " → ".join(
                f'<b style="color:{_cmp_colors[p]}">{p.split()[-1]}</b>'
                + (f' <span style="color:{role_color(compare_df[compare_df["player_name"]==p].iloc[0].get(config.PRIMARY_ROLE_COL,""))};font-size:0.76rem">({compare_df[compare_df["player_name"]==p].iloc[0].get(config.PRIMARY_ROLE_COL,"—")})</span>' if has_roles else "")
                for p in _sb_roles_ranked
            )
            st.markdown(
                f'<div style="background:#1e293b;border-radius:10px;padding:16px 22px;'
                f'border-left:4px solid #334155;margin-bottom:4px">'
                f'<p style="margin:0 0 4px;font-size:0.68rem;font-weight:600;color:#94a3b8;'
                f'text-transform:uppercase;letter-spacing:0.8px">Scout Brief — ranked by overall score</p>'
                f'<p style="margin:0;font-size:0.88rem;color:#cbd5e1;line-height:1.8">{_sb_ranked_html}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # ── Tactical DNA — 2-player card / pairwise matrix ────────────
        st.markdown('<p class="section-title">Tactical DNA</p>', unsafe_allow_html=True)

        if len(selected_players) == 2:
            _p1, _p2 = selected_players
            _v1 = _get_vec(_p1)
            _v2 = _get_vec(_p2)
            _sim = _pairwise_sim(_p1, _p2)
            _sim_label = (
                "very similar — nearly interchangeable tactically" if _sim >= 80 else
                "similar — strong stylistic overlap"               if _sim >= 70 else
                "partial overlap — clear stylistic differences"    if _sim >= 55 else
                "contrasting archetypes"
            )
            _gaps = [(_sim_metrics_cmp[i], _v1[i] - _v2[i]) for i in range(len(_v1))]
            _p1_edge = max(_gaps, key=lambda x: x[1])
            _p2_edge = min(_gaps, key=lambda x: x[1])
            _c1, _c2 = _cmp_colors[_p1], _cmp_colors[_p2]
            _sim_color = "#22c55e" if _sim >= 80 else "#f59e0b" if _sim >= 70 else "#94a3b8"
            _r1_dna = compare_df[compare_df["player_name"] == _p1].iloc[0].get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
            _r2_dna = compare_df[compare_df["player_name"] == _p2].iloc[0].get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
            _sim_implication = (
                "Signing either covers the same tactical need." if _sim >= 80 else
                "Both fit a similar role, but different ceiling metrics may tip the decision." if _sim >= 70 else
                "They serve different functions — this is a profile choice, not a like-for-like swap." if _sim >= 55 else
                "Define the tactical need before choosing — these are fundamentally different players."
            )
            if _r1_dna == _r2_dna and _r1_dna:
                _dna_role_ctx = f'Both are <b style="color:{role_color(_r1_dna)}">{_r1_dna}s</b> — a true within-archetype contest.'
            elif _r1_dna and _r2_dna:
                _dna_role_ctx = (
                    f'The divergence reflects their different mandates: '
                    f'<b style="color:{role_color(_r1_dna)}">{_r1_dna}</b> vs '
                    f'<b style="color:{role_color(_r2_dna)}">{_r2_dna}</b>.'
                )
            else:
                _dna_role_ctx = ""
            st.markdown(
                f'<div style="background:#1e293b;border-radius:10px;padding:20px 24px;'
                f'border-left:4px solid {_sim_color}">'
                f'<div style="display:flex;align-items:center;gap:18px;margin-bottom:12px">'
                f'<span style="font-size:2.2rem;font-weight:800;color:{_sim_color}">{_sim:.0f}%</span>'
                f'<span style="color:#94a3b8;font-size:0.88rem;line-height:1.4">{_sim_label}</span>'
                f'</div>'
                f'<div style="background:#0f172a;border-radius:4px;height:6px;margin-bottom:14px">'
                f'<div style="background:linear-gradient(90deg,{_c1},{_c2});'
                f'border-radius:4px;height:6px;width:{min(_sim,100):.0f}%"></div></div>'
                f'<p style="margin:0;font-size:0.86rem;color:#cbd5e1;line-height:1.8">'
                f'<b style="color:{_c1}">{_p1.split()[-1]}</b> leads on '
                f'<b style="color:#f1f5f9">{label(_p1_edge[0])}</b> (+{_p1_edge[1]:.0f} pct pts). '
                f'<b style="color:{_c2}">{_p2.split()[-1]}</b> leads on '
                f'<b style="color:#f1f5f9">{label(_p2_edge[0])}</b> (+{abs(_p2_edge[1]):.0f} pct pts). '
                f'{_dna_role_ctx}'
                f'<br><span style="color:#64748b;font-style:italic">{_sim_implication}</span></p>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            # Pairwise matrix for 3-4 players
            _pairs_all = [
                (a, b, _pairwise_sim(a, b))
                for i, a in enumerate(selected_players)
                for b in selected_players[i + 1:]
            ]
            _most_sim_pair  = max(_pairs_all, key=lambda x: x[2])
            _least_sim_pair = min(_pairs_all, key=lambda x: x[2])
            _matrix_html = (
                f'<table style="width:100%;border-collapse:collapse;font-size:0.82rem">'
                f'<tr><th style="padding:8px;color:#94a3b8;font-weight:400"></th>'
            )
            for _pn in selected_players:
                _pc = _cmp_colors[_pn]
                _matrix_html += (
                    f'<th style="padding:8px;text-align:center;color:{_pc};font-weight:700">'
                    f'{_pn.split()[-1]}</th>'
                )
            _matrix_html += "</tr>"
            for _pa in selected_players:
                _ca = _cmp_colors[_pa]
                _matrix_html += f'<tr><td style="padding:8px;color:{_ca};font-weight:700">{_pa.split()[-1]}</td>'
                for _pb in selected_players:
                    if _pa == _pb:
                        _matrix_html += '<td style="padding:8px;text-align:center;color:#64748b">—</td>'
                    else:
                        _s = _pairwise_sim(_pa, _pb)
                        _sc = "#22c55e" if _s >= 80 else "#f59e0b" if _s >= 70 else "#94a3b8"
                        _matrix_html += (
                            f'<td style="padding:8px;text-align:center;'
                            f'font-weight:700;color:{_sc}">{_s:.0f}%</td>'
                        )
                _matrix_html += "</tr>"
            _matrix_html += "</table>"
            _c_ms1 = _cmp_colors[_most_sim_pair[0]]
            _c_ms2 = _cmp_colors[_most_sim_pair[1]]
            _c_ls1 = _cmp_colors[_least_sim_pair[0]]
            _c_ls2 = _cmp_colors[_least_sim_pair[1]]
            st.markdown(
                f'<div style="background:#1e293b;border-radius:10px;padding:18px 22px">'
                f'<p style="margin:0 0 12px;font-size:0.60rem;font-weight:600;color:#94a3b8;'
                f'text-transform:uppercase;letter-spacing:0.8px">Pairwise Similarity</p>'
                f'{_matrix_html}'
                f'<p style="margin:12px 0 0;font-size:0.78rem;color:#64748b;line-height:1.7">'
                f'Most similar: <b style="color:{_c_ms1}">{_most_sim_pair[0].split()[-1]}</b> &amp; '
                f'<b style="color:{_c_ms2}">{_most_sim_pair[1].split()[-1]}</b> ({_most_sim_pair[2]:.0f}%). '
                f'Most contrasting: <b style="color:{_c_ls1}">{_least_sim_pair[0].split()[-1]}</b> &amp; '
                f'<b style="color:{_c_ls2}">{_least_sim_pair[1].split()[-1]}</b> ({_least_sim_pair[2]:.0f}%).'
                f'</p>'
                f'<p style="margin:4px 0 0;font-size:0.72rem;color:#64748b;font-style:italic">'
                f'Green = highly interchangeable · Amber = stylistic overlap · Grey = distinct archetypes'
                f'</p></div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # ── Radar overlay ──────────────────────────────────────────────
        st.markdown('<p class="section-title">Tactical Fingerprint</p>', unsafe_allow_html=True)
        _pct_lbl = "within-league" if _league_mode else "cross-league"
        st.caption(
            f"Percentile ranks ({_pct_lbl}) across 8 creation metrics. "
            "Overlapping fills show shared strengths. Gaps between traces reveal where one player "
            "covers ground the other doesn't."
        )
        fig_radar_cmp = create_comparison_radar(
            [player_view_dict(r, active_pct_suffix) for _, r in compare_df.iterrows()],
            compare_df["player_name"].tolist(),
            metrics=CORE_METRICS,
        )
        st.plotly_chart(fig_radar_cmp, use_container_width=True)

        # ── Spike callout: each player's sharpest strength on the radar ──
        if CORE_METRICS:
            _spike_parts = []
            for _spn in selected_players:
                _spc = _cmp_colors[_spn]
                _spv = player_view_dict(compare_df[compare_df["player_name"] == _spn].iloc[0], active_pct_suffix)
                _sp_best_m = max(CORE_METRICS, key=lambda m: float(_spv.get(m, 0) or 0))
                _sp_best_v = float(_spv.get(_sp_best_m, 0) or 0)
                _spike_parts.append(
                    f'<b style="color:{_spc}">{_spn.split()[-1]}</b>: '
                    f'<b style="color:#f1f5f9">{label(_sp_best_m)}</b> ({_sp_best_v:.0f}th pct)'
                )
            st.markdown(
                f'<div style="background:#1e293b;border-radius:8px;padding:10px 16px;'
                f'font-size:0.82rem;color:#64748b;line-height:1.9">'
                f'<span style="color:#94a3b8;font-size:0.68rem;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:0.7px;margin-right:10px">Sharpest spikes</span>'
                + " &nbsp;·&nbsp; ".join(_spike_parts)
                + f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # ── Role fit — bars (2 players) or heatmap (3-4 players) ──────
        if has_roles and ROLE_SCORE_COLS:
            st.markdown('<p class="section-title">Tactical Slot Fit</p>', unsafe_allow_html=True)
            st.caption(
                "Score 0–100 on every tactical slot. ★ marks each player's primary role. "
                "The slot you need to fill doesn't have to match their natural role — look for the highest score."
            )
            _role_short = {
                "Creator": "Creator", "Ball Progressor": "Progressor",
                "Box Threat": "Box Threat", "Deep Builder": "Deep Builder",
            }
            _shared_xlabels = [_role_short.get(r, r) for r in ALL_ROLES]

            if len(selected_players) <= 2:
                # Grouped bar chart for 2 players
                fig_role_fit = go.Figure()
                for _pn in selected_players:
                    _pr    = compare_df[compare_df["player_name"] == _pn].iloc[0]
                    _pc    = _cmp_colors[_pn]
                    _prim  = _pr.get(config.PRIMARY_ROLE_COL, "")
                    _yvals = [float(_pr.get(role_score_col(r), 0) or 0) for r in ALL_ROLES]
                    _is_prim = [r == _prim for r in ALL_ROLES]
                    fig_role_fit.add_trace(go.Bar(
                        name=_pn, x=_shared_xlabels, y=_yvals,
                        marker_color=_pc, opacity=0.85,
                        text=["★" if p else "" for p in _is_prim],
                        textposition="outside",
                        textfont=dict(size=12, color=_pc),
                        hovertemplate=f"<b>{_pn}</b><br>%{{x}}: %{{y:.1f}}<extra></extra>",
                    ))
                fig_role_fit.update_layout(**dark_layout(
                    barmode="group", height=320,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                                font=dict(size=11, color=D_TEXT), bgcolor="rgba(0,0,0,0)"),
                    xaxis=dict(tickfont=dict(size=11, color=D_TEXT)),
                    yaxis=dict(title="Role score", range=[0, 116], gridcolor=D_GRID, color=D_TICK, dtick=25),
                    margin=dict(l=10, r=10, t=50, b=10),
                ))
                st.plotly_chart(fig_role_fit, use_container_width=True)
                # Role narrative for 2 players
                _rf_p1, _rf_p2 = selected_players
                _rf_r1 = compare_df[compare_df["player_name"] == _rf_p1].iloc[0]
                _rf_r2 = compare_df[compare_df["player_name"] == _rf_p2].iloc[0]
                _rf_lines = []
                for r in ALL_ROLES:
                    _s1 = float(_rf_r1.get(role_score_col(r), 0) or 0)
                    _s2 = float(_rf_r2.get(role_score_col(r), 0) or 0)
                    _gap = abs(_s1 - _s2)
                    if _gap > 8:
                        _rf_winner = _rf_p1 if _s1 > _s2 else _rf_p2
                        _rf_wc = _cmp_colors[_rf_winner]
                        _rf_rc = role_color(r)
                        _rf_lines.append(
                            f'<b style="color:{_rf_wc}">{_rf_winner.split()[-1]}</b> scores higher as a '
                            f'<b style="color:{_rf_rc}">{r}</b> (+{_gap:.0f})'
                        )
                if _rf_lines:
                    st.markdown(
                        f'<div style="background:#1e293b;border-radius:8px;padding:10px 16px;'
                        f'font-size:0.82rem;color:#94a3b8;line-height:1.9">'
                        + " &nbsp;·&nbsp; ".join(_rf_lines)
                        + f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                # Heatmap for 3-4 players — much less crowded
                _hm_z, _hm_text = [], []
                for _pn in selected_players:
                    _pr   = compare_df[compare_df["player_name"] == _pn].iloc[0]
                    _prim = _pr.get(config.PRIMARY_ROLE_COL, "")
                    _row_z, _row_t = [], []
                    for r in ALL_ROLES:
                        v = float(_pr.get(role_score_col(r), 0) or 0)
                        _row_z.append(v)
                        _row_t.append(f"{'★ ' if r == _prim else ''}{v:.0f}")
                    _hm_z.append(_row_z)
                    _hm_text.append(_row_t)

                fig_role_fit = go.Figure(go.Heatmap(
                    z=_hm_z,
                    x=_shared_xlabels,
                    y=[p.split()[-1] for p in selected_players],
                    text=_hm_text,
                    texttemplate="%{text}",
                    textfont=dict(size=13, color="#f1f5f9"),
                    colorscale=[[0, "#0f172a"], [0.5, "#1e3a5f"], [1, "#0095FF"]],
                    showscale=False,
                    hovertemplate="%{y} · %{x}: %{z:.0f}<extra></extra>",
                ))
                fig_role_fit.update_layout(**dark_layout(
                    height=max(160, len(selected_players) * 60),
                    margin=dict(l=10, r=10, t=20, b=10),
                    xaxis=dict(tickfont=dict(size=11, color=D_TEXT), side="top"),
                    yaxis=dict(tickfont=dict(size=11, color=D_TEXT)),
                ))
                st.plotly_chart(fig_role_fit, use_container_width=True)

            # Role description cards — what each slot means
            if ALL_ROLES and ROLE_DESCRIPTIONS:
                _rd_cols = st.columns(len(ALL_ROLES))
                for _rdi, _rdn in enumerate(ALL_ROLES):
                    _rdc = role_color(_rdn)
                    _rd_desc = ROLE_DESCRIPTIONS.get(_rdn, "")
                    _rd_metrics = list(config.ROLE_WEIGHTS.get(_rdn, {}).keys())[:2]
                    _rd_metric_labels = ", ".join(label(m) for m in _rd_metrics)
                    with _rd_cols[_rdi]:
                        st.markdown(
                            f'<div style="background:#0f172a;border-radius:8px;padding:10px 12px;'
                            f'border-top:2px solid {_rdc}">'
                            f'<div style="color:{_rdc};font-weight:700;font-size:0.76rem;'
                            f'margin-bottom:5px">{_rdn}</div>'
                            f'<div style="color:#64748b;font-size:0.72rem;line-height:1.5;'
                            f'margin-bottom:5px">{_rd_desc}</div>'
                            f'<div style="color:#64748b;font-size:0.68rem">Key: {_rd_metric_labels}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            st.markdown("---")

        # ── Where the Gap Opens — top-10 most differentiated metrics ──
        st.markdown('<p class="section-title">Where the Gap Opens</p>', unsafe_allow_html=True)

        _battle_metrics = list(dict.fromkeys(
            list(config.CHANCE_CREATION_METRICS) +
            [m for w in config.ROLE_WEIGHTS.values() for m in w]
        ))
        _battle_avail = [m for m in _battle_metrics if f"{m}{active_pct_suffix}" in compare_df.columns]
        _verdict_winner = None
        _battle_sorted_all: list = []

        if _battle_avail:
            def _metric_spread(m):
                vals = [
                    float(compare_df.loc[compare_df["player_name"] == p, f"{m}{active_pct_suffix}"].values[0] or 0)
                    for p in selected_players
                ]
                return max(vals) - min(vals) if len(vals) > 1 else 0

            _battle_sorted_all = sorted(_battle_avail, key=_metric_spread, reverse=True)
            _show_all = st.toggle("Show all metrics", value=False)
            _battle_sorted = _battle_sorted_all if _show_all else _battle_sorted_all[:10]
            _battle_labels = [label(m) for m in _battle_sorted]

            st.caption(
                f"Top {len(_battle_sorted)} metrics where these players diverge most — biggest gaps first. "
                "A scout targeting a specific quality should focus here."
                + (" Toggle above to see all." if not _show_all else "")
            )

            fig_battle = go.Figure()
            for _pn in selected_players:
                _pc = _cmp_colors[_pn]
                _pcts = [
                    float(compare_df.loc[compare_df["player_name"] == _pn, f"{m}{active_pct_suffix}"].values[0] or 0)
                    if f"{m}{active_pct_suffix}" in compare_df.columns else 0
                    for m in _battle_sorted
                ]
                _raws = [
                    float(compare_df.loc[compare_df["player_name"] == _pn, m].values[0] or 0)
                    if m in compare_df.columns else 0
                    for m in _battle_sorted
                ]
                fig_battle.add_trace(go.Bar(
                    name=_pn, y=_battle_labels, x=_pcts, orientation="h",
                    marker_color=_pc, opacity=0.85,
                    hovertemplate=f"<b>{_pn}</b><br>%{{y}}: %{{x:.0f}}th pct · %{{customdata:.2f}} / 90<extra></extra>",
                    customdata=_raws,
                ))

            # Verdict: who wins the most metrics
            _wins = {p: 0 for p in selected_players}
            for m in _battle_sorted:
                _col = f"{m}{active_pct_suffix}"
                _scores = {p: float(compare_df.loc[compare_df["player_name"] == p, _col].values[0] or 0)
                           for p in selected_players if _col in compare_df.columns}
                if _scores:
                    _winner = max(_scores, key=_scores.get)
                    _wins[_winner] += 1
            _verdict_winner = max(_wins, key=_wins.get)
            _verdict_color  = _cmp_colors[_verdict_winner]
            _verdict_sorted = sorted(_wins.items(), key=lambda x: -x[1])

            # Find the winner's sharpest differentiating metric
            _vw_best_m, _vw_best_gap = None, -1.0
            for _bm in _battle_sorted_all[:5]:
                _bcol = f"{_bm}{active_pct_suffix}"
                if _bcol not in compare_df.columns:
                    continue
                _bwv = float(compare_df.loc[compare_df["player_name"] == _verdict_winner, _bcol].values[0] or 0)
                _bov = [
                    float(compare_df.loc[compare_df["player_name"] == p, _bcol].values[0] or 0)
                    for p in selected_players if p != _verdict_winner and _bcol in compare_df.columns
                ]
                if _bov and (_bwv - max(_bov)) > _vw_best_gap:
                    _vw_best_gap = _bwv - max(_bov)
                    _vw_best_m = _bm

            # Role-dimension breakdown of who wins where
            _role_metric_map = {r: set(config.ROLE_WEIGHTS.get(r, {}).keys()) for r in ALL_ROLES}
            _player_role_wins: dict[str, dict[str, int]] = {p: {r: 0 for r in ALL_ROLES} for p in selected_players}
            for _bm in _battle_sorted:
                _bcol = f"{_bm}{active_pct_suffix}"
                _bscores = {p: float(compare_df.loc[compare_df["player_name"] == p, _bcol].values[0] or 0)
                            for p in selected_players if _bcol in compare_df.columns}
                if not _bscores:
                    continue
                _bwinner = max(_bscores, key=_bscores.get)
                for r, mset in _role_metric_map.items():
                    if _bm in mset:
                        _player_role_wins[_bwinner][r] += 1

            # Build verdict narrative
            _vw_name = _verdict_winner.split()[-1]
            _vw_wins_n, _vw_total = _verdict_sorted[0][1], len(_battle_sorted)
            _verdict_narrative = (
                f'<b style="color:{_verdict_color}">{_vw_name}</b> wins '
                f'<b style="color:#f1f5f9">{_vw_wins_n}/{_vw_total}</b> tracked metrics'
            )
            if _vw_best_m and _vw_best_gap > 0:
                _verdict_narrative += (
                    f', with the sharpest edge in <b style="color:#f1f5f9">{label(_vw_best_m)}</b>'
                    f' (+{_vw_best_gap:.0f} pct pts ahead).'
                )
            else:
                _verdict_narrative += "."

            # Role-dimension callout for the overall winner
            _vw_top_roles = sorted(
                [(r, _player_role_wins[_verdict_winner][r]) for r in ALL_ROLES if _player_role_wins[_verdict_winner][r] > 0],
                key=lambda x: -x[1],
            )
            if _vw_top_roles:
                _top_r, _top_r_n = _vw_top_roles[0]
                _verdict_narrative += (
                    f' Leads the <b style="color:{role_color(_top_r)}">{_top_r}</b> dimension '
                    f'({_top_r_n} metric{"s" if _top_r_n != 1 else ""}).'
                )

            _verdict_counts_html = " &nbsp;·&nbsp; ".join(
                f'<b style="color:{_cmp_colors[p]}">{p.split()[-1]}</b> {w}/{_vw_total}'
                for p, w in _verdict_sorted
            )

            fig_battle.update_layout(**dark_layout(
                barmode="group",
                height=max(280, len(_battle_sorted) * 28),
                xaxis=dict(title="Percentile rank", range=[0, 110], gridcolor=D_GRID, color=D_TICK, ticksuffix="th"),
                yaxis=dict(tickfont=dict(size=10, color=D_TEXT), autorange="reversed"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                            font=dict(size=11, color=D_TEXT), bgcolor="rgba(0,0,0,0)"),
                margin=dict(l=10, r=10, t=50, b=10),
            ))
            st.plotly_chart(fig_battle, use_container_width=True)

            # Battleground verdict
            st.markdown(
                f'<div style="background:#1e293b;border-radius:8px;padding:14px 18px;'
                f'border-left:4px solid {_verdict_color}">'
                f'<p style="margin:0 0 5px;font-size:0.68rem;font-weight:600;color:#94a3b8;'
                f'text-transform:uppercase;letter-spacing:0.7px">Battleground verdict</p>'
                f'<p style="margin:0 0 6px;font-size:0.86rem;color:#cbd5e1">{_verdict_narrative}</p>'
                f'<p style="margin:0;font-size:0.78rem;color:#64748b">{_verdict_counts_html}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Scout Summary (2-player only) ──────────────────────────────
        if len(selected_players) == 2:
            st.markdown("---")
            st.markdown('<p class="section-title">Scout Summary</p>', unsafe_allow_html=True)
            _ss_p1, _ss_p2 = selected_players
            _ss_r1 = compare_df[compare_df["player_name"] == _ss_p1].iloc[0]
            _ss_r2 = compare_df[compare_df["player_name"] == _ss_p2].iloc[0]
            _ss_c1, _ss_c2 = _cmp_colors[_ss_p1], _cmp_colors[_ss_p2]
            _ss_role1 = _ss_r1.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
            _ss_role2 = _ss_r2.get(config.PRIMARY_ROLE_COL, "") if has_roles else ""
            _ss_score1 = float(_ss_r1.get(role_score_col(_ss_role1), 0) or 0) if _ss_role1 else 0.0
            _ss_score2 = float(_ss_r2.get(role_score_col(_ss_role2), 0) or 0) if _ss_role2 else 0.0
            _ss_age1 = int(_ss_r1["age"]) if "age" in _ss_r1 and pd.notna(_ss_r1["age"]) else None
            _ss_age2 = int(_ss_r2["age"]) if "age" in _ss_r2 and pd.notna(_ss_r2["age"]) else None
            _ss_mins1 = int(_ss_r1.get("minutes_played", 0) or 0)
            _ss_mins2 = int(_ss_r2.get("minutes_played", 0) or 0)
            _ss_sim_val = _pairwise_sim(_ss_p1, _ss_p2)
            _ss_sim_lbl = (
                "very similar profiles" if _ss_sim_val >= 80 else
                "similar profiles" if _ss_sim_val >= 70 else
                "partially overlapping profiles" if _ss_sim_val >= 55 else
                "contrasting profiles"
            )

            _ss_narrative_intros = {
                "Creator":         "unlocks defences through dangerous deliveries — key passes, through balls, and crosses",
                "Ball Progressor": "drives the team forward through direct carrying and dribbling",
                "Box Threat":      "generates constant threat through high box-touch volume and direct shooting",
                "Deep Builder":    "controls tempo from deep with accurate, forward-oriented passing",
            }

            # Build prose sentences
            _ss_lines = []
            _ss_n1 = _ss_p1.split()[-1]
            _ss_n2 = _ss_p2.split()[-1]
            _ss_flag1 = LEAGUE_FLAGS.get(_ss_r1.get("league", ""), "") if has_league_col else ""
            _ss_flag2 = LEAGUE_FLAGS.get(_ss_r2.get("league", ""), "") if has_league_col else ""

            # Opening line
            if _ss_role1 and _ss_role2:
                if _ss_role1 == _ss_role2:
                    _ss_lines.append(
                        f'<b style="color:{_ss_c1}">{_ss_n1}</b> ({_ss_flag1} {_ss_r1["team_name"]}) and '
                        f'<b style="color:{_ss_c2}">{_ss_n2}</b> ({_ss_flag2} {_ss_r2["team_name"]}) '
                        f'share the same primary role — '
                        f'<b style="color:{role_color(_ss_role1)}">{_ss_role1}</b> — '
                        f'with {_ss_sim_lbl} ({_ss_sim_val:.0f}% match).'
                    )
                else:
                    _ss_lines.append(
                        f'<b style="color:{_ss_c1}">{_ss_n1}</b> ({_ss_flag1} {_ss_r1["team_name"]}) is a '
                        f'<b style="color:{role_color(_ss_role1)}">{_ss_role1}</b> — '
                        f'{_ss_narrative_intros.get(_ss_role1, "contributes across the midfield")}. '
                        f'<b style="color:{_ss_c2}">{_ss_n2}</b> ({_ss_flag2} {_ss_r2["team_name"]}) is a '
                        f'<b style="color:{role_color(_ss_role2)}">{_ss_role2}</b> — '
                        f'{_ss_narrative_intros.get(_ss_role2, "contributes across the midfield")}. '
                        f'Overall {_ss_sim_lbl} ({_ss_sim_val:.0f}% match).'
                    )

            # Role-fit sentence
            if _ss_role1 and _ss_role2 and _ss_role1 != _ss_role2:
                _ss_stronger = _ss_p1 if _ss_score1 >= _ss_score2 else _ss_p2
                _ss_stronger_role = _ss_role1 if _ss_stronger == _ss_p1 else _ss_role2
                _ss_stronger_sc = max(_ss_score1, _ss_score2)
                _ss_weaker_sc = min(_ss_score1, _ss_score2)
                _ss_sc = _ss_c1 if _ss_stronger == _ss_p1 else _ss_c2
                _ss_lines.append(
                    f'<b style="color:{_ss_sc}">{_ss_stronger.split()[-1]}</b> rates higher in their primary role '
                    f'(<b style="color:{role_color(_ss_stronger_role)}">{_ss_stronger_role}</b>: '
                    f'{_ss_stronger_sc:.0f} vs {_ss_weaker_sc:.0f}).'
                )

            # Top battleground metric
            if _battle_avail and _battle_sorted_all:
                _ss_top_m = _battle_sorted_all[0]
                _ss_top_col = f"{_ss_top_m}{active_pct_suffix}"
                if _ss_top_col in compare_df.columns:
                    _ss_v1 = float(compare_df.loc[compare_df["player_name"] == _ss_p1, _ss_top_col].values[0] or 0)
                    _ss_v2 = float(compare_df.loc[compare_df["player_name"] == _ss_p2, _ss_top_col].values[0] or 0)
                    _ss_top_leader = _ss_p1 if _ss_v1 >= _ss_v2 else _ss_p2
                    _ss_top_lc = _ss_c1 if _ss_top_leader == _ss_p1 else _ss_c2
                    _ss_top_lead_v, _ss_top_trail_v = ((_ss_v1, _ss_v2) if _ss_v1 >= _ss_v2 else (_ss_v2, _ss_v1))
                    _ss_lines.append(
                        f'The biggest gap is <b style="color:#f1f5f9">{label(_ss_top_m)}</b>: '
                        f'<b style="color:{_ss_top_lc}">{_ss_top_leader.split()[-1]}</b> leads '
                        f'({_ss_top_lead_v:.0f}th vs {_ss_top_trail_v:.0f}th pct).'
                    )

            # Age context
            if _ss_age1 and _ss_age2 and abs(_ss_age1 - _ss_age2) >= 3:
                _ss_younger = _ss_p1 if _ss_age1 < _ss_age2 else _ss_p2
                _ss_older   = _ss_p2 if _ss_younger == _ss_p1 else _ss_p1
                _ss_yc = _ss_c1 if _ss_younger == _ss_p1 else _ss_c2
                _ss_age_diff = abs(_ss_age1 - _ss_age2)
                _ss_lines.append(
                    f'At {min(_ss_age1, _ss_age2)}, '
                    f'<b style="color:{_ss_yc}">{_ss_younger.split()[-1]}</b> is {_ss_age_diff} years younger — '
                    f'the longer-term development profile if your timeline extends beyond this window.'
                )

            # Minutes context
            if _ss_mins1 and _ss_mins2:
                _ss_higher_mins = _ss_p1 if _ss_mins1 >= _ss_mins2 else _ss_p2
                _ss_hmc = _ss_c1 if _ss_higher_mins == _ss_p1 else _ss_c2
                _ss_min_ratio = max(_ss_mins1, _ss_mins2) / max(min(_ss_mins1, _ss_mins2), 1)
                if _ss_min_ratio >= 1.2:
                    _ss_lines.append(
                        f'<b style="color:{_ss_hmc}">{_ss_higher_mins.split()[-1]}</b> has accumulated '
                        f'significantly more minutes ({max(_ss_mins1, _ss_mins2):,} vs {min(_ss_mins1, _ss_mins2):,}) — '
                        f'a larger sample for this profile.'
                    )

            _ss_lead_color = _ss_c1 if _verdict_winner == _ss_p1 else _ss_c2 if _battle_avail else "#334155"
            st.markdown(
                f'<div class="narrative-card" style="border-left:4px solid {_ss_lead_color}">'
                + "<br>".join(f'<p style="margin:0 0 8px 0">{ln}</p>' for ln in _ss_lines)
                + f'</div>',
                unsafe_allow_html=True,
            )


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
            "Labelled players have the highest Overall Score."
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


# ══════════════════════════════════════════════════════════════════════
# TAB 6 — LEAGUE OVERVIEW
# ══════════════════════════════════════════════════════════════════════
with tab_league:

    if not has_league_col or not has_roles or not ROLE_SCORE_COLS:
        st.info("League data not available. Run the multi-league pipeline first.")
    else:
        # Use full df filtered only by minutes/age/position — not by league sidebar selection
        _ov_mask = df["minutes_played"] >= min_mins
        if "age" in df.columns:
            _ov_mask &= (df["age"] >= age_range[0]) & (df["age"] <= age_range[1])
        if selected_positions:
            _ov_mask &= df["position"].isin(selected_positions)
        ov_df = df[_ov_mask].copy()
        leagues_in_ov = sorted(ov_df["league"].dropna().unique().tolist())

        if len(leagues_in_ov) < 2:
            st.info("Load data for multiple leagues to see the League Overview.")
        else:
            _lg_palette = {
                lg: c for lg, c in zip(
                    leagues_in_ov,
                    ["#0095FF", "#FF5252", "#00C896", "#FF9800", "#B450FF", "#FFC400"],
                )
            }
            _role_abbrev_lg = {
                "Creator":         "Creator",
                "Ball Progressor": "Progressor",
                "Box Threat":      "Box Threat",
                "Deep Builder":    "Deep Builder",
            }

            # Pre-compute per-league averages once
            _lg_avgs: dict[str, dict[str, float]] = {}
            for _lg in leagues_in_ov:
                _lgdf = ov_df[ov_df["league"] == _lg]
                _lg_avgs[_lg] = {
                    r: (_lgdf[role_score_col(r)].mean() if role_score_col(r) in _lgdf.columns else 0.0)
                    for r in ALL_ROLES
                }

            # ── Header ──────────────────────────────────────────────────
            st.markdown('<p class="section-title">League Identity</p>', unsafe_allow_html=True)
            st.markdown(
                "Each of Europe's top five leagues has a distinct midfield character — shaped "
                "by tactical culture, coaching philosophy, and recruitment patterns. "
                "This page reveals those identities through the lens of four tactical roles."
            )
            st.markdown("<div style='margin:16px 0'></div>", unsafe_allow_html=True)

            # ── League identity cards ────────────────────────────────────
            _id_cols = st.columns(len(leagues_in_ov))
            for _ci, _lg in enumerate(leagues_in_ov):
                _avgs_lg  = _lg_avgs[_lg]
                _sorted_r = sorted(_avgs_lg.items(), key=lambda x: x[1], reverse=True)
                _top_role, _top_sc = _sorted_r[0]
                _r2, _r3  = _sorted_r[1][0], _sorted_r[2][0]
                _rc       = role_color(_top_role)
                _n_pl     = int((ov_df["league"] == _lg).sum())
                _avg_ov   = ov_df.loc[ov_df["league"] == _lg, score_col].mean() \
                            if score_col in ov_df.columns else 0
                with _id_cols[_ci]:
                    st.markdown(
                        f'<div style="background:#1e293b;border-radius:10px;padding:16px;'
                        f'border-top:3px solid {_rc};text-align:center">'
                        f'<div style="font-size:1.8rem">{LEAGUE_FLAGS.get(_lg,"")}</div>'
                        f'<div style="font-size:0.88rem;font-weight:700;color:#f1f5f9;margin-top:6px">'
                        f'{LEAGUE_DISPLAY.get(_lg, _lg.replace("_"," "))}</div>'
                        f'<div style="margin:10px 0;padding:10px;background:{_rc}15;'
                        f'border-radius:8px;border:1px solid {_rc}30">'
                        f'<div style="color:{_rc};font-weight:700;font-size:0.85rem">'
                        f'{_top_role}</div>'
                        f'<div style="color:#64748b;font-size:0.72rem;margin-top:2px">'
                        f'dominant role · {_top_sc:.0f} avg</div>'
                        f'</div>'
                        f'<div style="font-size:0.75rem;color:#94a3b8;line-height:2">'
                        f'{_r2}<br>'
                        f'{_r3}</div>'
                        f'<div style="margin-top:10px;display:flex;justify-content:space-around;'
                        f'font-size:0.72rem">'
                        f'<span style="color:#64748b">{_n_pl} players</span>'
                        f'<span style="color:#94a3b8">avg OVR {_avg_ov:.0f}</span>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            st.markdown("---")

            # ── Role fingerprint heatmap ─────────────────────────────────
            st.markdown('<p class="section-title">Role Fingerprint by League</p>', unsafe_allow_html=True)
            st.caption(
                "Average role score across all qualified midfielders per league. "
                "★ marks the top league for each role."
            )
            _hm_roles   = [_role_abbrev_lg.get(r, r) for r in ALL_ROLES]
            _hm_leagues = [league_badge(_lg) for _lg in leagues_in_ov]
            _hm_z, _hm_text = [], []
            # per-role max for ★ annotation
            _role_max = {
                r: max(leagues_in_ov, key=lambda lg: _lg_avgs[lg].get(r, 0))
                for r in ALL_ROLES
            }
            for _lg in leagues_in_ov:
                _row_z, _row_t = [], []
                for r in ALL_ROLES:
                    v = _lg_avgs[_lg].get(r, 0)
                    _row_z.append(v)
                    _row_t.append(f"{'★ ' if _role_max[r] == _lg else ''}{v:.1f}")
                _hm_z.append(_row_z)
                _hm_text.append(_row_t)

            fig_lg_hm = go.Figure(go.Heatmap(
                z=_hm_z,
                x=_hm_roles,
                y=_hm_leagues,
                text=_hm_text,
                texttemplate="%{text}",
                textfont=dict(size=13, color="#f1f5f9"),
                colorscale=[[0, "#0f172a"], [0.4, "#1e3a5f"], [1, "#0095FF"]],
                showscale=True,
                colorbar=dict(
                    title=dict(text="Avg score", font=dict(color=D_TICK, size=11)),
                    tickfont=dict(color=D_TICK, size=10),
                    thickness=14, len=0.8,
                    bgcolor="rgba(0,0,0,0)",
                    outlinewidth=0,
                ),
                hovertemplate="<b>%{y}</b><br>%{x}: %{z:.1f}<extra></extra>",
            ))
            fig_lg_hm.update_layout(**dark_layout(
                height=max(220, len(leagues_in_ov) * 56),
                xaxis=dict(tickfont=dict(size=12, color=D_TEXT), side="top", tickangle=-20),
                yaxis=dict(tickfont=dict(size=12, color=D_TEXT), autorange="reversed"),
                margin=dict(l=10, r=80, t=60, b=10),
            ))
            st.plotly_chart(fig_lg_hm, use_container_width=True)

            st.markdown("---")

            # ── League vs league — grouped bar ───────────────────────────
            st.markdown('<p class="section-title">Role Scores — League vs League</p>', unsafe_allow_html=True)
            st.caption("Average role score per league. Which league produces the strongest players in each archetype?")
            fig_lgbar = go.Figure()
            for _lg in leagues_in_ov:
                fig_lgbar.add_trace(go.Bar(
                    name=league_badge(_lg),
                    x=[_role_abbrev_lg.get(r, r) for r in ALL_ROLES],
                    y=[_lg_avgs[_lg].get(r, 0) for r in ALL_ROLES],
                    marker_color=_lg_palette[_lg],
                    hovertemplate=f"<b>{league_badge(_lg)}</b><br>%{{x}}: %{{y:.1f}}<extra></extra>",
                ))
            fig_lgbar.update_layout(**dark_layout(
                barmode="group", height=360,
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=11, color=D_TEXT), bgcolor="rgba(0,0,0,0)",
                ),
                xaxis=dict(tickfont=dict(size=10, color=D_TEXT), tickangle=-20),
                yaxis=dict(
                    title="Avg role score", range=[0, 80],
                    gridcolor=D_GRID, color=D_TICK, dtick=20,
                ),
                margin=dict(l=10, r=10, t=50, b=10),
            ))
            st.plotly_chart(fig_lgbar, use_container_width=True)

            st.markdown("---")

            # ── Best player per role per league ─────────────────────────
            st.markdown('<p class="section-title">Best in Class — Top Player per Role per League</p>', unsafe_allow_html=True)
            st.caption(
                "The highest-scoring player for each role within each league. "
                "Only players whose **primary role** matches are included — scores reflect how well they fit that archetype."
            )
            _best_rows = []
            for _role in ALL_ROLES:
                _sc_r = role_score_col(_role)
                _row  = {"Role": _role}
                for _lg in leagues_in_ov:
                    _ldf = ov_df[
                        (ov_df["league"] == _lg) &
                        (ov_df.get(config.PRIMARY_ROLE_COL, pd.Series(dtype=str)) == _role)
                    ] if config.PRIMARY_ROLE_COL in ov_df.columns else pd.DataFrame()
                    if len(_ldf) > 0 and _sc_r in _ldf.columns:
                        _best = _ldf.nlargest(1, _sc_r).iloc[0]
                        _row[league_badge(_lg)] = f"{_best['player_name']} · {_best[_sc_r]:.0f}"
                    else:
                        _row[league_badge(_lg)] = "—"
                _best_rows.append(_row)
            _best_df = pd.DataFrame(_best_rows).set_index("Role")
            st.dataframe(_best_df, use_container_width=True, hide_index=False)

            st.markdown("---")

            # ── Age profile by league ────────────────────────────────────
            if "age" in ov_df.columns:
                st.markdown('<p class="section-title">Age Profile by League</p>', unsafe_allow_html=True)
                st.caption("Distribution of midfielder ages per league — reveals which leagues trust young players vs. experienced ones.")
                fig_age = go.Figure()
                for _lg in leagues_in_ov:
                    _ages = ov_df.loc[ov_df["league"] == _lg, "age"].dropna()
                    fig_age.add_trace(go.Box(
                        y=_ages,
                        name=league_badge(_lg),
                        marker_color=_lg_palette[_lg],
                        boxmean="sd",
                        hovertemplate=f"<b>{league_badge(_lg)}</b><br>Age: %{{y}}<extra></extra>",
                    ))
                fig_age.update_layout(**dark_layout(
                    height=320,
                    yaxis=dict(title="Age", gridcolor=D_GRID, color=D_TICK, dtick=2),
                    xaxis=dict(tickfont=dict(size=12, color=D_TEXT)),
                    margin=dict(l=10, r=10, t=20, b=10),
                    showlegend=False,
                ))
                st.plotly_chart(fig_age, use_container_width=True)


# ─── Footer ───────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "Built by **R. Berk Karatas** · "
    "[GitHub](https://github.com/rberkkaratas) · "
    "[LinkedIn](https://www.linkedin.com/in/rberkkaratas/) · "
    "Data: WhoScored · Top 5 Leagues 2025/26"
)

# ══════════════════════════════════════════════════════════════════
# TAB 7 — ABOUT
# ══════════════════════════════════════════════════════════════════
with tab_about:
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

