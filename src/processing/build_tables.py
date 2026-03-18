"""
Build Tables
-------------
Reads per-match event CSVs produced by the extractor and aggregates
them into three normalized tables:

    - matches.csv:   match-level metadata (date, teams, score)
    - players.csv:   player-level stats per match (derived from events)
    - teams.csv:     team-level stats per match (derived from events)

Output is written to data/processed/{league}/{season}/.
A `league` column is added to every table for downstream merging.

Usage:
    python -m src.processing.build_tables --league Serie_A --season 2025-2026
    python -m src.processing.build_tables --league Premier_League --season 2025-2026
"""

import ast
import os
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

import config


# ─── WhoScored qualifier displayName constants ────────────────────────
# Casing is exactly as returned by WhoScored — do NOT normalize.
# Tests in tests/test_build_tables.py guard these as regression fixtures.
_Q_KEY_PASS          = "KeyPass"
_Q_INTENTIONAL_ASSIST = "IntentionalAssist"
_Q_THROUGH_BALL      = "Throughball"       # NOT "ThroughBall"
_Q_LONG_BALL         = "Longball"          # NOT "LongBall"
_Q_CROSS             = "Cross"


# ─── Qualifier Helpers ────────────────────────────────────────────────

def parse_qualifiers(qual_str):
    """
    Parse the qualifiers column from a string representation to a list of dicts.
    WhoScored qualifiers look like: [{'type': {'displayName': 'Zone', 'value': 79}, 'value': 'Right'}, ...]
    """
    if pd.isna(qual_str) or qual_str == "[]":
        return []

    try:
        # Try literal eval first (handles Python-style dicts in CSV)
        quals = ast.literal_eval(str(qual_str))
        if isinstance(quals, list):
            return quals
    except (ValueError, SyntaxError):
        pass

    return []


def has_qualifier(qualifiers: list, qualifier_display_name: str) -> bool:
    """Check if a specific qualifier exists by displayName."""
    for q in qualifiers:
        q_type = q.get("type", {})
        if isinstance(q_type, dict) and q_type.get("displayName") == qualifier_display_name:
            return True
    return False


def get_qualifier_value(qualifiers: list, qualifier_display_name: str):
    """Get the value of a specific qualifier by displayName."""
    for q in qualifiers:
        q_type = q.get("type", {})
        if isinstance(q_type, dict) and q_type.get("displayName") == qualifier_display_name:
            return q.get("value")
    return None


# ─── Event-Level Feature Extraction ──────────────────────────────────

