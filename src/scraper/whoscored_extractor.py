"""
WhoScored Event Data Extractor
-------------------------------
Semi-automated pipeline: you provide match IDs, the scraper extracts
raw event data and saves per-match CSVs.

Usage:
    # Explicit match IDs (league/season required for multi-league setup):
    python -m src.scraper.whoscored_extractor --league Serie_A --season 2025-2026 --ids 1829473 1829474

    # From the fixture manifest (recommended — also marks matches as scraped):
    python -m src.scraper.whoscored_extractor --league Premier_League --season 2025-2026 --manifest

    # Legacy: from an arbitrary CSV (outputs to default Serie_A path):
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
        description="WhoScored Event Data Scraper — Top 5 Leagues"
    )
    parser.add_argument(
        "--league", default=config.LEAGUE,
        choices=list(config.LEAGUES.keys()) + ["all"],
        help="League key (default: %(default)s) or 'all' to process every league's manifest sequentially. "
             "'all' requires --manifest; --ids and --csv are not supported."
    )
    parser.add_argument(
        "--season", default=config.SEASON,
        help="Season string, e.g. 2025-2026 (default: %(default)s)"
    )
    parser.add_argument(
        "--ids", nargs="+", default=[],
        help="Explicit list of WhoScored match IDs"
    )
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Path to an arbitrary CSV with a match_id column"
    )
    parser.add_argument(
        "--manifest", action="store_true", default=False,
        help="Load IDs from the fixture manifest (data/match_ids/{league}_{season}.csv) "
             "and mark them as scraped on completion"
    )
    parser.add_argument(
        "--skip-existing", action="store_true", default=True,
        help="Skip matches already extracted (default: True)"
    )
    return parser.parse_args()


def load_match_ids_from_csv(csv_path: str) -> list[str]:
    """Load match IDs from a CSV file."""
    df = pd.read_csv(csv_path, dtype={"match_id": str})
    col = "match_id" if "match_id" in df.columns else df.columns[0]
    return [str(mid) for mid in df[col].tolist()]


def load_match_ids_from_manifest(league: str, season: str) -> list[str]:
    """Load only un-scraped match IDs from the fixture manifest."""
    path = config.get_match_ids_path(league, season)
    if not path.exists():
        print(f"[!] Manifest not found: {path}")
        print(f"    Run fixture_scraper first: python -m src.scraper.fixture_scraper --league {league} --season {season}")
        return []
    df = pd.read_csv(path, dtype={"match_id": str})
    pending = df[~df["scraped"].astype(bool)]["match_id"].tolist()
    print(f"  Manifest: {len(df)} total, {len(pending)} not yet scraped.")
    return pending


def mark_scraped_in_manifest(league: str, season: str, match_ids: list[str]):
    """Set scraped=True for successfully extracted match IDs in the manifest."""
    path = config.get_match_ids_path(league, season)
    if not path.exists():
        return
    df = pd.read_csv(path, dtype={"match_id": str})
    df.loc[df["match_id"].isin(match_ids), "scraped"] = True
    df.to_csv(path, index=False)
    print(f"  Marked {len(match_ids)} matches as scraped in manifest.")


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


def _extract_one_league(league: str, season: str, args) -> tuple[int, int]:
    """
    Extract matches for a single league.
    Returns (success_count, failed_count).
    """
    # Collect match IDs
    match_ids = list(args.ids)
    if args.csv:
        match_ids.extend(load_match_ids_from_csv(args.csv))
    if args.manifest:
        match_ids.extend(load_match_ids_from_manifest(league, season))
    match_ids = list(dict.fromkeys(match_ids))  # dedupe, preserve order

    if not match_ids:
        print(f"  [{league}] No match IDs found. Run fixture_scraper first.")
        return 0, 0

    output_dir = str(config.get_events_path(league, season))

    if args.skip_existing:
        existing = get_existing_match_ids(output_dir)
        before = len(match_ids)
        match_ids = [mid for mid in match_ids if mid not in existing]
        skipped = before - len(match_ids)
        if skipped:
            print(f"  [{league}] Skipping {skipped} already-extracted matches.")

    print(f"  [{league}] Extracting {len(match_ids)} matches → {output_dir}\n")

    success_ids, failed = [], 0
    for match_id in tqdm(match_ids, desc=f"{league}"):
        ok = process_match(match_id, output_dir)
        if ok:
            success_ids.append(match_id)
        else:
            failed += 1

        if len(match_ids) > 1:
            time.sleep(config.REQUEST_DELAY_SECONDS)

    print(f"\n  [{league}] Done. Success: {len(success_ids)} | Failed: {failed}")

    if args.manifest and success_ids:
        mark_scraped_in_manifest(league, season, success_ids)

    return len(success_ids), failed


def run_extraction():
    """
    Main entry point: parse args, resolve IDs, extract, save.
    """
    args = parse_arguments()
    season = args.season

    if args.league == "all":
        if args.ids or args.csv:
            print("[!] --league all does not support --ids or --csv. Use --manifest.")
            return
        if not args.manifest:
            print("[!] --league all requires --manifest. Each league's manifest is used.")
            return

        leagues = list(config.LEAGUES.keys())
        print(f"Extracting all {len(leagues)} leagues from manifests: {', '.join(leagues)}\n")
        total_ok, total_fail = 0, 0
        for league in leagues:
            ok, fail = _extract_one_league(league, season, args)
            total_ok += ok
            total_fail += fail
        print(f"\nAll leagues done. Total success: {total_ok} | Total failed: {total_fail}")
    else:
        _extract_one_league(args.league, season, args)


if __name__ == "__main__":
    run_extraction()
