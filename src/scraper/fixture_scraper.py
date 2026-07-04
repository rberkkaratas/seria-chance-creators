"""
WhoScored Fixture List Scraper
-------------------------------
Scrapes all match IDs for a given league/season from WhoScored's
fixtures page and saves them to data/match_ids/{league}_{season}.csv.

The output CSV has two columns:
    match_id  — WhoScored numeric match ID
    scraped   — False initially; set to True by whoscored_extractor

HTML analysis of the live WhoScored fixtures page (Bundesliga 2025-2026):

  - Match data is embedded as JSON in the page source:
      "matches":[{"stageId":...,"id":1910749,"status":6,...}, ...]
    Extracted via regex: `"id":(\\d+),"status"`

  - Navigation buttons have stable IDs:
      #dayChangeBtn-prev  — go to previous time window
      #dayChangeBtn-next  — go to next time window
    Each click loads a new month's worth of fixtures (~25-35 matches).
    The button does NOT get a disabled attribute at season boundaries;
    instead the matches list becomes empty — we detect this to stop.

  Strategy:
    1. Load the fixture URL (lands on current date's month).
    2. Click #dayChangeBtn-prev until no new IDs appear for MAX_EMPTY_CLICKS
       consecutive clicks — this walks back to the season start.
    3. Reload the fixture URL to reset to current position.
    4. Click #dayChangeBtn-next until no new IDs appear for MAX_EMPTY_CLICKS
       consecutive clicks — this walks forward to the season end.

Usage:
    # Fixture URL must be set in config.LEAGUES[league]["fixture_url"]
    python -m src.scraper.fixture_scraper --league Bundesliga --season 2025-2026

    # Override URL at runtime:
    python -m src.scraper.fixture_scraper \\
        --league Premier_League --season 2025-2026 \\
        --fixture-url "https://www.whoscored.com/regions/252/..."
"""

import re
import time
import argparse

import pandas as pd
from seleniumbase import Driver

import config


WHOSCORED_BASE = "https://www.whoscored.com"

# Extraction method 1: match IDs embedded in the React component JSON blob.
# Present in the initial server-rendered page. Pattern confirmed from live HTML:
#   "id":1910749,"status":6
# NOTE: this script tag persists in page_source after React navigation — it always
# returns the initial page's IDs and cannot be relied on alone after navigation.
# status == 6 means the match is finished/played on WhoScored.
MATCH_ID_JSON_PATTERN = re.compile(r'"id":(\d+),"status":(\d+)')
FINISHED_STATUS = 6

# Extraction method 2: match IDs in anchor hrefs.
# After React navigates to a new month, new matches are rendered as DOM elements
# with hrefs like /matches/1910749/live/... or /matches/1910749/show/...
# Both /live/ and /show/ point to the same match — capture either.
MATCH_ID_HREF_PATTERN = re.compile(r"/matches/(\d+)/(?:live|show)/", re.IGNORECASE)
MATCH_DATA_PATTERN = re.compile(r"matchCentreData", re.IGNORECASE)
STAGE_ID_PATTERN = re.compile(r"/stages/(\d+)/", re.IGNORECASE)

# Confirmed button IDs from live HTML inspection.
BTN_PREV = "#dayChangeBtn-prev"
BTN_NEXT = "#dayChangeBtn-next"

# Stop navigating after this many consecutive clicks yield no new IDs.
MAX_EMPTY_CLICKS = 3


# ─── CLI ──────────────────────────────────────────────────────────────

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Scrape WhoScored fixture list → match ID manifest CSV"
    )
    parser.add_argument(
        "--league", required=True,
        choices=list(config.LEAGUES.keys()) + ["all"],
        help="League key (e.g. Premier_League) or 'all' to scrape every league sequentially"
    )
    parser.add_argument(
        "--season", default=config.SEASON,
        help="Season string (e.g. 2025-2026)"
    )
    parser.add_argument(
        "--fixture-url", default=None,
        help="Full WhoScored fixtures page URL. Overrides config.LEAGUES[league]['fixture_url']. "
             "Ignored when --league all."
    )
    parser.add_argument(
        "--max-clicks", type=int, default=20,
        help="Safety cap on total navigation clicks in each direction (default: 20)"
    )
    parser.add_argument(
        "--include-future", action="store_true", default=False,
        help="Also navigate forward to collect upcoming fixture IDs (not yet playable). "
             "By default only past/finished matches are collected."
    )
    return parser.parse_args()