def enrich_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add boolean columns to each event row for easier aggregation.
    This is where we translate WhoScored event types + qualifiers
    into the stats we care about.
    """
    df = df.copy()

    # Parse qualifiers once
    if "qualifiers" in df.columns:
        df["_quals"] = df["qualifiers"].apply(parse_qualifiers)
    else:
        df["_quals"] = [[] for _ in range(len(df))]

    # ── Event type flags ──
    df["is_pass"] = df["type"] == "Pass"
    df["is_take_on"] = df["type"] == "TakeOn"
    df["is_shot"] = df["type"].isin(["MissedShots", "SavedShot", "ShotOnPost", "Goal"])
    df["is_goal"] = df["type"] == "Goal"
    df["is_tackle"] = df["type"] == "Tackle"
    df["is_interception"] = df["type"] == "Interception"
    df["is_clearance"] = df["type"] == "Clearance"
    df["is_aerial"] = df["type"] == "Aerial"
    df["is_ball_recovery"] = df["type"] == "BallRecovery"
    df["is_carry"] = df["type"] == "Carry"  # if WhoScored includes carries
    df["is_blocked_pass"] = df["type"] == "BlockedPass"

    # ── Outcome flags ──
    df["is_successful"] = df["outcomeType"] == "Successful"

    # ── Qualifier-based flags (chance creation) ──
    df["is_key_pass"] = df["_quals"].apply(lambda q: has_qualifier(q, _Q_KEY_PASS))

    # Assist detection via satisfiedEventsTypes (event-type ID 92 = goal scored on this action).
    # WhoScored's IntentionalAssist qualifier is NOT used for assists because:
    #   1. It appears on ALL key passes (passes leading to any shot, not just goals) — so
    #      IntentionalAssist ≈ KeyPass and would inflate assists to match key-pass counts.
    #   2. It also appears on the resulting shot/goal event, causing double-counting.
    # Event-type 92 in satisfiedEventsTypes is present only on pass events that directly
    # led to a goal, making it the correct signal for actual assists.
    # Fallback to qualifier-based approach when satisfiedEventsTypes is absent (e.g. in tests).
    if "satisfiedEventsTypes" in df.columns:
        def _sat_set(val):
            try:
                parsed = ast.literal_eval(str(val))
                return set(int(x) for x in parsed) if isinstance(parsed, list) else set()
            except Exception:
                return set()
        df["_sat"] = df["satisfiedEventsTypes"].apply(_sat_set)
        df["is_assist"] = df["is_pass"] & df["_sat"].apply(lambda s: 92 in s)
    else:
        df["is_assist"] = df["is_pass"] & df["_quals"].apply(
            lambda q: has_qualifier(q, _Q_INTENTIONAL_ASSIST)
        )

    df["is_through_ball"] = df["_quals"].apply(lambda q: has_qualifier(q, _Q_THROUGH_BALL))
    df["is_long_ball"]    = df["_quals"].apply(lambda q: has_qualifier(q, _Q_LONG_BALL))
    df["is_cross"]        = df["_quals"].apply(lambda q: has_qualifier(q, _Q_CROSS))

    # ── Spatial flags (using x, y coordinates if available) ──
    # WhoScored uses a 0-100 coordinate system (x=0 own goal line, x=100 opp goal line)
    if "x" in df.columns and "endX" in df.columns:
        # Progressive pass: moves ball at least 25% closer to goal
        # (only for successful passes)
        df["is_progressive_pass"] = (
            df["is_pass"]
            & df["is_successful"]
            & ((100 - df["endX"]) <= 0.75 * (100 - df["x"]))
        )

        # Pass into final third (endX >= 66.7)
        df["is_pass_into_final_third"] = (
            df["is_pass"]
            & df["is_successful"]
            & (df["x"] < 66.7)
            & (df["endX"] >= 66.7)
        )

        # Pass into penalty area (endX >= 83 and 21 <= endY <= 79 approximately)
        df["is_pass_into_penalty_area"] = (
            df["is_pass"]
            & df["is_successful"]
            & (df["endX"] >= 83)
            & (df["endY"] >= 21.1)
            & (df["endY"] <= 78.9)
        )

        # Progressive carry — inferred from sequential per-player events (same carry
        # detection approach as is_carry_into_final_third).  A carry is progressive if
        # the inferred end position is at least 25% closer to goal than the start.
        # We approximate end position as the next event's x when it's a forward move.
        df["is_progressive_carry"] = False  # placeholder; overwritten below if possible

        # Forward pass: successful pass that advances toward the opponent's goal
        df["is_forward_pass"] = (
            df["is_pass"]
            & df["is_successful"]
            & (df["endX"] > df["x"])
        )

        # Penalty area touch: any event occurring inside the attacking penalty area
        df["is_penalty_area_touch"] = (
            (df["x"] >= 83)
            & (df["y"] >= 21.1)
            & (df["y"] <= 78.9)
        )

        # Half-space pass: successful pass ending in the attacking half-spaces
        # (final third but outside the central lane and penalty area width)
        df["is_half_space_pass"] = (
            df["is_pass"]
            & df["is_successful"]
            & (df["endX"] >= 66)
            & ((df["endY"] < 37) | (df["endY"] > 63))
        )

        # Possession won in the final third: ball recovery in the attacking third
        df["is_possession_won_final_third"] = (
            df["is_ball_recovery"]
            & (df["x"] >= 66.7)
        )

        # Carry into the final third — inferred from sequential per-player events.
        # WhoScored does not log Carry events; we detect carries by noticing when a
        # player's event starts inside the final third (x >= 66.7) while their previous
        # event ended outside it (x < 66.7), with a gap <= 30 units (consistent with a
        # carry, not a long-pass reception), AND where the previous event indicates the
        # player retained possession (BallTouch, BallRecovery, or a successful
        # TakeOn / Interception / Tackle — all events after which the player has the ball).
        # Successful passes are explicitly excluded: after passing, the player no longer
        # has the ball and the next event inside the final third is a new reception.
        _carry_cols = ["playerId", "x", "endX", "type", "outcomeType"]
        _temporal   = [c for c in ["period", "minute", "second"] if c in df.columns]
        if _temporal and "playerId" in df.columns:
            _s = df[_carry_cols + _temporal].copy()
            _s["_end_x"] = np.where(_s["endX"].notna(), _s["endX"], _s["x"])
            _s = _s.sort_values(["playerId"] + _temporal)
            _s["_prev_end_x"]  = _s.groupby("playerId")["_end_x"].shift(1)
            _s["_prev_type"]   = _s.groupby("playerId")["type"].shift(1)
            _s["_prev_outcome"]= _s.groupby("playerId")["outcomeType"].shift(1)
            if "period" in _temporal:
                _s["_prev_period"] = _s.groupby("playerId")["period"].shift(1)
                _same_period = _s["_prev_period"] == _s["period"]
            else:
                _same_period = True
            _prev_kept_ball = (
                _s["_prev_type"].isin(["BallTouch", "BallRecovery"])
                | ((_s["_prev_type"] == "TakeOn")       & (_s["_prev_outcome"] == "Successful"))
                | ((_s["_prev_type"] == "Interception") & (_s["_prev_outcome"] == "Successful"))
                | ((_s["_prev_type"] == "Tackle")       & (_s["_prev_outcome"] == "Successful"))
            )
            _carry_mask = (
                _s["_prev_end_x"].notna()
                & _same_period
                & (_s["_prev_end_x"] < 66.7)
                & (_s["x"] >= 66.7)
                & ((_s["x"] - _s["_prev_end_x"]).between(0, 30))
                & _prev_kept_ball
            )
            df["is_carry_into_final_third"] = _carry_mask.reindex(df.index, fill_value=False)
        else:
            df["is_carry_into_final_third"] = False

        # Ball-winning height accumulators: sum x and count for interceptions + recoveries
        # Used to compute average ball-winning height in feature engineering
        df["ball_winning_x_contrib"] = np.where(
            df["is_interception"] | df["is_ball_recovery"],
            df["x"].astype(float),
            0.0,
        )
        df["ball_winning_count"] = (
            (df["is_interception"] | df["is_ball_recovery"]).astype(int)
        )
    else:
        # Without coordinates, these will be zero
        df["is_progressive_pass"] = False
        df["is_pass_into_final_third"] = False
        df["is_pass_into_penalty_area"] = False
        df["is_progressive_carry"] = False
        df["is_forward_pass"] = False
        df["is_penalty_area_touch"] = False
        df["is_half_space_pass"] = False
        df["is_possession_won_final_third"] = False
        df["is_carry_into_final_third"] = False
        df["ball_winning_x_contrib"] = 0.0
        df["ball_winning_count"] = 0

    # ── Shot-creating action (SCA) ──
    # Simplified: key pass or successful take-on that precedes a shot
    # For now, use key_pass + successful dribble as proxy
    df["is_shot_creating_action"] = (
        df["is_key_pass"] | (df["is_take_on"] & df["is_successful"])
    )

    # ── Touches in final third ──
    if "x" in df.columns:
        df["is_touch_final_third"] = (
            (df.get("isTouch", False) == True) & (df["x"] >= 66.7)
        )
    else:
        df["is_touch_final_third"] = False

    return df


# ─── Aggregation: Player Stats Per Match ─────────────────────────────

def aggregate_player_match_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate event-level data to one row per player per match.
    """
    if "playerId" not in df.columns:
        return pd.DataFrame()

    # Drop events without a player (e.g., referee events)
    player_events = df[df["playerId"].notna()].copy()

    agg = player_events.groupby(["playerId", "teamId"]).agg(
        # ── Passing ──
        total_passes=("is_pass", "sum"),
        accurate_passes=pd.NamedAgg(
            column="is_pass",
            aggfunc=lambda s: ((player_events.loc[s.index, "is_pass"]) &
                               (player_events.loc[s.index, "is_successful"])).sum()
        ),
        key_passes=("is_key_pass", "sum"),
        through_balls=("is_through_ball", "sum"),
        long_balls=("is_long_ball", "sum"),
        crosses=("is_cross", "sum"),
        progressive_passes=("is_progressive_pass", "sum"),
        passes_into_final_third=("is_pass_into_final_third", "sum"),
        passes_into_penalty_area=("is_pass_into_penalty_area", "sum"),

        # ── Chance creation ──
        assists=("is_assist", "sum"),
        shot_creating_actions=("is_shot_creating_action", "sum"),

        # ── Dribbling ──
        successful_dribbles=pd.NamedAgg(
            column="is_take_on",
            aggfunc=lambda s: ((player_events.loc[s.index, "is_take_on"]) &
                               (player_events.loc[s.index, "is_successful"])).sum()
        ),
        total_dribbles=("is_take_on", "sum"),

        # ── Carrying ──
        progressive_carries=("is_progressive_carry", "sum"),

        # ── Shooting ──
        shots=("is_shot", "sum"),
        goals=("is_goal", "sum"),

        # ── Defensive ──
        tackles=("is_tackle", "sum"),
        interceptions=("is_interception", "sum"),
        ball_recoveries=("is_ball_recovery", "sum"),
        clearances=("is_clearance", "sum"),
        aerials_won=pd.NamedAgg(
            column="is_aerial",
            aggfunc=lambda s: ((player_events.loc[s.index, "is_aerial"]) &
                               (player_events.loc[s.index, "is_successful"])).sum()
        ),

        # ── Touches ──
        touches=("isTouch", "sum") if "isTouch" in player_events.columns else ("is_pass", lambda x: 0),
        touches_final_third=("is_touch_final_third", "sum"),
    ).reset_index()

    return agg


