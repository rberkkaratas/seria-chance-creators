"""
Build Tables
-------------
Reads per-match event CSVs produced by the extractor and aggregates
them into three normalized tables:

    - matches.csv:   match-level metadata (date, teams, score)
    - players.csv:   player-level stats per match (derived from events)
    - teams.csv:     team-level stats per match (derived from events)

The key challenge: WhoScored event data stores everything as individual
events with qualifiers. Stats like "key passes" or "through balls" are
NOT pre-aggregated — we derive them by counting events + qualifiers.

Usage:
    python -m src.processing.build_tables
"""

import ast
import os
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

import config


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

    # ── Outcome flags ──
    df["is_successful"] = df["outcomeType"] == "Successful"

    # ── Qualifier-based flags (chance creation) ──
    df["is_key_pass"] = df["_quals"].apply(lambda q: has_qualifier(q, "KeyPass"))
    df["is_assist"] = df["_quals"].apply(lambda q: has_qualifier(q, "IntentionalAssist"))
    df["is_through_ball"] = df["_quals"].apply(lambda q: has_qualifier(q, "Throughball"))
    df["is_long_ball"] = df["_quals"].apply(lambda q: has_qualifier(q, "Longball"))
    df["is_cross"] = df["_quals"].apply(lambda q: has_qualifier(q, "Cross"))

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

        # Progressive carry (same logic for carries if available)
        df["is_progressive_carry"] = (
            df["is_carry"]
            & ((100 - df["endX"]) <= 0.75 * (100 - df["x"]))
        )
    else:
        # Without coordinates, these will be zero
        df["is_progressive_pass"] = False
        df["is_pass_into_final_third"] = False
        df["is_pass_into_penalty_area"] = False
        df["is_progressive_carry"] = False

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

    sum_cols = {
        "is_pass": "total_passes",
        "accurate_pass": "accurate_passes",
        "is_key_pass": "key_passes",
        "is_through_ball": "through_balls",
        "is_long_ball": "long_balls",
        "is_cross": "crosses",
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
        "is_interception": "interceptions",
        "is_ball_recovery": "ball_recoveries",
        "is_clearance": "clearances",
        "aerial_won": "aerials_won",
        "is_touch_final_third": "touches_final_third",
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


# ─── Main Build Pipeline ─────────────────────────────────────────────

def build_all_tables():
    """
    Read all event CSVs → aggregate → save matches.csv, players.csv, teams.csv
    """
    event_dir = config.DATA_EVENTS
    csv_files = sorted(event_dir.glob("*.csv")) if event_dir.exists() else []

    print(f"Found {len(csv_files)} event CSVs in {event_dir}")

    if not csv_files:
        print("No event data found. Run the extractor first:")
        print("  python -m src.scraper.whoscored_extractor --ids <match_ids>")
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

    # Save
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

    df_matches.to_csv(config.DATA_PROCESSED / "matches.csv", index=False)
    df_players.to_csv(config.DATA_PROCESSED / "players.csv", index=False)
    df_teams.to_csv(config.DATA_PROCESSED / "teams.csv", index=False)

    print(f"\nTables saved to {config.DATA_PROCESSED}/")
    print(f"  matches: {len(df_matches)} rows")
    print(f"  players: {len(df_players)} rows")
    print(f"  teams:   {len(df_teams)} rows")

    # Quick sanity check
    if not df_players.empty:
        print(f"\n  Unique players: {df_players['player_id'].nunique()}")
        print(f"  Sample columns: {list(df_players.columns[:10])}")


if __name__ == "__main__":
    build_all_tables()
