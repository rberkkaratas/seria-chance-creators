"""
Central configuration for the European League Player Scout project.
All paths, thresholds, league definitions, position groups, and role taxonomies
live here.
"""

from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent
DATA_ENRICHMENT = ROOT_DIR / "data" / "enrichment"
MATCH_IDS_DIR   = ROOT_DIR / "data" / "match_ids"
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
    "Championship": {
        "display_name": "Championship",
        "country": "England",
        "fixture_url": "https://www.whoscored.com/regions/252/tournaments/7/seasons/10784/stages/24580/fixtures/england-championship-2025-2026",
        "extra_fixture_urls": [
            "https://www.whoscored.com/regions/252/tournaments/7/seasons/10784/stages/25405/fixtures/england-championship-2025-2026",
        ],
        "match_title_markers": [" - Championship 2025/2026 Live"],
        "id_scan_ranges": [(1908240, 1908800), (1979290, 1979940)],
    },
    "Primeira_Liga": {
        "display_name": "Liga Portugal",
        "country": "Portugal",
        "fixture_url": "https://www.whoscored.com/regions/177/tournaments/21/seasons/10774/stages/24568/fixtures/portugal-liga-portugal-2025-2026",
        "match_title_markers": [" - Liga Portugal 2025/2026 Live"],
        "id_scan_ranges": [(1915560, 1915875)],
    },
    "Eredivisie": {
        "display_name": "Eredivisie",
        "country": "Netherlands",
        "fixture_url": "https://www.whoscored.com/regions/155/tournaments/13/seasons/10752/stages/24542/fixtures/netherlands-eredivisie-2025-2026",
        "match_title_markers": [" - Eredivisie 2025/2026 Live"],
        "id_scan_ranges": [(1903733, 1904055)],
    },
    "Belgium_Pro_League": {
        "display_name": "Jupiler Pro League",
        "country": "Belgium",
        "fixture_url": "https://www.whoscored.com/regions/22/tournaments/18/seasons/10759/stages/24549/fixtures/belgium-jupiler-pro-league-2025-2026",
        "extra_fixture_urls": [
            "https://www.whoscored.com/regions/22/tournaments/18/seasons/10759/stages/25287/fixtures/belgium-jupiler-pro-league-2025-2026",
            "https://www.whoscored.com/regions/22/tournaments/18/seasons/10759/stages/25288/fixtures/belgium-jupiler-pro-league-2025-2026",
            "https://www.whoscored.com/regions/22/tournaments/18/seasons/10759/stages/25289/fixtures/belgium-jupiler-pro-league-2025-2026",
            "https://www.whoscored.com/regions/22/tournaments/18/seasons/10759/stages/25500/fixtures/belgium-jupiler-pro-league-2025-2026",
        ],
        "match_title_markers": [" - Jupiler Pro League 2025/2026 Live"],
        "id_scan_ranges": [(1904900, 1905140)],
    },
    "Super_Lig": {
        "display_name": "Super Lig",
        "country": "Turkey",
        "fixture_url": "https://www.whoscored.com/regions/225/tournaments/17/seasons/10807/stages/24627/fixtures/turchia-super-lig-2025-2026",
        "match_title_markers": [" - Super Lig 2025/2026 Live"],
        "id_scan_ranges": [(1915274, 1915579)],
    },
}

