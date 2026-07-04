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
    "long_balls_p90":                   "Long Balls / 90",
    "total_passes_p90":                 "Passes / 90",
    "accurate_passes_p90":              "Accurate Passes / 90",
    "pass_accuracy":                    "Pass Accuracy (%)",
    "dribble_success_rate":             "Dribble Success (%)",
    "tackle_success_rate":              "Tackle Success (%)",
    "aerial_win_rate":                  "Aerial Win Rate (%)",
    "cross_accuracy":                   "Cross Accuracy (%)",
    "tackles_p90":                      "Tackles / 90",
    "tackles_successful_p90":           "Successful Tackles / 90",
    "interceptions_p90":                "Interceptions / 90",
    "clearances_p90":                   "Clearances / 90",
    "ball_recoveries_p90":              "Ball Recoveries / 90",
    "shots_blocked_p90":                "Shots Blocked / 90",
    "aerials_won_p90":                  "Aerials Won / 90",
    "aerials_total_p90":                "Aerial Duels / 90",
    "possession_won_p90":               "Possession Won / 90",
    "possession_lost_p90":              "Possession Lost / 90",
    "touches_final_third_p90":          "Final Third Touches / 90",
}


def label(col: str) -> str:
    return METRIC_LABELS.get(col, col.replace("_p90", "").replace("_", " ").title())


TEAM_METRIC_LABELS = {
    "team_rating":                    "Team Rating",
    "team_strength_z":                "Squad Strength (z)",
    "global_rank":                    "Global Rank",
    "league_rank_rating":             "League Rank (Rating)",
    "league_rank_points":             "League Rank (Points)",
    "perf_delta_rank":                "Performance Δ",
    "matches_played":                 "MP",
    "wins":                           "W",
    "draws":                          "D",
    "losses":                         "L",
    "goals_for":                      "GF",
    "goals_against":                  "GA",
    "goal_diff":                      "GD",
    "points":                         "Pts",
    "points_per_match":               "Pts / Match",
    "possession_share":               "Possession (pass share)",
    "pass_accuracy":                  "Pass Accuracy",
    "passes_per_match":               "Passes / Match",
    "shots_per_match":                "Shots / Match",
    "shots_conceded_per_match":       "Shots Conceded / Match",
    "goals_per_match":                "Goals / Match",
    "goals_conceded_per_match":       "Goals Conceded / Match",
    "shot_conversion":                "Shot Conversion",
    "shot_conversion_against":        "Opp. Shot Conversion",
    "key_passes_per_match":           "Key Passes / Match",
    "ppda_proxy":                     "PPDA (proxy)",
    "progressive_passes_pm":          "Progressive Passes / Match",
    "passes_into_final_third_pm":     "Passes into Final Third / Match",
    "long_ball_share":                "Long-Ball Share",
    "forward_pass_pct":               "Forward Pass %",
    "crosses_pm":                     "Crosses / Match",
    "dribbles_pm":                    "Dribbles / Match",
    "aerials_won_pm":                 "Aerials Won / Match",
    "aerial_win_rate":                "Aerial Win %",
    "ball_recoveries_pm":             "Ball Recoveries / Match",
    "possession_won_final_third_pm":  "High Turnovers Won / Match",
    "ball_winning_height":            "Ball-Winning Height",
    "touches_final_third_pm":         "Final-Third Touches / Match",
    "penalty_area_touches_pm":        "Box Touches / Match",
    "squad_size":                     "Scored Players",
    "age_weighted":                   "Avg Age (min-weighted)",
    "age_median":                     "Median Age",
    "market_value_total_eur":         "Squad Value (€)",
    "market_value_median_eur":        "Median Value (€)",
    "rating_coverage":                "Rating Coverage",
    "qualified_players":              "Qualified Players",
    "club_elo":                       "Club Elo",
}


def team_label(col: str) -> str:
    return TEAM_METRIC_LABELS.get(col, col.replace("_pm", " / match").replace("_", " ").title())


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
    "Championship":   "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Primeira_Liga":  "🇵🇹",
    "Eredivisie":     "🇳🇱",
    "Belgium_Pro_League": "🇧🇪",
    "Super_Lig":      "🇹🇷",
}


def league_badge(league_key: str) -> str:
    flag = LEAGUE_FLAGS.get(league_key, "")
    name = LEAGUE_DISPLAY.get(league_key, league_key.replace("_", " "))
    return f"{flag} {name}"


def role_color(name: str) -> str:
    return config.ALL_ROLE_COLORS.get(name, "#888")


def role_score_col(role: str) -> str:
    return f"{config.ROLE_SCORE_COL_PREFIX}{role}"


# ─── Role Descriptions ────────────────────────────────────────────────
ROLE_ICONS: dict[str, str] = {}   # icons removed — kept for API compatibility

ROLE_DESCRIPTIONS = config.ALL_ROLE_DESCRIPTIONS
