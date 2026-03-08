"""
WhoScored Event Data Extractor
-------------------------------
Semi-automated pipeline: you provide match IDs, the scraper extracts
raw event data and saves per-match CSVs.

Based on your original main.py scraper — restructured to fit the
project scaffold while keeping your exact extraction logic.

Usage:
    # Via CLI (same interface as your original script):
    python -m src.scraper.whoscored_extractor --ids 1234567 1234568 1234569

    # Or load IDs from CSV:
    python -m src.scraper.whoscored_extractor --csv data/match_ids.csv
"""

import os
import re
import json
import time
import argparse

import pandas as pd
from datetime import datetime
from seleniumbase import Driver
from tqdm import tqdm

import config


# ─── CLI Arguments ────────────────────────────────────────────────────

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="WhoScored Event Data Scraper for Serie A Chance Creators"
    )
    parser.add_argument(
        "--ids", nargs="+", default=[],
        help="List of WhoScored match IDs"
    )
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Path to CSV file with match IDs (column: match_id)"
    )
    parser.add_argument(
        "--skip-existing", action="store_true", default=True,
        help="Skip matches that have already been extracted (default: True)"
    )
    return parser.parse_args()


def load_match_ids_from_csv(csv_path: str) -> list[str]:
    """Load match IDs from a CSV file."""
    df = pd.read_csv(csv_path)
    col = "match_id" if "match_id" in df.columns else df.columns[0]
    return [str(mid) for mid in df[col].tolist()]


def get_existing_match_ids(output_dir: str) -> set[str]:
    """Check which matches have already been extracted."""
    existing = set()
    if os.path.exists(output_dir):
        for f in os.listdir(output_dir):
            if f.endswith(".csv"):
                # Filename format: DDMMYYYY_matchid.csv
                parts = f.replace(".csv", "").split("_")
                if len(parts) >= 2:
                    existing.add(parts[-1])
    return existing


# ─── Core Scraper Logic (from your main.py) ──────────────────────────

def download_match_html(match_id: str) -> str | None:
    """
    Fetch match page HTML using SeleniumBase UC mode.
    Returns raw HTML or None on failure.
    """
    url = f"https://www.whoscored.com/Matches/{match_id}/Live/"
    print(f"  [*] Fetching match {match_id} from: {url}")

    driver = None
    try:
        driver = Driver(uc=True, headless=True)
        driver.get(url)

        # Wait for page load and JS challenges to resolve
        time.sleep(config.PAGE_LOAD_WAIT)

        html_content = driver.page_source
        if "matchCentreData" not in html_content:
            print(f"  [!] 'matchCentreData' not found yet for {match_id}, waiting longer...")
            time.sleep(config.PAGE_LOAD_WAIT_EXTENDED)
            html_content = driver.page_source

        return html_content
    except Exception as e:
        print(f"  [-] Failed to download match {match_id}: {e}")
        return None
    finally:
        if driver:
            driver.quit()


def extract_json(html: str) -> str | None:
    """
    Extract the matchCentreData JSON from the raw HTML.
    Uses two regex strategies with fallback.
    """
    # Primary regex
    regex_pattern = r'require\.config\.params\["args"\]\s*=\s*([\s\S]*?);'
    matches = re.findall(regex_pattern, html)

    if not matches:
        # Fallback regex
        regex_pattern = r'matchCentreData\s*:\s*([\s\S]*?)\s*,\s*matchCentreEventTypeJson'
        matches = re.findall(regex_pattern, html)
        if not matches:
            return None
        return '{"matchCentreData": ' + matches[0] + "}"

    return matches[0]


def parse_match_json(data_txt: str) -> dict | None:
    """
    Clean and parse the extracted JSON string into a Python dict.
    Handles WhoScored's unquoted keys.
    """
    # Quote known unquoted keys
    data_txt = data_txt.replace("matchId", '"matchId"')
    data_txt = data_txt.replace("matchCentreData", '"matchCentreData"')
    data_txt = data_txt.replace("matchCentreEventTypeJson", '"matchCentreEventTypeJson"')
    data_txt = data_txt.replace("formationIdNameMappings", '"formationIdNameMappings"')
    data_txt = data_txt.strip(";").strip()

    try:
        return json.loads(data_txt)
    except json.JSONDecodeError:
        # Aggressive key quoting fallback
        data_txt = re.sub(r"(\w+)\s*:", r'"\1":', data_txt)
        try:
            return json.loads(data_txt)
        except Exception as e:
            print(f"  [-] JSON Parse Error: {e}")
            return None


def events_to_dataframe(match_data: dict) -> pd.DataFrame | None:
    """
    Extract events from matchCentreData and normalize into a DataFrame.
    """
    events = match_data.get("events", [])
    df = pd.DataFrame(events)

    if df.empty:
        return None

    # Normalize dict columns to displayName strings
    for col in ["type", "outcomeType", "period"]:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: x.get("displayName") if isinstance(x, dict) else x
            )

    # Map teamId to team names
    teams = {
        match_data["home"]["teamId"]: match_data["home"]["name"],
        match_data["away"]["teamId"]: match_data["away"]["name"],
    }
    df["teamName"] = df["teamId"].map(teams)

    return df