def aggregate_player_match_stats_simple(df: pd.DataFrame) -> pd.DataFrame:
    """
    Simpler, more robust aggregation using direct boolean column sums.
    Avoids complex lambda NamedAgg patterns that can be fragile.
    """
    if "playerId" not in df.columns:
        return pd.DataFrame()

    player_events = df[df["playerId"].notna()].copy()

    # Pre-compute combined columns
    player_events["accurate_pass"] = player_events["is_pass"] & player_events["is_successful"]
    player_events["successful_dribble"] = player_events["is_take_on"] & player_events["is_successful"]
    player_events["aerial_won"] = player_events["is_aerial"] & player_events["is_successful"]
    player_events["successful_tackle"] = player_events["is_tackle"] & player_events["is_successful"]
    player_events["successful_cross"] = player_events["is_cross"] & player_events["is_successful"]
    player_events["possession_lost"] = (
        (player_events["is_pass"] & ~player_events["is_successful"]) |
        (player_events["is_take_on"] & ~player_events["is_successful"])
    )

    sum_cols = {
        "is_pass": "total_passes",
        "accurate_pass": "accurate_passes",
        "is_key_pass": "key_passes",
        "is_through_ball": "through_balls",
        "is_long_ball": "long_balls",
        "is_cross": "crosses",
        "successful_cross": "crosses_successful",
        "is_progressive_pass": "progressive_passes",
        "is_pass_into_final_third": "passes_into_final_third",
        "is_pass_into_penalty_area": "passes_into_penalty_area",
        "is_assist": "assists",
        "is_shot_creating_action": "shot_creating_actions",
        "successful_dribble": "successful_dribbles",
        "is_take_on": "total_dribbles",
        "is_progressive_carry": "progressive_carries",
        "is_shot": "shots",
        "is_goal": "goals",
        "is_tackle": "tackles",
        "successful_tackle": "tackles_successful",
        "is_interception": "interceptions",
        "is_ball_recovery": "ball_recoveries",
        "is_clearance": "clearances",
        "is_aerial": "aerials_total",
        "aerial_won": "aerials_won",
        "is_blocked_pass": "shots_blocked",
        "possession_lost": "possession_lost",
        "is_touch_final_third": "touches_final_third",
        # ── New spatial metrics ──
        "is_forward_pass": "forward_passes",
        "is_penalty_area_touch": "penalty_area_touches",
        "is_half_space_pass": "half_space_passes",
        "is_possession_won_final_third": "possession_won_final_third",
        "is_carry_into_final_third": "carries_into_final_third",
        "ball_winning_x_contrib": "ball_winning_x_sum",
        "ball_winning_count": "ball_winning_count",
    }

    # Add touches if available
    if "isTouch" in player_events.columns:
        player_events["_touch"] = player_events["isTouch"].fillna(False).astype(bool)
        sum_cols["_touch"] = "touches"

    # Only use columns that exist
    available = {k: v for k, v in sum_cols.items() if k in player_events.columns}

    agg = (
        player_events
        .groupby(["playerId", "teamId"])
        [list(available.keys())]
        .sum()
        .rename(columns=available)
        .reset_index()
    )

    return agg