# ─── League Strength (ClubElo) ───────────────────────────────────────
# Cross-league scores are league-anchored: within-league percentiles are
# mapped to latent z-scores and shifted by a per-league strength offset
# before the global rerank (see src/features/merge_leagues.py).
#
# Offsets derive from ClubElo (http://clubelo.com): the mean club Elo of
# each league, fetched by src/enrichment/league_strength.py and cached in
# data/enrichment/clubelo_league_strength.csv (committed — the merge step
# never needs network access). Only *relative* offsets matter: the global
# rerank cancels any constant, so ELO_PER_SIGMA is the single tuning knob.
#
# ClubElo identifies leagues by (country_code, level); level 2 = second
# tier (e.g. the Championship).
LEAGUE_CLUBELO = {
    "Serie_A":            ("ITA", 1),
    "Premier_League":     ("ENG", 1),
    "La_Liga":            ("ESP", 1),
    "Bundesliga":         ("GER", 1),
    "Ligue_1":            ("FRA", 1),
    "Championship":       ("ENG", 2),
    "Primeira_Liga":      ("POR", 1),
    "Eredivisie":         ("NED", 1),
    "Belgium_Pro_League": ("BEL", 1),
    "Super_Lig":          ("TUR", 1),
}
ELO_PER_SIGMA = 270.0                  # Elo points per 1 SD of player-quality offset
CLUBELO_SNAPSHOT_DATE = "2026-05-01"   # end of season; update alongside fixture_urls
LEAGUE_STRENGTH_OFFSET_COL = "league_strength_offset"

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

# ─── Player Filters & Sample Reliability ─────────────────────────────
# Players with at least MIN_MINUTES_INCLUDED in a position group are visible
# in the dataset. FULL_SAMPLE_MINUTES is the old qualification threshold and
# now acts as the point where minutes carry full scoring confidence.
MIN_MINUTES_INCLUDED = 180
MIN_MINUTES_PLAYED = 600
FULL_SAMPLE_MINUTES = MIN_MINUTES_PLAYED
FULL_SAMPLE_APPEARANCES = 10
FULL_SAMPLE_STARTS = 6
SCORE_NEUTRAL_POINT = 50.0
SAMPLE_RELIABILITY_COL = "sample_reliability"
SCORE_CONFIDENCE_COL = "score_confidence"
SAMPLE_TIER_COL = "sample_tier"
SAMPLE_RELIABILITY_WEIGHTS = {
    "minutes": 0.65,
    "appearances": 0.15,
    "starts": 0.15,
    "start_rate": 0.05,
}
MAX_AGE = 40

# Rate metrics whose sample size is the contest count, not minutes played.
# Before percentile ranking, these are shrunk toward the pool-average rate
# with a Bayesian prior of `prior_strength` pseudo-contests, so a defender
# with 5 aerial duels can't post a 0% or 100% rate that outranks a player
# with 100 contests.
RATE_SHRINKAGE = {
    "aerial_win_rate": {
        "successes": "aerials_won",
        "attempts": "aerials_total",
        "prior_strength": 15,
    },
    "tackle_success_rate": {
        "successes": "tackles_successful",
        "attempts": "tackles",
        "prior_strength": 15,
    },
    "cross_accuracy": {
        "successes": "crosses_successful",
        "attempts": "crosses",
        "prior_strength": 15,
    },
    "dribble_success_rate": {
        "successes": "successful_dribbles",
        "attempts": "total_dribbles",
        "prior_strength": 15,
    },
}

# Possession adjustment (PAdj). Defensive volume depends on how often the
# opponent has the ball: a centre-back in a 65%-possession side gets far fewer
# chances to tackle or intercept than one in a 40%-possession side. Metrics
# listed here are rescaled to a 50% opponent-possession baseline before
# percentile ranking (rank sources only — displayed raw columns are untouched).
# Opponent share is derived per match from teams.csv pass counts and averaged
# per player weighted by minutes actually played.
# Only metrics whose volume scales with OPPONENT possession belong here.
# ball_recoveries and possession_won_final_third correlate NEGATIVELY with
# opponent possession (they scale with your own team's press), so adjusting
# them would double-reward dominant-team players — keep them out.
PADJ_OPPONENT_SHARE_COL = "opp_possession_share"
PADJ_BASELINE = 0.5
PADJ_OPP_SHARE_CLIP = (0.25, 0.75)
PADJ_METRICS = {
    "DEF": (
        "tackles_p90",
        "tackles_successful_p90",
        "interceptions_p90",
        "shots_blocked_p90",
        "clearances_p90",
    ),
    "FB": (
        "tackles_p90",
        "tackles_successful_p90",
        "interceptions_p90",
        "def_actions_p90",
    ),
    "MID": (
        "tackles_p90",
        "tackles_successful_p90",
        "interceptions_p90",
        "def_actions_p90",
    ),
}

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

