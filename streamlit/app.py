"""
Midfielder Scout — Streamlit entry point.
Wires together data loading, filtering, and tab rendering.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import config
from components.css import inject_css
from components.header import render_header
from components.filters import render_filters
from core.data_loader import DataLoader
from core.filter_service import FilterService
from tabs.shortlist import ShortlistTab
from tabs.role_map import RoleMapTab
from tabs.scout_report import ScoutReportTab
from tabs.compare import CompareTab
from tabs.explore import ExploreTab
from tabs.league_overview import LeagueOverviewTab
from tabs.about import AboutTab

st.set_page_config(page_title="Midfielder Scout 2025/26", page_icon="⚽", layout="wide")
inject_css()

# ── Data ──────────────────────────────────────────────────────────────
df                         = DataLoader.load()
df                         = DataLoader.enrich(df)
raw_players_df, matches_df = DataLoader.load_raw()
last_updated               = DataLoader.load_last_updated()

if last_updated:
    st.info(f"Database last updated: **{last_updated}**", icon="🗓️")

# ── Session state ─────────────────────────────────────────────────────
if "profile_player" not in st.session_state:
    st.session_state["profile_player"] = None

# ── Header placeholder (rendered after filters, but positioned above) ─
header_slot = st.empty()
st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

# ── Filters ───────────────────────────────────────────────────────────
has_league_col = "league" in df.columns
has_tm_data    = "market_value_eur" in df.columns
all_leagues    = sorted(df["league"].dropna().unique().tolist()) if has_league_col else []
all_roles      = list(config.ROLE_WEIGHTS.keys())

filter_state = render_filters(df, has_league_col, has_tm_data, all_roles, all_leagues, config)

# ── Apply filters + build AppState ────────────────────────────────────
filtered  = FilterService.apply(df, filter_state, config.PRIMARY_ROLE_COL in df.columns, has_league_col, has_tm_data)
app_state = FilterService.build_app_state(df, filtered, raw_players_df, matches_df, filter_state, config)

# ── Header (fills the slot above filters) ─────────────────────────────
render_header(header_slot, app_state)

# ── Tab registry ──────────────────────────────────────────────────────
TABS = [
    ("📊 Shortlist",       ShortlistTab()),
    ("⚡ Role Map",         RoleMapTab()),
    ("👤 Scout Report",    ScoutReportTab()),
    ("🔍 Compare",         CompareTab()),
    ("📈 Explore",         ExploreTab()),
    ("🌍 League Overview", LeagueOverviewTab()),
    ("ℹ️ About",           AboutTab()),
]

tab_containers = st.tabs([name for name, _ in TABS])
for container, (_, renderer) in zip(tab_containers, TABS):
    with container:
        renderer.render(app_state)

# ── Footer ─────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .app-footer {
        margin-top: 3rem;
        padding: 1.2rem 1.5rem;
        border-top: 1px solid rgba(250,250,250,0.12);
        background: rgba(14,17,23,0.6);
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 0.5rem;
        font-size: 0.82rem;
        color: rgba(250,250,250,0.55);
    }
    .app-footer a {
        color: rgba(250,250,250,0.75);
        text-decoration: none;
        transition: color 0.2s;
    }
    .app-footer a:hover { color: #fff; }
    .footer-badge {
        background: rgba(255,255,255,0.07);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 20px;
        padding: 0.2rem 0.7rem;
        font-size: 0.75rem;
        white-space: nowrap;
    }
    .footer-links { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
    </style>
    <div class="app-footer">
        <div>
            Built by <strong style="color:rgba(250,250,250,0.85)">R. Berk Karatas</strong>
            &nbsp;·&nbsp;
            <a href="https://github.com/rberkkaratas" target="_blank">GitHub</a>
            &nbsp;·&nbsp;
            <a href="https://www.linkedin.com/in/rberkkaratas/" target="_blank">LinkedIn</a>
        </div>
        <div class="footer-links">
            <span class="footer-badge">⚽ Top 5 Leagues 2025/26</span>
            <span class="footer-badge">📡 Events: WhoScored</span>
            <span class="footer-badge">💶 Values: Transfermarkt</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
