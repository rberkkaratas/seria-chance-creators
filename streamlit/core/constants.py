"""Shared constants and helper functions used across the dashboard."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import config

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