# ─── Load and Process a Single Match CSV ─────────────────────────────

def process_match_csv(filepath: Path) -> tuple[dict, pd.DataFrame, dict]:
    """
    Process a single event CSV into match info, player stats, and team stats.

    Returns:
        match_info (dict), player_stats (DataFrame), team_info (dict pair)
    """
    df = pd.read_csv(filepath, low_memory=False)

    # Extract match metadata from filename: DDMMYYYY_matchid.csv
    stem = filepath.stem
    parts = stem.split("_")
    date_str = parts[0] if len(parts) >= 2 else "unknown"
    match_id = parts[-1] if len(parts) >= 2 else stem

    # Get team info
    home_team = None
    away_team = None
    if "teamName" in df.columns and "teamId" in df.columns:
        team_map = df[["teamId", "teamName"]].drop_duplicates()
        teams = team_map.to_dict("records")
        if len(teams) >= 2:
            home_team = teams[0]
            away_team = teams[1]
        elif len(teams) == 1:
            home_team = teams[0]

    # Count goals per team
    goals = df[df["type"] == "Goal"].groupby("teamId").size().to_dict() if "type" in df.columns else {}

    match_info = {
        "match_id": match_id,
        "date_str": date_str,
        "home_team_id": home_team["teamId"] if home_team else None,
        "home_team_name": home_team["teamName"] if home_team else None,
        "away_team_id": away_team["teamId"] if away_team else None,
        "away_team_name": away_team["teamName"] if away_team else None,
        "home_score": goals.get(home_team["teamId"], 0) if home_team else None,
        "away_score": goals.get(away_team["teamId"], 0) if away_team else None,
        "total_events": len(df),
    }

    # Enrich events with derived flags
    df = enrich_events(df)

    # Aggregate player stats
    player_stats = aggregate_player_match_stats_simple(df)
    player_stats["match_id"] = match_id

    # Add player names (from the first event per player — WhoScored
    # doesn't always include playerName; adjust if your data has it)
    # If your CSV has a 'playerName' column:
    if "playerName" in df.columns:
        name_map = (
            df[df["playerName"].notna()]
            .groupby("playerId")["playerName"]
            .first()
        )
        player_stats = player_stats.merge(
            name_map.reset_index(), on="playerId", how="left"
        )

    # Add team names
    if "teamName" in df.columns:
        team_name_map = (
            df[df["teamName"].notna()]
            .groupby("teamId")["teamName"]
            .first()
        )
        player_stats = player_stats.merge(
            team_name_map.reset_index(), on="teamId", how="left"
        )

    # ── Merge player metadata (position, age, minutes) if available ──
    players_dir = filepath.parent / "players"
    player_meta_file = players_dir / f"{filepath.stem}_players.csv"

    if player_meta_file.exists():
        meta = pd.read_csv(player_meta_file)
        meta_cols = ["playerId", "position", "age", "minutes_played",
                     "isFirstEleven", "height", "weight", "rating"]
        available_meta = [c for c in meta_cols if c in meta.columns]
        player_stats = player_stats.merge(
            meta[available_meta], on="playerId", how="left"
        )
        if "minutes_played" in player_stats.columns:
            player_stats["minutes_played"] = player_stats["minutes_played"].clip(lower=0)
        # If playerName wasn't in events, get it from metadata
        if "playerName" not in player_stats.columns and "playerName" in meta.columns:
            name_from_meta = meta[["playerId", "playerName"]].drop_duplicates()
            player_stats = player_stats.merge(
                name_from_meta, on="playerId", how="left"
            )
    else:
        # No metadata file — downstream will need to handle missing columns
        pass

    # Team-level stats
    team_stats = []
    for team in [home_team, away_team]:
        if team is None:
            continue
        team_events = df[df["teamId"] == team["teamId"]]
        team_stats.append({
            "match_id": match_id,
            "team_id": team["teamId"],
            "team_name": team["teamName"],
            "is_home": team == home_team,
            "total_passes": team_events["is_pass"].sum(),
            "accurate_passes": (team_events["is_pass"] & team_events["is_successful"]).sum(),
            "total_shots": team_events["is_shot"].sum(),
            "goals": team_events["is_goal"].sum(),
            "key_passes": team_events["is_key_pass"].sum(),
            "tackles": team_events["is_tackle"].sum(),
            "interceptions": team_events["is_interception"].sum(),
        })

    return match_info, player_stats, team_stats


