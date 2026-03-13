"""
Central configuration for the Serie A Chance Creators scouting project.
All paths, thresholds, and parameters live here.
"""

from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent
DATA_EVENTS = ROOT_DIR / "data" / "events" / "Serie_A" / "2025-2026"
DATA_PROCESSED = ROOT_DIR / "data" / "processed"
DATA_FINAL = ROOT_DIR / "data" / "final"
DATA_ENRICHMENT = ROOT_DIR / "data" / "enrichment"

# ─── Season & League ─────────────────────────────────────────────────
SEASON = "2025-2026"
LEAGUE = "Serie_A"

# ─── Scraper Settings ────────────────────────────────────────────────
# Mirrors your config.json structure
SCRAPER_CONFIG = {
    "league": LEAGUE,
    "season": SEASON,
    "base_output_dir": str(ROOT_DIR / "data" / "events"),
}

REQUEST_DELAY_SECONDS = 2.0
PAGE_LOAD_WAIT = 7
PAGE_LOAD_WAIT_EXTENDED = 5

# ─── Player Filters ─────────────────────────────────────────────────
MIN_MINUTES_PLAYED = 600
MAX_AGE = 40
POSITIONS = [
    "AMC",   # Attacking midfielder central
    "AML",   # Attacking midfielder left
    "AMR",   # Attacking midfielder right
    "MC",    # Central midfielder
    "ML",    # Left midfielder
    "MR",    # Right midfielder
]

# ─── WhoScored Event Qualifiers ─────────────────────────────────────
# Qualifier IDs used to derive stats from raw event data.
# These come from WhoScored's qualifier system embedded in each event.
# You may need to verify/adjust these by inspecting your event CSVs.
QUALIFIER_IDS = {
    "key_pass": 179,             # keyPass qualifier
    "assisted": 210,             # assist qualifier
    "through_ball": 4,           # throughBall qualifier
    "long_ball": 1,              # longBall qualifier
    "cross": 2,                  # cross qualifier
    "corner_taken": 6,           # cornerTaken
    "free_kick_taken": 5,        # freeKickTaken
    "involved_player": 140,      # playerIdInvolved (for SCA chains)
}

# ─── Feature Engineering ─────────────────────────────────────────────
CHANCE_CREATION_METRICS = [
    "key_passes_p90",
    "passes_into_penalty_area_p90",
    "through_balls_p90",
    "assists_p90",
    "half_space_passes_p90",
    "successful_dribbles_p90",
]

# Weights for composite chance-creation score (must sum to 1.0).
# Removed: shot_creating_actions_p90 — derived as key_passes + dribbles, causing
#   double-counting at an effective ~37% for key passes and ~18% for dribbles.
# Removed: passes_into_final_third_p90, progressive_passes_p90 — ball progression
#   metrics, not chance creation; they belong in Ball Progressor role scoring.
# Added:   assists_p90 — direct output of chance creation, previously absent.
# Added:   half_space_passes_p90 — deliveries from the most dangerous off-centre zones.
COMPOSITE_WEIGHTS = {
    "key_passes_p90":               0.30,
    "passes_into_penalty_area_p90": 0.20,
    "through_balls_p90":            0.15,
    "assists_p90":                  0.15,
    "half_space_passes_p90":        0.10,
    "successful_dribbles_p90":      0.10,
}

# ─── Clustering ──────────────────────────────────────────────────────
N_CLUSTERS = 3
CLUSTERING_FEATURES = CHANCE_CREATION_METRICS
RANDOM_STATE = 42

# ─── Midfielder Role Scoring ──────────────────────────────────────────
# Six roles each defined by weighted percentile metrics (weights sum to 1.0).
# Role score = weighted average of per-metric percentile ranks (0–100).
# primary_role = role with the highest score.

ROLE_SCORE_COL_PREFIX = "role_score_"   # e.g. "role_score_Playmaker"
PRIMARY_ROLE_COL      = "primary_role"

ROLE_WEIGHTS = {
    # Direct chance creation: key passes and through balls are the primary signals.
    # SCA removed — it's derived from key_passes + dribbles and would double-count both.
    # passes_into_pa and half_space_passes both kept but treated as distinct spatial signals
    # (half_space = entry zone, pa = delivery zone). assists raised to reflect output quality.
    "Playmaker": {
        "key_passes_p90":               0.25,
        "passes_into_penalty_area_p90": 0.20,
        "through_balls_p90":            0.15,
        "assists_p90":                  0.15,
        "half_space_passes_p90":        0.15,
        "successful_dribbles_p90":      0.05,
        "penalty_area_touches_p90":     0.05,
    },
    # Progressive carries added as a true ball-progression signal distinct from passes.
    # passes_into_final_third removed — near-duplicate of progressive_passes.
    # pass_accuracy reduced: a safe, sideways passer should not score highly here.
    # forward_pass_pct raised: directional intent is the defining trait of a progressor.
    "Ball Progressor": {
        "progressive_passes_p90":       0.40,
        "carries_into_final_third_p90": 0.20,
        "forward_pass_pct":             0.15,
        "total_passes_p90":             0.15,
        "pass_accuracy":                0.10,
    },
    # possession_won removed — it is a composite of tackles_successful + interceptions
    # + ball_recoveries, so keeping it alongside tackles and interceptions triple-counts.
    # interceptions raised to 0.30: reading the game is the primary Ball Winner trait.
    # tackle_success_rate raised: efficiency matters more than raw volume.
    "Ball Winner": {
        "interceptions_p90":                0.30,
        "tackles_p90":                      0.25,
        "tackle_success_rate":              0.25,
        "possession_won_final_third_p90":   0.10,
        "ball_winning_height":              0.10,
    },
    # shots_blocked reduced: primarily a CB behaviour, high weight risks mis-classifying
    # deep-lying CBs who occasionally play in midfield.
    # aerials_total reduced and aerial_win_rate raised: dominance > volume.
    # interceptions_p90 added to capture the positional reading of a true shield.
    "Defensive Shield": {
        "aerial_win_rate":              0.30,
        "clearances_p90":               0.25,
        "interceptions_p90":            0.15,
        "aerials_total_p90":            0.15,
        "shots_blocked_p90":            0.15,
    },
    # SCA removed — contained successful_dribbles (already at 35%), causing double-count.
    # Replaced with key_passes_p90 to add a genuine secondary creative dimension.
    "Dribbler": {
        "successful_dribbles_p90":      0.35,
        "dribble_success_rate":         0.30,
        "carries_into_final_third_p90": 0.15,
        "key_passes_p90":               0.10,
        "penalty_area_touches_p90":     0.10,
    },
    # crosses volume reduced and cross_accuracy reduced: volume/rate conflict.
    # key_passes raised to 0.20 — cleanest chance-creation signal for a wide player.
    "Wide Creator": {
        "key_passes_p90":               0.20,
        "crosses_p90":                  0.25,
        "cross_accuracy":               0.20,
        "passes_into_penalty_area_p90": 0.20,
        "half_space_passes_p90":        0.15,
    },
}

ROLE_COLORS = {
    "Playmaker":        "#0095FF",
    "Ball Progressor":  "#00C896",
    "Ball Winner":      "#FF5252",
    "Defensive Shield": "#FF9800",
    "Dribbler":         "#B450FF",
    "Wide Creator":     "#FFC400",
}

# ─── Transfermarkt Enrichment ─────────────────────────────────────────
TM_MATCH_THRESHOLD = 85                # rapidfuzz confidence for auto-verification
TM_CURRENT_SEASON_END_YEAR = int(SEASON.split("-")[1])   # e.g. 2026 from "2025-2026"