# ─── Extraction ───────────────────────────────────────────────────────

def extract_match_ids_from_html(html: str, past_only: bool = True) -> set[str]:
    """
    Extract WhoScored match IDs from a rendered fixtures page.

    JSON blob: present in the initial server-rendered HTML; persists unchanged
      in page_source after React navigation (stale after month changes).
      When past_only=True, only IDs with status == FINISHED_STATUS are included.
    hrefs (/live/ and /show/): updated by React on every navigation — this is
      the authoritative source for any month after the initial load.
    """
    if past_only:
        json_ids = {mid for mid, status in MATCH_ID_JSON_PATTERN.findall(html)
                    if int(status) == FINISHED_STATUS}
    else:
        json_ids = {mid for mid, status in MATCH_ID_JSON_PATTERN.findall(html)}
    href_ids = set(MATCH_ID_HREF_PATTERN.findall(html))
    return json_ids | href_ids


# Selector for the calendar month label — e.g. "Mar 2026".
# Confirmed from live HTML: <span class="toggleDatePicker">Mar 2026</span>
CALENDAR_LABEL_SELECTOR = "span.toggleDatePicker"

# Poll interval and max wait for React state update after a click.
_POLL_INTERVAL = 0.4   # seconds between polls
_MAX_WAIT      = 8.0   # seconds to wait for month label to change


def _get_calendar_month(driver) -> str:
    """Return the currently displayed calendar month label (e.g. 'Mar 2026')."""
    try:
        el = driver.find_element("css selector", CALENDAR_LABEL_SELECTOR)
        return el.text.strip()
    except Exception:
        return ""


def _js_click(driver, btn_selector: str) -> bool:
    """
    Click a button via JavaScript — required for React SPA pages where
    native Selenium click() does not trigger React's synthetic event listeners.
    Returns True on success, False if the button is not found.
    """
    try:
        btn = driver.find_element("css selector", btn_selector)
        driver.execute_script("arguments[0].click();", btn)
        return True
    except Exception:
        return False


def _wait_for_month_change(driver, previous_month: str) -> bool:
    """
    Poll until the calendar month label changes from previous_month,
    or until _MAX_WAIT seconds elapse.
    Returns True if the month changed, False on timeout.
    """
    elapsed = 0.0
    while elapsed < _MAX_WAIT:
        time.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL
        if _get_calendar_month(driver) != previous_month:
            return True
    return False


def _navigate_direction(
    driver,
    btn_selector: str,
    direction: str,
    all_ids: set[str],
    max_clicks: int,
) -> set[str]:
    """
    Click btn_selector repeatedly, waiting for the calendar month to change
    on each click before extracting IDs. Stops when the month does not change
    for MAX_EMPTY_CLICKS consecutive clicks (season boundary) or max_clicks
    is reached.

    Uses JavaScript click to reliably fire React's synthetic event listeners.
    """
    empty_streak = 0
    for click_num in range(1, max_clicks + 1):
        before_month = _get_calendar_month(driver)

        ok = _js_click(driver, btn_selector)
        if not ok:
            print(f"  [{direction}] Button not found at click {click_num}. Stopping.")
            break

        # Wait for React to re-render with new month's fixtures.
        changed = _wait_for_month_change(driver, before_month)
        after_month = _get_calendar_month(driver)

        # WhoScored's React calendar can update match blocks without changing
        # the visible month label, so always parse after a click and only treat
        # it as empty when both the label is unchanged and no new IDs appear.
        time.sleep(1.0)
        html = driver.page_source
        found = extract_match_ids_from_html(html)
        new = found - all_ids
        all_ids |= found

        if not changed and not new:
            empty_streak += 1
            print(
                f"  [{direction}] click {click_num}: month did not change "
                f"({before_month} → {after_month}) [{empty_streak}/{MAX_EMPTY_CLICKS}]"
            )
            if empty_streak >= MAX_EMPTY_CLICKS:
                print(f"  [{direction}] Season boundary reached.")
                break
            continue

        empty_streak = 0
        print(
            f"  [{direction}] click {click_num}: {before_month} → {after_month} "
            f"| +{len(new)} new IDs (total {len(all_ids)})"
        )

    return all_ids