# ─── Role Scoring ─────────────────────────────────────────────────────
POSITION_GROUP_COL = "position_group"
OVERALL_SCORE_COL  = "overall_score"
ROLE_SCORE_COL_PREFIX = "role_score_"
PRIMARY_ROLE_COL      = "primary_role"

ZONE_META = {
    "Deep":     {"label": "Deep",     "color": "#06B6D4", "order": 1},
    "Dynamic":  {"label": "Dynamic",  "color": "#00C896", "order": 2},
    "Advanced": {"label": "Advanced", "color": "#F59E0B", "order": 3},
}

POSITION_GROUPS = {
    "DEF": {
        "display_name": "Defenders",
        "positions": ["DC"],
        "roles": {
            "Stopper": {
                # clearances_p90 removed: it correlates negatively with the
                # ball-winning core (deep-block volume, not proactive defending)
                # and already carries 25% of Aerial Dominator.
                "tackles_successful_p90": 0.25,
                "interceptions_p90": 0.25,
                "shots_blocked_p90": 0.20,
                "ball_recoveries_p90": 0.15,
                "tackle_success_rate": 0.15,
            },
            "Aerial Dominator": {
                "aerials_won_p90": 0.40,
                "aerial_win_rate": 0.35,
                "clearances_p90": 0.25,
            },
            "Ball-Playing Defender": {
                # passes_into_final_third is near-duplicate of progressive
                # passes (r=0.87) so it keeps only a residual weight; raw
                # long-ball volume is capped at 0.10 until an accurate-long-ball
                # split is aggregated (it rewards hoofing, r=-0.54 vs accuracy).
                "progressive_passes_p90": 0.35,
                "pass_accuracy": 0.20,
                "carries_into_final_third_p90": 0.15,
                "long_balls_p90": 0.10,
                "passes_into_final_third_p90": 0.10,
                "forward_pass_pct": 0.10,
            },
        },
        "role_colors": {
            "Stopper": "#EF4444",
            "Aerial Dominator": "#8B5CF6",
            "Ball-Playing Defender": "#06B6D4",
        },
        "role_descriptions": {
            "Stopper": "Wins defensive actions through tackles, interceptions, blocks, and recoveries.",
            "Aerial Dominator": "Controls aerial duels through high contest volume, win rate, and clearance output.",
            "Ball-Playing Defender": "Builds from the back through progressive passing and carrying with secure possession.",
        },
        "role_zones": {
            "Stopper": "Deep",
            "Aerial Dominator": "Deep",
            "Ball-Playing Defender": "Deep",
        },
        "radar_metrics": [
            "tackles_successful_p90",
            "interceptions_p90",
            "clearances_p90",
            "aerial_win_rate",
            "shots_blocked_p90",
            "progressive_passes_p90",
            "long_balls_p90",
            "pass_accuracy",
        ],
        "composite_weights": {
            "Stopper": 0.35,
            "Ball-Playing Defender": 0.35,
            "Aerial Dominator": 0.30,
        },
        "lenses": {
            "Stopper": {
                "x": "interceptions_p90",
                "y": "tackles_p90",
                "question": "Who wins the most defensive actions?",
                "elite_label": "High-volume stoppers",
            },
            "Aerial Dominator": {
                "x": "aerial_win_rate",
                "y": "aerials_won_p90",
                "question": "Who dominates aerial contests?",
                "elite_label": "Aerial leaders",
            },
            "Ball-Playing Defender": {
                "x": "pass_accuracy",
                "y": "progressive_passes_p90",
                "question": "Who progresses play from the back without losing security?",
                "elite_label": "Progressive builders",
            },
        },
    },
    "FB": {
        "display_name": "Fullbacks",
        "positions": ["DL", "DR", "DML", "DMR"],
        "roles": {
            "Defensive Fullback": {
                # clearances_p90 removed: deep-block volume that correlates
                # negatively with the channel-defending core (same issue as
                # the DEF Stopper fix).
                "tackles_successful_p90": 0.25,
                "interceptions_p90": 0.25,
                "ball_recoveries_p90": 0.20,
                "tackle_success_rate": 0.15,
                "possession_won_final_third_p90": 0.15,
            },
            "Attacking Fullback": {
                "carries_into_final_third_p90": 0.25,
                "crosses_p90": 0.25,
                "successful_dribbles_p90": 0.20,
                "touches_final_third_p90": 0.15,
                "passes_into_penalty_area_p90": 0.15,
            },
            "Inverted Fullback": {
                "progressive_passes_p90": 0.30,
                "pass_accuracy": 0.25,
                "total_passes_p90": 0.20,
                "forward_pass_pct": 0.15,
                "carries_into_final_third_p90": 0.10,
            },
            "Crossing Fullback": {
                "crosses_p90": 0.30,
                "cross_accuracy": 0.20,
                "key_passes_p90": 0.20,
                "passes_into_penalty_area_p90": 0.20,
                "assists_p90": 0.10,
            },
        },
        "role_colors": {
            "Defensive Fullback": "#22C55E",
            "Attacking Fullback": "#F59E0B",
            "Inverted Fullback": "#06B6D4",
            "Crossing Fullback": "#14B8A6",
        },
        "role_descriptions": {
            "Defensive Fullback": "Defends the channel, wins duels, recovers loose balls, and protects wide transitions.",
            "Attacking Fullback": "Provides width, carries forward, beats players, and reaches the final third.",
            "Inverted Fullback": "Builds play from deeper or inside lanes through secure, progressive passing.",
            "Crossing Fullback": "Creates from wide delivery, box entries, key passes, and accurate crossing.",
        },
        "role_zones": {
            "Defensive Fullback": "Deep",
            "Inverted Fullback": "Dynamic",
            "Attacking Fullback": "Dynamic",
            "Crossing Fullback": "Advanced",
        },
        "radar_metrics": [
            "tackles_successful_p90",
            "interceptions_p90",
            "progressive_passes_p90",
            "pass_accuracy",
            "carries_into_final_third_p90",
            "successful_dribbles_p90",
            "crosses_p90",
            "passes_into_penalty_area_p90",
        ],
        "composite_weights": {
            "Attacking Fullback": 0.30,
            "Defensive Fullback": 0.25,
            "Inverted Fullback": 0.25,
            "Crossing Fullback": 0.20,
        },
        "lenses": {
            "Defensive Fullback": {
                "x": "tackle_success_rate",
                "y": "def_actions_p90",
                "question": "Who protects wide zones most reliably?",
                "elite_label": "Defensive fullbacks",
            },
            "Attacking Fullback": {
                "x": "successful_dribbles_p90",
                "y": "carries_into_final_third_p90",
                "question": "Who carries the ball into dangerous wide areas?",
                "elite_label": "Dynamic fullbacks",
            },
            "Inverted Fullback": {
                "x": "pass_accuracy",
                "y": "progressive_passes_p90",
                "question": "Who builds from fullback zones with security and intent?",
                "elite_label": "Inverted builders",
            },
            "Crossing Fullback": {
                "x": "cross_accuracy",
                "y": "crosses_p90",
                "question": "Who creates most reliably from wide delivery?",
                "elite_label": "Wide delivery leaders",
            },
        },
    },
    "MID": {
        "display_name": "Midfielders",
        "positions": ["DMC", "MC", "AMC"],
        "roles": {
            "Creator": {
                # key_passes and passes_into_penalty_area are near-twins
                # (r=0.85); combined weight trimmed in favour of outcome
                # (assists) and incision (through balls).
                "key_passes_p90": 0.30,
                "assists_p90": 0.25,
                "passes_into_penalty_area_p90": 0.15,
                "through_balls_p90": 0.15,
                "crosses_p90": 0.15,
            },
            "Ball Progressor": {
                "carries_into_final_third_p90": 0.40,
                "successful_dribbles_p90": 0.30,
                "progressive_passes_p90": 0.20,
                "dribble_success_rate": 0.10,
            },
            "Box Threat": {
                "penalty_area_touches_p90": 0.35,
                "shots_p90": 0.30,
                "touches_final_third_p90": 0.15,
                "goals_p90": 0.10,
                "passes_into_penalty_area_p90": 0.10,
            },
            "Deep Builder": {
                # total_passes trimmed: near-twin of progressive_passes
                # (r=0.81) in this pool.
                "progressive_passes_p90": 0.35,
                "pass_accuracy": 0.25,
                "total_passes_p90": 0.15,
                "forward_pass_pct": 0.15,
                "key_passes_p90": 0.10,
            },
            "Ball Winner": {
                # Refocused on ball-winning volume: height metrics correlate
                # negatively with deep defensive volume (two archetypes were
                # fighting inside one score), so they keep only residual weight.
                "def_actions_p90": 0.35,
                "ball_recoveries_p90": 0.25,
                "tackle_success_rate": 0.20,
                "possession_won_final_third_p90": 0.10,
                "ball_winning_height": 0.10,
            },
        },
        "role_colors": {
            "Creator": "#0095FF",
            "Ball Progressor": "#00C896",
            "Box Threat": "#FF5252",
            "Deep Builder": "#FF9800",
            "Ball Winner": "#22C55E",
        },
        "role_descriptions": {
            "Creator": "Delivers the ball into dangerous areas through key passes, through balls, crosses, or cut-backs.",
            "Ball Progressor": "Drives the team forward through carrying, dribbling, and progressive actions.",
            "Box Threat": "Arrives in the penalty area, shoots often, and creates from proximity.",
            "Deep Builder": "Controls tempo through high-volume, accurate, forward-oriented passing.",
            "Ball Winner": "Recovers possession, disrupts opposition attacks, and wins the ball high enough to sustain pressure.",
        },
        "role_zones": {
            "Deep Builder": "Deep",
            "Ball Winner": "Deep",
            "Ball Progressor": "Dynamic",
            "Creator": "Advanced",
            "Box Threat": "Advanced",
        },
        "radar_metrics": [
            "passes_into_penalty_area_p90",
            "key_passes_p90",
            "def_actions_p90",
            "carries_into_final_third_p90",
            "successful_dribbles_p90",
            "penalty_area_touches_p90",
            "shots_p90",
            "progressive_passes_p90",
        ],
        "composite_weights": {
            "Creator": 0.30,
            "Ball Progressor": 0.20,
            "Box Threat": 0.20,
            "Deep Builder": 0.15,
            "Ball Winner": 0.15,
        },
        "lenses": {
            "Creator": {
                "x": "key_passes_p90",
                "y": "passes_into_penalty_area_p90",
                "question": "Who creates the most dangerous chances?",
                "elite_label": "Prolific creators",
            },
            "Ball Progressor": {
                "x": "successful_dribbles_p90",
                "y": "carries_into_final_third_p90",
                "question": "Who drives the team forward with the ball?",
                "elite_label": "Direct progressors",
            },
            "Box Threat": {
                "x": "shots_p90",
                "y": "penalty_area_touches_p90",
                "question": "Who lives in the box and creates direct goal threat?",
                "elite_label": "Box threats",
            },
            "Deep Builder": {
                "x": "progressive_passes_p90",
                "y": "pass_accuracy",
                "question": "Who builds from deep with accuracy and intent?",
                "elite_label": "Reliable builders",
            },
            "Ball Winner": {
                "x": "tackle_success_rate",
                "y": "def_actions_p90",
                "question": "Who wins the ball reliably and often?",
                "elite_label": "Ball winners",
            },
        },
    },
    "WING": {
        "display_name": "Wingers",
        "positions": ["ML", "MR", "AML", "AMR", "FWL", "FWR"],
        "roles": {
            "Touchline Winger": {
                "crosses_p90": 0.25,
                "carries_into_final_third_p90": 0.25,
                "successful_dribbles_p90": 0.20,
                "passes_into_penalty_area_p90": 0.15,
                "touches_final_third_p90": 0.15,
            },
            "Inside Forward": {
                "goals_p90": 0.25,
                "shots_p90": 0.25,
                "penalty_area_touches_p90": 0.25,
                "successful_dribbles_p90": 0.15,
                "key_passes_p90": 0.10,
            },
            "Wide Creator": {
                "key_passes_p90": 0.30,
                "assists_p90": 0.25,
                "shot_creating_actions_p90": 0.20,
                "crosses_p90": 0.15,
                "through_balls_p90": 0.10,
            },
            "Pressing Winger": {
                "possession_won_final_third_p90": 0.35,
                "ball_winning_height": 0.20,
                "ball_recoveries_p90": 0.20,
                "tackles_successful_p90": 0.15,
                "tackle_success_rate": 0.10,
            },
        },
        "role_colors": {
            "Touchline Winger": "#14B8A6",
            "Inside Forward": "#E11D48",
            "Wide Creator": "#3B82F6",
            "Pressing Winger": "#F97316",
        },
        "role_descriptions": {
            "Touchline Winger": "Holds width, beats opponents, carries forward, and delivers into the box.",
            "Inside Forward": "Attacks the box from wide zones through shots, goals, dribbles, and penalty-area touches.",
            "Wide Creator": "Creates chances from wide or half-space zones through key passes, assists, and final balls.",
            "Pressing Winger": "Presses aggressively from wide areas and wins the ball high up the pitch.",
        },
        "role_zones": {
            "Touchline Winger": "Dynamic",
            "Pressing Winger": "Dynamic",
            "Inside Forward": "Advanced",
            "Wide Creator": "Advanced",
        },
        "radar_metrics": [
            "goals_p90",
            "shots_p90",
            "key_passes_p90",
            "assists_p90",
            "successful_dribbles_p90",
            "carries_into_final_third_p90",
            "crosses_p90",
            "possession_won_final_third_p90",
        ],
        "composite_weights": {
            "Inside Forward": 0.30,
            "Touchline Winger": 0.25,
            "Wide Creator": 0.25,
            "Pressing Winger": 0.20,
        },
        "lenses": {
            "Touchline Winger": {
                "x": "successful_dribbles_p90",
                "y": "crosses_p90",
                "question": "Who beats players and delivers from wide?",
                "elite_label": "Touchline threats",
            },
            "Inside Forward": {
                "x": "shots_p90",
                "y": "penalty_area_touches_p90",
                "question": "Who attacks the box from wide zones?",
                "elite_label": "Inside forwards",
            },
            "Wide Creator": {
                "x": "key_passes_p90",
                "y": "shot_creating_actions_p90",
                "question": "Who creates the most from wide and half-space zones?",
                "elite_label": "Wide creators",
            },
            "Pressing Winger": {
                "x": "ball_winning_height",
                "y": "possession_won_final_third_p90",
                "question": "Who presses and wins it highest from wide?",
                "elite_label": "Pressing wingers",
            },
        },
    },
    "FW": {
        "display_name": "Forwards",
        "positions": ["FW"],
        "roles": {
            "Finisher": {
                "goals_p90": 0.35,
                "penalty_area_touches_p90": 0.30,
                "shots_p90": 0.25,
                "touches_final_third_p90": 0.10,
            },
            "Target Man": {
                # aerials_total dropped: r=0.91 twin of aerials_won. Mirrors
                # the DEF Aerial Dominator volume + rate + outcome design.
                "aerials_won_p90": 0.40,
                "aerial_win_rate": 0.30,
                "goals_p90": 0.15,
                "penalty_area_touches_p90": 0.15,
            },
            "Creative Forward": {
                # shot_creating_actions trimmed: it contains key passes by
                # construction (r=0.79 with key_passes here).
                "key_passes_p90": 0.30,
                "assists_p90": 0.25,
                "passes_into_penalty_area_p90": 0.20,
                "through_balls_p90": 0.15,
                "shot_creating_actions_p90": 0.10,
            },
            "Pressing Forward": {
                "possession_won_final_third_p90": 0.35,
                "ball_winning_height": 0.25,
                "ball_recoveries_p90": 0.20,
                "tackles_p90": 0.20,
            },
        },
        "role_colors": {
            "Finisher": "#E11D48",
            "Target Man": "#A855F7",
            "Creative Forward": "#3B82F6",
            "Pressing Forward": "#F97316",
        },
        "role_descriptions": {
            "Finisher": "Converts box presence and shooting volume into goals.",
            "Target Man": "Provides aerial presence, penalty-area occupation, and a focal point for direct attacks.",
            "Creative Forward": "Links attacks and creates shots for teammates from advanced zones.",
            "Pressing Forward": "Defends from the front through high regains, recoveries, and active ball pressure.",
        },
        "role_zones": {
            "Target Man": "Advanced",
            "Finisher": "Advanced",
            "Creative Forward": "Advanced",
            "Pressing Forward": "Dynamic",
        },
        "radar_metrics": [
            "goals_p90",
            "shots_p90",
            "penalty_area_touches_p90",
            "key_passes_p90",
            "shot_creating_actions_p90",
            "aerials_won_p90",
            "aerial_win_rate",
            "possession_won_final_third_p90",
        ],
        "composite_weights": {
            "Finisher": 0.40,
            "Creative Forward": 0.25,
            "Target Man": 0.20,
            "Pressing Forward": 0.15,
        },
        "lenses": {
            "Finisher": {
                "x": "shots_p90",
                "y": "goals_p90",
                "question": "Who turns shooting volume into goals?",
                "elite_label": "Efficient finishers",
            },
            "Target Man": {
                "x": "aerial_win_rate",
                "y": "aerials_won_p90",
                "question": "Who gives the attack a reliable aerial focal point?",
                "elite_label": "Target forwards",
            },
            "Creative Forward": {
                "x": "key_passes_p90",
                "y": "shot_creating_actions_p90",
                "question": "Who creates shots from advanced positions?",
                "elite_label": "Creative forwards",
            },
            "Pressing Forward": {
                "x": "ball_winning_height",
                "y": "possession_won_final_third_p90",
                "question": "Who pressures and wins the ball highest?",
                "elite_label": "Pressing leaders",
            },
        },
    },
}

