"""
Central configuration for the Top 5 League Midfielder Scouting project.
All paths, thresholds, and parameters live here.
"""

from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent
DATA_ENRICHMENT = ROOT_DIR / "data" / "enrichment"
MATCH_IDS_DIR   = ROOT_DIR / "data" / "match_ids"

# Backward-compatible aliases (Serie A defaults — used by legacy scripts)
DATA_EVENTS    = ROOT_DIR / "data" / "events"    / "Serie_A" / "2025-2026"
DATA_PROCESSED = ROOT_DIR / "data" / "processed" / "Serie_A" / "2025-2026"
DATA_FINAL     = ROOT_DIR / "data" / "final"

# ─── Path Helpers ────────────────────────────────────────────────────

def get_events_path(league: str, season: str) -> Path:
    return ROOT_DIR / "data" / "events" / league / season

def get_processed_path(league: str, season: str) -> Path:
    return ROOT_DIR / "data" / "processed" / league / season

def get_final_path(league: str, season: str) -> Path:
    return ROOT_DIR / "data" / "final" / f"{league}_{season}.csv"

def get_match_ids_path(league: str, season: str) -> Path:
    MATCH_IDS_DIR.mkdir(parents=True, exist_ok=True)
    return MATCH_IDS_DIR / f"{league}_{season}.csv"

# ─── Supported Leagues ───────────────────────────────────────────────
# fixture_url: the WhoScored fixtures page for this league/season.
#   Season and stage IDs change each year — update per season.
#   Format: https://www.whoscored.com/Regions/{region}/Tournaments/{tournament}/
#           Seasons/{season_id}/Stages/{stage_id}/Fixtures/{slug}
LEAGUES = {
    "Serie_A": {
        "display_name": "Serie A",
        "country": "Italy",
        "fixture_url": "https://www.whoscored.com/regions/108/tournaments/5/seasons/10732/stages/24500/fixtures/italy-serie-a-2025-2026",   # fill in: /Regions/108/Tournaments/5/Seasons/.../Fixtures/...
    },
    "Premier_League": {
        "display_name": "Premier League",
        "country": "England",
        "fixture_url": "https://www.whoscored.com/regions/252/tournaments/2/seasons/10743/stages/24533/fixtures/england-premier-league-2025-2026",   # fill in: /Regions/252/Tournaments/2/Seasons/.../Fixtures/...
    },
    "La_Liga": {
        "display_name": "La Liga",
        "country": "Spain",
        "fixture_url": "https://www.whoscored.com/regions/206/tournaments/4/seasons/10803/stages/24622/fixtures/spain-laliga-2025-2026",   # fill in: /Regions/206/Tournaments/4/Seasons/.../Fixtures/...
    },
    "Bundesliga": {
        "display_name": "Bundesliga",
        "country": "Germany",
        "fixture_url": "https://www.whoscored.com/regions/81/tournaments/3/seasons/10720/stages/24478/fixtures/germany-bundesliga-2025-2026",   # fill in: /Regions/81/Tournaments/3/Seasons/.../Fixtures/...
    },
    "Ligue_1": {
        "display_name": "Ligue 1",
        "country": "France",
        "fixture_url": "https://www.whoscored.com/regions/74/tournaments/22/seasons/10792/stages/24609/fixtures/france-ligue-1-2025-2026",   # fill in: /Regions/74/Tournaments/22/Seasons/.../Fixtures/...
    },
}

# ─── Season & League ─────────────────────────────────────────────────
SEASON = "2025-2026"
LEAGUE = "Serie_A"

# ─── Scraper Settings ────────────────────────────────────────────────
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
# Eight metrics for the player radar chart — one per key creative dimension,
# covering all five creation roles without redundancy.
CHANCE_CREATION_METRICS = [
    "passes_into_penalty_area_p90", # box delivery — Creator primary
    "key_passes_p90",               # direct chance creation — Creator
    "crosses_p90",                  # wide delivery — Creator
    "carries_into_final_third_p90", # ball carrying — Ball Progressor primary
    "successful_dribbles_p90",      # dribbling — Ball Progressor
    "penalty_area_touches_p90",     # box presence — Box Threat primary
    "shots_p90",                    # direct goal threat — Box Threat
    "progressive_passes_p90",       # build-up progression — Deep Builder primary
]

