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
MIN_MINUTES_PLAYED = 900
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
    "through_balls_p90",
    "passes_into_final_third_p90",
    "passes_into_penalty_area_p90",
    "shot_creating_actions_p90",
    "successful_dribbles_p90",
    "progressive_passes_p90",
]

# Weights for composite score (must sum to 1.0)
# Note: progressive_carries removed — WhoScored event data does not include Carry events.
# Its 5% redistributed to key_passes.
COMPOSITE_WEIGHTS = {
    "key_passes_p90": 0.25,
    "through_balls_p90": 0.10,
    "passes_into_final_third_p90": 0.10,
    "passes_into_penalty_area_p90": 0.15,
    "shot_creating_actions_p90": 0.20,
    "successful_dribbles_p90": 0.10,
    "progressive_passes_p90": 0.10,
}

# ─── Clustering ──────────────────────────────────────────────────────
N_CLUSTERS = 3
CLUSTERING_FEATURES = CHANCE_CREATION_METRICS
RANDOM_STATE = 42

# ─── Transfermarkt Enrichment ─────────────────────────────────────────
TM_MATCH_THRESHOLD = 85                # rapidfuzz confidence for auto-verification
TM_CURRENT_SEASON_END_YEAR = int(SEASON.split("-")[1])   # e.g. 2026 from "2025-2026"
