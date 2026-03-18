"""CSS injection for the dashboard."""

import streamlit as st


def inject_css() -> None:
    """Inject global CSS styles."""
    st.markdown("""
<style>
    section[data-testid="stMain"] > div {
        max-width: 1200px;
        margin: 0 auto;
        padding-left: 2rem;
        padding-right: 2rem;
    }
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