def scrape_fixture_page(fixture_url: str, max_clicks: int = 20, include_future: bool = False) -> list[str]:
    """
    Navigate the WhoScored fixtures page and collect match IDs.

    1. Load the URL (lands on current month).
    2. Navigate backward (prev) to collect past/finished fixtures.
    3. Optionally reload and navigate forward (next) for upcoming fixtures.

    By default only finished matches (status == 6) are collected.
    Pass include_future=True to also collect upcoming fixture IDs.

    Returns a deduplicated, sorted list of match ID strings.
    """
    all_ids: set[str] = set()
    driver = None

    try:
        driver = Driver(uc=True, headless=True)

        # ── Initial page load ──────────────────────────────────────────
        print("  Loading fixture page...")
        driver.get(fixture_url)
        time.sleep(config.PAGE_LOAD_WAIT)

        html = driver.page_source
        initial_ids = extract_match_ids_from_html(html, past_only=not include_future)
        all_ids |= initial_ids
        print(f"  Initial load: {len(initial_ids)} IDs (total {len(all_ids)})")

        # ── Backward pass — past fixtures ──────────────────────────────
        print(f"\n  Navigating backward (past fixtures)...")
        all_ids = _navigate_direction(driver, BTN_PREV, "prev", all_ids, max_clicks)

        # ── Forward pass — upcoming fixtures (opt-in only) ─────────────
        if include_future:
            print(f"\n  Reloading page for forward pass...")
            driver.get(fixture_url)
            time.sleep(config.PAGE_LOAD_WAIT)
            all_ids |= extract_match_ids_from_html(driver.page_source, past_only=False)

            print(f"\n  Navigating forward (upcoming fixtures)...")
            all_ids = _navigate_direction(driver, BTN_NEXT, "next", all_ids, max_clicks)
        else:
            print("  Skipping forward pass (future matches excluded). Use --include-future to enable.")

    except Exception as e:
        print(f"  [!] Scraper error: {e}")
    finally:
        if driver:
            driver.quit()

    return sorted(all_ids)


def scan_match_id_ranges(
    id_ranges: list[tuple[int, int]],
    title_markers: list[str],
    wait_seconds: float = 1.25,
) -> list[str]:
    """
    Fallback fixture discovery for WhoScored pages whose React pagination
    cannot run because CDN assets fail to load.

    WhoScored league fixtures are usually allocated in compact match-ID blocks,
    but adjacent leagues can share the same numeric area. We therefore only
    accept IDs whose match page title contains a configured league marker and
    whose page contains matchCentreData, because this pipeline only needs event
    data. Event extraction later verifies whether the page exposes
    matchCentreData.
    """
    if not id_ranges or not title_markers:
        return []

    found: set[str] = set()
    total_candidates = sum(end - start + 1 for start, end in id_ranges)
    scanned = 0
    driver = None

    def _new_scan_driver():
        scan_driver = Driver(uc=True, headless=True, page_load_strategy="none")
        scan_driver.set_page_load_timeout(15)
        scan_driver.command_executor._client_config.timeout = 10
        return scan_driver

    try:
        driver = _new_scan_driver()

        for start, end in id_ranges:
            print(f"  Scanning match ID range {start}-{end} ({end - start + 1} candidates)")
            for match_id in range(start, end + 1):
                scanned += 1
                if scanned == 1 or scanned % 50 == 0 or scanned == total_candidates:
                    print(f"    scan progress: {scanned}/{total_candidates} | found {len(found)}")

                try:
                    open_url = driver.default_get if hasattr(driver, "default_get") else driver.get
                    open_url(f"{WHOSCORED_BASE}/Matches/{match_id}/Live/")
                    time.sleep(wait_seconds)
                    driver.execute_script("window.stop();")
                    title = driver.execute_script("return document.title || '';") or ""
                    if not any(marker in title for marker in title_markers):
                        continue

                    found.add(str(match_id))
                    print(f"    + {match_id}: {title}")
                except Exception as exc:
                    print(f"    [!] scan failed for {match_id}: {exc}")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    time.sleep(1.0)
                    driver = _new_scan_driver()
                    continue
    finally:
        if driver:
            driver.quit()

    return sorted(found)


# ─── Manifest Management ─────────────────────────────────────────────