def extract_player_metadata(match_data: dict) -> pd.DataFrame:
    """
    Extract player metadata (name, position, age, minutes played, etc.)
    from matchCentreData's player arrays. This info is NOT in the events —
    it comes from home.players and away.players.

    Returns a DataFrame with one row per player appearance in this match.
    """
    rows = []

    for side in ["home", "away"]:
        team = match_data.get(side, {})
        team_id = team.get("teamId")
        team_name = team.get("name")

        for player in team.get("players", []):
            row = {
                "playerId": player.get("playerId"),
                "playerName": player.get("name"),
                "teamId": team_id,
                "teamName": team_name,
                "position": player.get("position"),
                "age": player.get("age"),
                "height": player.get("height"),
                "weight": player.get("weight"),
                "isFirstEleven": player.get("isFirstEleven", False),
                "isManOfTheMatch": player.get("isManOfTheMatch", False),
                "subbedInExpandedMinute": player.get("subbedInExpandedMinute"),
                "subbedOutExpandedMinute": player.get("subbedOutExpandedMinute"),
                # Player stats summary (WhoScored pre-calculates some)
                "rating": player.get("stats", {}).get("ratings", {}).get("overall", {}).get("average"),
            }

            # Calculate minutes played
            sub_in = player.get("subbedInExpandedMinute")
            sub_out = player.get("subbedOutExpandedMinute")
            is_starter = player.get("isFirstEleven", False)

            if is_starter and sub_out is not None:
                row["minutes_played"] = sub_out
            elif is_starter:
                # Played full match — approximate as 90 + stoppage
                row["minutes_played"] = match_data.get("maxMinute", 90)
            elif sub_in is not None and sub_out is not None:
                row["minutes_played"] = max(0, sub_out - sub_in)
            elif sub_in is not None:
                row["minutes_played"] = match_data.get("maxMinute", 90) - sub_in
            else:
                row["minutes_played"] = 0  # unused sub

            rows.append(row)

    return pd.DataFrame(rows)


# ─── Main Processing ─────────────────────────────────────────────────

def process_match(match_id: str, output_dir: str) -> bool:
    """
    Full extraction pipeline for a single match.
    Returns True on success, False on failure.
    """
    html = download_match_html(match_id)
    if not html:
        return False

    data_txt = extract_json(html)
    if not data_txt:
        print(f"  [-] Could not extract JSON for match {match_id}")
        return False

    data = parse_match_json(data_txt)
    if not data:
        return False

    match_data = data.get("matchCentreData")
    if not match_data:
        print(f"  [-] No matchCentreData found for {match_id}")
        return False

    # Extract date for filename
    start_time_str = match_data.get("startTime", "")
    try:
        dt = datetime.fromisoformat(start_time_str)
        date_str = dt.strftime("%d%m%Y")
    except (ValueError, TypeError):
        dt = datetime.now()
        date_str = dt.strftime("%d%m%Y")

    # Extract events to DataFrame
    df = events_to_dataframe(match_data)
    if df is None:
        print(f"  [-] No events found for match {match_id}")
        return False

    # Extract player metadata (position, age, minutes, etc.)
    df_players = extract_player_metadata(match_data)

    # Save events
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{date_str}_{match_id}.csv"
    save_path = os.path.join(output_dir, filename)
    df.to_csv(save_path, index=False)

    # Save player metadata alongside events
    players_dir = os.path.join(output_dir, "players")
    os.makedirs(players_dir, exist_ok=True)
    players_filename = f"{date_str}_{match_id}_players.csv"
    players_path = os.path.join(players_dir, players_filename)
    df_players.to_csv(players_path, index=False)

    print(f"  [+] SUCCESS: Saved {len(df)} events + {len(df_players)} players to {output_dir}")
    return True


def run_extraction():
    """
    Main entry point: parse args, resolve IDs, extract, save.
    """
    args = parse_arguments()

    # Collect match IDs from all sources
    match_ids = list(args.ids)
    if args.csv:
        match_ids.extend(load_match_ids_from_csv(args.csv))
    match_ids = list(dict.fromkeys(match_ids))  # dedupe, preserve order

    if not match_ids:
        print("No match IDs provided. Use --ids or --csv.")
        return

    # Output directory (matches your original folder structure)
    output_dir = str(config.DATA_EVENTS)

    # Skip already-extracted
    if args.skip_existing:
        existing = get_existing_match_ids(output_dir)
        before = len(match_ids)
        match_ids = [mid for mid in match_ids if mid not in existing]
        skipped = before - len(match_ids)
        if skipped:
            print(f"Skipping {skipped} already-extracted matches.")

    print(f"Extracting {len(match_ids)} matches → {output_dir}\n")

    success, failed = 0, 0
    for match_id in tqdm(match_ids, desc="Extracting"):
        ok = process_match(match_id, output_dir)
        if ok:
            success += 1
        else:
            failed += 1

        # Polite delay between matches
        if len(match_ids) > 1:
            time.sleep(config.REQUEST_DELAY_SECONDS)

    print(f"\nDone. Success: {success} | Failed: {failed}")


if __name__ == "__main__":
    run_extraction()