ALL_ROLE_WEIGHTS = {
    role: weights
    for group in POSITION_GROUPS.values()
    for role, weights in group["roles"].items()
}
ALL_ROLE_COLORS = {
    role: color
    for group in POSITION_GROUPS.values()
    for role, color in group["role_colors"].items()
}
ALL_ROLE_DESCRIPTIONS = {
    role: description
    for group in POSITION_GROUPS.values()
    for role, description in group["role_descriptions"].items()
}
POSITION_TO_GROUP = {
    position: group_key
    for group_key, group in POSITION_GROUPS.items()
    for position in group["positions"]
}


def _assert_weight_sum(name: str, weights: dict[str, float]) -> None:
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"{name} weights sum to {total}, expected 1.0")


def _validate_position_group_config() -> None:
    role_names = [
        role
        for group in POSITION_GROUPS.values()
        for role in group["roles"]
    ]
    if len(role_names) != len(set(role_names)):
        duplicates = sorted({role for role in role_names if role_names.count(role) > 1})
        raise ValueError(f"Role names must be globally unique: {duplicates}")

    position_names = [
        position
        for group in POSITION_GROUPS.values()
        for position in group["positions"]
    ]
    if len(position_names) != len(set(position_names)):
        duplicates = sorted({pos for pos in position_names if position_names.count(pos) > 1})
        raise ValueError(f"Positions can belong to only one group: {duplicates}")

    for group_key, group in POSITION_GROUPS.items():
        roles = set(group["roles"])
        if roles != set(group["role_colors"]):
            raise ValueError(f"{group_key} role_colors must match roles")
        if roles != set(group["role_descriptions"]):
            raise ValueError(f"{group_key} role_descriptions must match roles")
        if roles != set(group["role_zones"]):
            raise ValueError(f"{group_key} role_zones must match roles")
        if roles != set(group["composite_weights"]):
            raise ValueError(f"{group_key} composite_weights must match roles")
        for position, weights in group.get("position_composite_weights", {}).items():
            if position not in group["positions"]:
                raise ValueError(
                    f"{group_key}/{position} position_composite_weights uses unknown position"
                )
            if roles != set(weights):
                raise ValueError(
                    f"{group_key}/{position} position_composite_weights must match roles"
                )
            _assert_weight_sum(f"{group_key}/{position}/overall_score", weights)
        for role, zone in group["role_zones"].items():
            if zone not in ZONE_META:
                raise ValueError(f"{group_key}/{role} uses unknown zone '{zone}'")
        for role, weights in group["roles"].items():
            _assert_weight_sum(f"{group_key}/{role}", weights)
        _assert_weight_sum(f"{group_key}/overall_score", group["composite_weights"])