def load_existing_manifest(path) -> pd.DataFrame:
    """Load existing manifest or return empty DataFrame."""
    if path.exists():
        df = pd.read_csv(path, dtype={"match_id": str, "source_stage_id": str})
    else:
        df = pd.DataFrame(columns=config.MANIFEST_COLUMNS)
    return _normalize_manifest_columns(df)


def _normalize_manifest_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a manifest with the current schema, preserving old two-column files."""
    df = df.copy()
    for col in config.MANIFEST_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    if "scraped" in df.columns:
        df["scraped"] = df["scraped"].fillna(False).astype(bool)
    else:
        df["scraped"] = False
    # Force every metadata column to clean strings. A CSV round-trip turns
    # empty cells into float NaN, which str() renders as the literal "nan"
    # and which leaves all-NaN columns float64 — rejecting later string
    # assignment. Numeric-looking stage ids also drift to "24580.0" when a
    # reader omits dtype=str; strip the float suffix so stage_phases keys
    # keep matching.
    for col in config.MANIFEST_COLUMNS:
        if col == "scraped":
            continue
        df[col] = df[col].fillna("").astype(str).replace("nan", "")
    df["source_stage_id"] = df["source_stage_id"].str.replace(r"\.0$", "", regex=True)
    return df[config.MANIFEST_COLUMNS]


def _stage_id_from_url(source_url: str) -> str:
    match = STAGE_ID_PATTERN.search(source_url or "")
    return match.group(1) if match else ""


def _manifest_defaults_for_match(
    competition_key: str,
    source_url: str = "",
    stage_id: str | None = None,
) -> dict:
    """Competition metadata defaults for a manifest row."""
    competition = config.COMPETITIONS.get(competition_key, {})
    competition_type = competition.get("competition_type", config.COMPETITION_TYPE_DOMESTIC)
    stage = stage_id if stage_id is not None else _stage_id_from_url(source_url)
    phase = competition.get("stage_phases", {}).get(
        str(stage), config.PHASE_REGULAR_SEASON
    )
    return {
        "competition_key": competition_key,
        "competition_type": competition_type,
        "source_stage_id": str(stage or ""),
        "competition_phase": phase,
        "source_url": source_url,
        "validation_status": config.VALIDATION_PENDING,
        "validated_home_team": "",
        "validated_away_team": "",
    }


def merge_into_manifest(
    existing: pd.DataFrame,
    new_ids: list[str],
    competition_key: str,
    records_by_id: dict[str, dict] | None = None,
) -> pd.DataFrame:
    """
    Merge newly discovered match IDs into the existing manifest.
    Preserves scraped=True for already-processed rows.
    New IDs get scraped=False.
    """
    existing = _normalize_manifest_columns(existing)
    records_by_id = records_by_id or {}
    existing_ids = set(existing["match_id"].tolist())
    truly_new = [mid for mid in new_ids if mid not in existing_ids]

    # Backfill metadata for legacy rows where only match_id/scraped existed.
    # Values are clean strings after _normalize_manifest_columns; an empty
    # stage id is passed as None so it can be re-derived from source_url.
    for idx, row in existing.iterrows():
        defaults = _manifest_defaults_for_match(
            competition_key,
            source_url=row.get("source_url") or "",
            stage_id=row.get("source_stage_id") or None,
        )
        for col, value in defaults.items():
            current = row.get(col)
            if pd.isna(current) or current == "":
                existing.at[idx, col] = value

    if not truly_new:
        print(f"  No new match IDs (all {len(new_ids)} already in manifest).")
        return existing[config.MANIFEST_COLUMNS]

    rows = []
    for mid in truly_new:
        record = records_by_id.get(str(mid), {})
        row = {
            "match_id": str(mid),
            "scraped": False,
            **_manifest_defaults_for_match(
                competition_key,
                source_url=record.get("source_url", ""),
                stage_id=record.get("source_stage_id"),
            ),
        }
        row.update({k: v for k, v in record.items() if k in config.MANIFEST_COLUMNS})
        rows.append(row)

    new_rows = pd.DataFrame(rows)
    combined = pd.concat([existing, new_rows], ignore_index=True)
    combined = combined.sort_values("match_id").reset_index(drop=True)
    print(f"  Added {len(truly_new)} new match IDs to manifest.")
    return _normalize_manifest_columns(combined)


# ─── Entry Point ─────────────────────────────────────────────────────

def _normalize_fixture_url(fixture_url: str) -> str:
    """Return a fully-qualified WhoScored fixtures URL."""
    if fixture_url.startswith("http"):
        return fixture_url
    return WHOSCORED_BASE + fixture_url


def _fixture_urls_for_league(league: str, fixture_url_override: str | None) -> list[str]:
    """Return primary plus extra fixture URLs for a league, unless overridden."""
    if fixture_url_override:
        return [_normalize_fixture_url(fixture_url_override)]

    league_cfg = config.LEAGUES[league]
    raw_urls = [
        league_cfg.get("fixture_url", ""),
        *league_cfg.get("extra_fixture_urls", []),
    ]
    return [_normalize_fixture_url(url) for url in raw_urls if url]


def _scrape_one_league(league: str, season: str, fixture_url_override: str | None, max_clicks: int, include_future: bool = False):
    """Scrape fixture IDs for a single league and write/update its manifest."""
    fixture_urls = _fixture_urls_for_league(league, fixture_url_override)
    if not fixture_urls:
        print(
            f"[!] No fixture URL for {league} {season}.\n"
            f"    Set config.LEAGUES['{league}']['fixture_url'] or pass --fixture-url."
        )
        return

    manifest_path = config.get_match_ids_path(league, season)

    print(f"\nScraping fixtures: {config.LEAGUES[league]['display_name']} {season}")
    print(f"  URLs:     {len(fixture_urls)}")
    for idx, fixture_url in enumerate(fixture_urls, start=1):
        print(f"    {idx}. {fixture_url}")
    print(f"  Manifest: {manifest_path}\n")

    all_match_ids: set[str] = set()
    records_by_id: dict[str, dict] = {}
    for idx, fixture_url in enumerate(fixture_urls, start=1):
        if len(fixture_urls) > 1:
            print(f"\n  Stage URL {idx}/{len(fixture_urls)}")
        stage_ids = scrape_fixture_page(
            fixture_url,
            max_clicks=max_clicks,
            include_future=include_future,
        )
        new_ids = set(stage_ids) - all_match_ids
        all_match_ids.update(stage_ids)
        defaults = _manifest_defaults_for_match(league, source_url=fixture_url)
        for match_id in stage_ids:
            records_by_id.setdefault(str(match_id), defaults.copy())
        print(f"  Stage IDs: {len(stage_ids)} found, +{len(new_ids)} new for league")

    league_cfg = config.LEAGUES[league]
    scan_ranges = league_cfg.get("id_scan_ranges", [])
    title_markers = league_cfg.get("match_title_markers", [])
    if scan_ranges:
        print("\n  Running match ID range scan fallback...")
        scanned_ids = scan_match_id_ranges(scan_ranges, title_markers)
        new_ids = set(scanned_ids) - all_match_ids
        all_match_ids.update(scanned_ids)
        defaults = _manifest_defaults_for_match(league)
        for match_id in scanned_ids:
            records_by_id.setdefault(str(match_id), defaults.copy())
        print(f"  Range scan IDs: {len(scanned_ids)} found, +{len(new_ids)} new for league")

    match_ids = sorted(all_match_ids)
    print(f"\nTotal match IDs found: {len(match_ids)}")

    existing = load_existing_manifest(manifest_path)
    manifest = merge_into_manifest(existing, match_ids, league, records_by_id)
    manifest.to_csv(manifest_path, index=False)

    scraped_count = int(manifest["scraped"].sum())
    print(
        f"Manifest saved → {manifest_path}\n"
        f"  Total:   {len(manifest)} matches\n"
        f"  Scraped: {scraped_count} / {len(manifest)}"
    )


def run_fixture_scraper():
    args = parse_arguments()
    season = args.season

    if args.league == "all":
        if args.fixture_url:
            print("[!] --fixture-url is ignored when --league all. URLs are read from config.")
        leagues = list(config.LEAGUES.keys())
        print(f"Running fixture scraper for all {len(leagues)} leagues: {', '.join(leagues)}")
        for league in leagues:
            _scrape_one_league(league, season, fixture_url_override=None, max_clicks=args.max_clicks, include_future=args.include_future)
        print("\nAll leagues scraped.")
    else:
        _scrape_one_league(args.league, season, args.fixture_url, args.max_clicks, include_future=args.include_future)


if __name__ == "__main__":
    run_fixture_scraper()
