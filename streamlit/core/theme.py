"""Dark theme constants shared across the dashboard."""

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