_validate_position_group_config()


def _validate_league_strength_config() -> None:
    if set(LEAGUE_CLUBELO) != set(LEAGUES):
        missing = sorted(set(LEAGUES) - set(LEAGUE_CLUBELO))
        extra = sorted(set(LEAGUE_CLUBELO) - set(LEAGUES))
        raise ValueError(
            f"LEAGUE_CLUBELO must cover exactly the LEAGUES keys "
            f"(missing: {missing}, extra: {extra})"
        )
    if ELO_PER_SIGMA <= 0:
        raise ValueError(f"ELO_PER_SIGMA must be positive, got {ELO_PER_SIGMA}")


_validate_league_strength_config()

# ─── Transfermarkt Enrichment ─────────────────────────────────────────
TM_CURRENT_SEASON_END_YEAR = int(SEASON.split("-")[1])   # e.g. 2026 from "2025-2026"

# Transfermarkt competition page URLs — one per configured league.
# Competition IDs are stable; only update if TM changes their URL structure.
TM_LEAGUE_URLS = {
    "Serie_A":       "https://www.transfermarkt.com/serie-a/startseite/wettbewerb/IT1",
    "Premier_League":"https://www.transfermarkt.com/premier-league/startseite/wettbewerb/GB1",
    "La_Liga":       "https://www.transfermarkt.com/laliga/startseite/wettbewerb/ES1",
    "Bundesliga":    "https://www.transfermarkt.com/bundesliga/startseite/wettbewerb/L1",
    "Ligue_1":       "https://www.transfermarkt.com/ligue-1/startseite/wettbewerb/FR1",
    "Championship":  "https://www.transfermarkt.com/championship/startseite/wettbewerb/GB2",
    "Primeira_Liga": "https://www.transfermarkt.com/liga-portugal/startseite/wettbewerb/PO1",
    "Eredivisie":    "https://www.transfermarkt.com/eredivisie/startseite/wettbewerb/NL1",
    "Belgium_Pro_League": "https://www.transfermarkt.com/jupiler-pro-league/startseite/wettbewerb/BE1",
    "Super_Lig":     "https://www.transfermarkt.com/super-lig/startseite/wettbewerb/TR1",
}