# ─── CLI ─────────────────────────────────────────────────────────────

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Build player/match/team tables from WhoScored event CSVs"
    )
    parser.add_argument(
        "--league", default=config.LEAGUE,
        choices=list(config.LEAGUES.keys()) + ["all"],
        help="League key (default: %(default)s) or 'all' to build tables for every league sequentially"
    )
    parser.add_argument(
        "--season", default=config.SEASON,
        help="Season string, e.g. 2025-2026 (default: %(default)s)"
    )
    return parser.parse_args()


# ─── Main Build Pipeline ─────────────────────────────────────────────

def build_all_tables(league: str = config.LEAGUE, season: str = config.SEASON):
    """
    Read all event CSVs → aggregate → save matches.csv, players.csv, teams.csv
    Output path: data/processed/{league}/{season}/
    All tables include a `league` column.
    """
    event_dir = config.get_events_path(league, season)
    csv_files = sorted(event_dir.glob("*.csv")) if event_dir.exists() else []

    print(f"League: {league}  Season: {season}")
    print(f"Found {len(csv_files)} event CSVs in {event_dir}")

    if not csv_files:
        print("No event data found. Run the extractor first:")
        print(f"  python -m src.scraper.whoscored_extractor --league {league} --season {season} --manifest")
        return

    all_matches = []
    all_players = []
    all_teams = []

    for filepath in tqdm(csv_files, desc="Building tables"):
        try:
            match_info, player_stats, team_stats = process_match_csv(filepath)
            all_matches.append(match_info)
            all_players.append(player_stats)
            all_teams.extend(team_stats)
        except Exception as e:
            print(f"\n  [!] Error processing {filepath.name}: {e}")
            continue

    # Combine
    df_matches = pd.DataFrame(all_matches)
    df_players = pd.concat(all_players, ignore_index=True) if all_players else pd.DataFrame()
    df_teams = pd.DataFrame(all_teams)

    # Standardize column names to snake_case for downstream modules
    if not df_players.empty:
        df_players.rename(columns={
            "playerId": "player_id",
            "teamId": "team_id",
            "playerName": "player_name",
            "teamName": "team_name",
        }, inplace=True)

    # Add league column to all tables
    for df in [df_matches, df_players, df_teams]:
        if not df.empty:
            df.insert(0, "league", league)

    # Save to league/season subdirectory
    out_dir = config.get_processed_path(league, season)
    out_dir.mkdir(parents=True, exist_ok=True)

    df_matches.to_csv(out_dir / "matches.csv", index=False)
    df_players.to_csv(out_dir / "players.csv", index=False)
    df_teams.to_csv(out_dir / "teams.csv", index=False)

    print(f"\nTables saved to {out_dir}/")
    print(f"  matches: {len(df_matches)} rows")
    print(f"  players: {len(df_players)} rows")
    print(f"  teams:   {len(df_teams)} rows")

    if not df_players.empty:
        print(f"\n  Unique players: {df_players['player_id'].nunique()}")
        print(f"  Sample columns: {list(df_players.columns[:10])}")


if __name__ == "__main__":
    args = parse_arguments()
    if args.league == "all":
        leagues = list(config.LEAGUES.keys())
        print(f"Building tables for all {len(leagues)} leagues: {', '.join(leagues)}\n")
        for league in leagues:
            build_all_tables(league=league, season=args.season)
            print()
        print("All leagues done.")
    else:
        build_all_tables(league=args.league, season=args.season)