# Overall chance-creation score — weighted blend of the five role scores.
# Creative Playmaker leads (most directly creates chances), Deep Builder trails
# (enables rather than directly creates). Weights sum to 1.0.
# Note: compute_composite_score() uses these as role-name → weight, not metric → weight.
COMPOSITE_WEIGHTS = {
    "Creator":         0.35,
    "Ball Progressor": 0.25,
    "Box Threat":      0.25,
    "Deep Builder":    0.15,
}

# ─── Clustering ──────────────────────────────────────────────────────
N_CLUSTERS = 3
CLUSTERING_FEATURES = CHANCE_CREATION_METRICS
RANDOM_STATE = 42

# ─── Role Scoring ─────────────────────────────────────────────────────
# Five creation-focused roles, each defined by 5 weighted metrics (sum = 1.0).
# Role score = weighted average of per-metric percentile ranks (0–100).
# primary_role = role with the highest score.
# No defensive metrics — this is a chance creators tool.

ROLE_SCORE_COL_PREFIX = "role_score_"   # e.g. "role_score_Creative Playmaker"
PRIMARY_ROLE_COL      = "primary_role"

ROLE_WEIGHTS = {
    # Creator: delivers the ball into dangerous areas regardless of method —
    # central key passes, wide crosses, through balls, or direct assists.
    # passes_into_penalty_area leads as the universal measure of dangerous delivery.
    "Creator": {
        "passes_into_penalty_area_p90": 0.30,
        "key_passes_p90":               0.25,
        "assists_p90":                  0.20,
        "crosses_p90":                  0.15,
        "through_balls_p90":            0.10,
    },
    # Ball Progressor: drives the team forward through carrying and dribbling.
    # Defined purely by the CARRY/DRIBBLE action — no destination metrics.
    # Distinct from Box Threat (who arrives in the box) and Deep Builder (who passes).
    "Ball Progressor": {
        "carries_into_final_third_p90": 0.40,
        "successful_dribbles_p90":      0.30,
        "progressive_passes_p90":       0.20,
        "progressive_carries_p90":      0.10,
    },
    # Box Threat: lives in the box, shoots, and creates from proximity.
    # Fully separated — no carries, no dribbles, no key passes, no assists.
    # touches_final_third ensures advanced area operation without overlapping
    # Ball Progressor's carrying metrics.
    "Box Threat": {
        "penalty_area_touches_p90":     0.40,
        "shots_p90":                    0.35,
        "touches_final_third_p90":      0.15,
        "passes_into_penalty_area_p90": 0.10,
    },
    # Deep Builder: enables through volume, accuracy, and forward-oriented passing.
    # Progressive passes lead; key_passes at low weight separates a creative deep
    # builder (Kroos) from a pure volume passer.
    "Deep Builder": {
        "progressive_passes_p90":       0.35,
        "pass_accuracy":                0.25,
        "total_passes_p90":             0.20,
        "forward_pass_pct":             0.10,
        "key_passes_p90":               0.10,
    },
}

ROLE_COLORS = {
    "Creator":         "#0095FF",
    "Ball Progressor": "#00C896",
    "Box Threat":      "#FF5252",
    "Deep Builder":    "#FF9800",
}

# ─── Transfermarkt Enrichment ─────────────────────────────────────────
TM_MATCH_THRESHOLD = 85                # rapidfuzz confidence for auto-verification
TM_CURRENT_SEASON_END_YEAR = int(SEASON.split("-")[1])   # e.g. 2026 from "2025-2026"

# Transfermarkt competition page URLs — one per top-5 league.
# Competition IDs are stable; only update if TM changes their URL structure.
TM_LEAGUE_URLS = {
    "Serie_A":       "https://www.transfermarkt.com/serie-a/startseite/wettbewerb/IT1",
    "Premier_League":"https://www.transfermarkt.com/premier-league/startseite/wettbewerb/GB1",
    "La_Liga":       "https://www.transfermarkt.com/laliga/startseite/wettbewerb/ES1",
    "Bundesliga":    "https://www.transfermarkt.com/bundesliga/startseite/wettbewerb/L1",
    "Ligue_1":       "https://www.transfermarkt.com/ligue-1/startseite/wettbewerb/FR1",
}
