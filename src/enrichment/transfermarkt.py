"""
Transfermarkt enrichment module.

Scrapes market value and contract data from Transfermarkt squad pages using
seleniumbase UC mode — the same approach used by the WhoScored scraper.

Results are cached locally so scraping only runs when you explicitly refresh.

Pipeline step (run after chance_creation.py and optionally clustering.py):
    python -m src.enrichment.transfermarkt            # use cache if available
    python -m src.enrichment.transfermarkt --refresh  # force re-scrape

Output:
    data/final/chance_creators_enriched.csv
    data/enrichment/tm_squads_cache.csv      ← scraped TM data, commit to git
    data/enrichment/tm_player_mapping.csv    ← name mapping, commit to git
"""

import argparse
import logging
import re
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd
from bs4 import BeautifulSoup
from rapidfuzz import fuzz, process

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config

logger = logging.getLogger(__name__)

MAPPING_FILE    = config.DATA_ENRICHMENT / "tm_player_mapping.csv"
SQUADS_CACHE    = config.DATA_ENRICHMENT / "tm_squads_cache.csv"
MANUAL_PLAYERS  = config.DATA_ENRICHMENT / "tm_manual_players.csv"

TM_BASE       = "https://www.transfermarkt.com"
TM_LEAGUE_URL = f"{TM_BASE}/serie-a/startseite/wettbewerb/IT1"
TM_KADER_SEASON = int(config.SEASON.split("-")[0])   # e.g. 2025 from "2025-2026"

# Keywords that identify the "contract until" column header in both EN and DE
_CONTRACT_HEADER_KEYWORDS = {"contract until", "vertrag bis", "contract expires"}


# ─── Persistent cache / mapping I/O ──────────────────────────────────

def _load_mapping() -> pd.DataFrame:
    if MAPPING_FILE.exists():
        return pd.read_csv(MAPPING_FILE, dtype={"player_id": str, "tm_player_id": str})
    return pd.DataFrame(columns=[
        "player_id", "player_name", "tm_player_id",
        "tm_player_name", "confidence", "verified",
    ])


def _save_mapping(df: pd.DataFrame) -> None:
    config.DATA_ENRICHMENT.mkdir(parents=True, exist_ok=True)
    df.to_csv(MAPPING_FILE, index=False)
    logger.info("Mapping saved → %s", MAPPING_FILE)


# ─── Scraping ─────────────────────────────────────────────────────────

def fetch_tm_squad_data(refresh: bool = False) -> pd.DataFrame:
    """
    Return a DataFrame of all Serie A squad players with market value and
    contract expiry. Uses a local cache; pass refresh=True to re-scrape.

    Columns: tm_player_name, tm_team_name, market_value_eur, contract_expires
    """
    if not refresh and SQUADS_CACHE.exists():
        logger.info("Loading TM squads from cache: %s", SQUADS_CACHE)
        return pd.read_csv(SQUADS_CACHE)

    from seleniumbase import Driver

    all_players: list[dict] = []

    # headless=False: TM is stricter than WhoScored about headless detection.
    # A browser window will be visible during the ~2 min scrape, then close.
    driver = Driver(uc=True, headless=False)
    try:
        # Step 1: Discover team kader URLs from the Serie A competition page
        print(f"[TM] Opening Serie A page …")
        driver.get(TM_LEAGUE_URL)
        time.sleep(config.PAGE_LOAD_WAIT)
        team_urls = _parse_team_urls(driver.page_source)
        print(f"[TM] Found {len(team_urls)} teams.")

        if not team_urls:
            raise RuntimeError(
                "Could not parse any team URLs from the Transfermarkt competition page. "
                "The page structure may have changed."
            )

        # Step 2: Scrape each team's kader page
        for i, (team_name, kader_url) in enumerate(team_urls.items(), 1):
            print(f"[TM] ({i}/{len(team_urls)}) Scraping {team_name} …")
            driver.get(kader_url)
            time.sleep(config.PAGE_LOAD_WAIT)   # full wait — TM needs more time than WhoScored

            players = _parse_kader_table(driver.page_source, team_name)
            all_players.extend(players)
            print(f"         → {len(players)} players parsed")

    finally:
        driver.quit()

    df = pd.DataFrame(all_players)
    config.DATA_ENRICHMENT.mkdir(parents=True, exist_ok=True)
    df.to_csv(SQUADS_CACHE, index=False)
    print(f"[TM] Cached {len(df)} players → {SQUADS_CACHE}")
    return df


# ─── HTML parsers ─────────────────────────────────────────────────────

def _parse_team_urls(html: str) -> dict[str, str]:
    """
    Parse the Serie A competition page and return a dict of
    {team_name: kader_url} for all 20 teams.

    Scopes the search to table cells only — this avoids picking up sidebar
    and navigation links that point to clubs from other competitions.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    team_urls: dict[str, str] = {}

    # Only look at <a> tags inside <td> elements (main competition table rows).
    # Sidebar / navigation links live in <li> or <div>, not <td>.
    for td in soup.find_all("td"):
        for a in td.find_all("a", href=True):
            href: str = a["href"]
            if "/startseite/verein/" not in href or "?" in href:
                continue

            # href looks like "/atalanta-bc/startseite/verein/800"
            parts = href.split("/startseite/verein/")
            if len(parts) != 2:
                continue

            slug      = parts[0].lstrip("/")
            verein_id = parts[1].split("/")[0]

            if not verein_id.isdigit() or verein_id in seen:
                continue

            team_name = a.get_text(strip=True)
            if not team_name:
                continue

            seen.add(verein_id)
            kader_url = (
                f"{TM_BASE}/{slug}/kader/verein/{verein_id}"
                f"/saison_id/{TM_KADER_SEASON}"
            )
            team_urls[team_name] = kader_url

    return team_urls


def _find_table_with_player_links(soup) -> Optional[object]:
    """
    Last-resort table finder: returns the first <table> that contains
    Transfermarkt player profile links (/profil/spieler/).
    """
    for table in soup.find_all("table"):
        if table.find("a", href=lambda h: h and "/profil/spieler/" in h):
            return table
    return None


def _parse_kader_table(html: str, team_name: str) -> list[dict]:
    """
    Parse a Transfermarkt /kader/ page.

    Extracts per-player: tm_player_name, tm_team_name,
    market_value_eur (float EUR), contract_expires (int year).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Cloudflare challenge detection — page didn't load properly
    if "cf-browser-verification" in html or "Checking your browser" in html:
        logger.warning("[%s] Cloudflare challenge page detected — page did not load.", team_name)
        return []

    # Table selector: try in order of preference as TM has changed IDs over time
    table = (
        soup.find("table", {"id": "yw1"})
        or soup.find("table", {"class": "items"})
        or _find_table_with_player_links(soup)
    )
    if table is None:
        logger.warning("[%s] No squad table found — page may not have loaded or structure changed.", team_name)
        return []

    # Detect "contract until" column index from the header row
    contract_col: Optional[int] = None
    thead = table.find("thead")
    if thead:
        ths = thead.find_all("th")
        for i, th in enumerate(ths):
            if th.get_text(strip=True).lower() in _CONTRACT_HEADER_KEYWORDS:
                contract_col = i
                break

    players: list[dict] = []
    tbody = table.find("tbody")
    if tbody is None:
        return []

    for row in tbody.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) < 3:
            continue

        # Player name: first td with class "hauptlink" (but not "rechts hauptlink")
        name: Optional[str] = None
        for td in tds:
            classes = td.get("class") or []
            if "hauptlink" in classes and "rechts" not in classes:
                a_tag = td.find("a")
                if a_tag:
                    name = a_tag.get_text(strip=True)
                    break

        if not name:
            continue

        # Market value: last td with both "rechts" and "hauptlink"
        mv_eur: Optional[float] = None
        for td in reversed(tds):
            classes = td.get("class") or []
            if "rechts" in classes and "hauptlink" in classes:
                mv_eur = _parse_market_value(td.get_text(strip=True))
                break

        # Contract expiry: by detected column index first, then fallback scan
        contract_until: Optional[int] = None
        if contract_col is not None and contract_col < len(tds):
            contract_until = _parse_contract_year(tds[contract_col].get_text(strip=True))

        if contract_until is None:
            # Fallback: scan centered cells for a future year (avoids DOB years)
            for td in tds:
                if "zentriert" not in (td.get("class") or []):
                    continue
                year = _parse_contract_year(td.get_text(strip=True))
                if year and year >= config.TM_CURRENT_SEASON_END_YEAR:
                    contract_until = year
                    break

        players.append({
            "tm_player_name":  name,
            "tm_team_name":    team_name,
            "market_value_eur": mv_eur,
            "contract_expires": contract_until,
        })

    return players


# ─── Value / date parsers ─────────────────────────────────────────────

def _parse_market_value(text: str) -> Optional[float]:
    """Convert TM value strings (€65.00m, €500k, -) to EUR float."""
    if not text or text in ("-", ""):
        return None
    s = text.strip().replace("€", "").replace(",", "").replace(" ", "")
    try:
        if s.lower().endswith("m"):
            return float(s[:-1]) * 1_000_000
        if s.lower().endswith("k"):
            return float(s[:-1]) * 1_000
        return float(s)
    except (ValueError, AttributeError):
        return None


def _parse_contract_year(text: str) -> Optional[int]:
    """Extract a 4-digit contract year from strings like 'Jun 30, 2027' or '30.06.2027'."""
    if not text or text in ("-", ""):
        return None
    m = re.search(r'\b(20[2-3]\d)\b', text)
    return int(m.group(1)) if m else None


# ─── Player name matching ─────────────────────────────────────────────

def build_name_mapping(
    players_df: pd.DataFrame,
    tm_squads: pd.DataFrame,
    existing_mapping: pd.DataFrame,
) -> pd.DataFrame:
    """
    Fuzzy-match WhoScored player names to Transfermarkt player names.

    Only processes players not already in the existing mapping.
    Matches with confidence ≥ TM_MATCH_THRESHOLD are auto-verified.
    Lower-confidence matches are flagged 'manual_needed' — edit the CSV
    and set verified='manual' to include them in the next enrichment run.
    """
    mapping   = existing_mapping.copy()
    mapped_ids = set(mapping["player_id"].astype(str).tolist())

    to_match = players_df[
        ~players_df["player_id"].astype(str).isin(mapped_ids)
    ].copy()

    if to_match.empty:
        logger.info("All players already in mapping — skipping fuzzy match.")
        return mapping

    print(f"[TM] Fuzzy-matching {len(to_match)} new players …")
    tm_names   = tm_squads["tm_player_name"].dropna().tolist()
    new_rows   = []
    manual_log = []

    for _, player in to_match.iterrows():
        ws_name = player["player_name"]
        ws_id   = str(player["player_id"])

        result = process.extractOne(ws_name, tm_names, scorer=fuzz.WRatio)
        if result is None:
            manual_log.append(ws_name)
            new_rows.append({
                "player_id": ws_id, "player_name": ws_name,
                "tm_player_id": None, "tm_player_name": None,
                "confidence": 0.0, "verified": "manual_needed",
            })
            continue

        tm_name, score, _ = result
        tm_row   = tm_squads[tm_squads["tm_player_name"] == tm_name].iloc[0]
        tm_id    = str(tm_row.get("tm_player_id", "")) if pd.notna(tm_row.get("tm_player_id")) else ""
        verified = "auto" if score >= config.TM_MATCH_THRESHOLD else "manual_needed"

        if verified == "manual_needed":
            manual_log.append(f"{ws_name}  →  {tm_name}  ({score:.0f})")

        new_rows.append({
            "player_id": ws_id, "player_name": ws_name,
            "tm_player_id": tm_id, "tm_player_name": tm_name,
            "confidence": round(score, 1), "verified": verified,
        })

    if manual_log:
        print(
            f"\nWARNING: {len(manual_log)} player(s) need manual verification.\n"
            f"Edit the mapping file and set verified='manual' for each:\n"
            f"  {MAPPING_FILE}\n"
        )
        for entry in manual_log:
            print(f"  · {entry}")
        print()

    return pd.concat([mapping, pd.DataFrame(new_rows)], ignore_index=True)


# ─── Transfer feasibility ─────────────────────────────────────────────

def compute_transfer_feasibility(contract_expires) -> str:
    """
    Expiring  — ≤1 year left  (final year or out of contract)
    Mid-term  — 1–2 years left
    Locked    — 2+ years left
    """
    try:
        years_left = int(contract_expires) - config.TM_CURRENT_SEASON_END_YEAR
    except (TypeError, ValueError):
        return "Unknown"
    if years_left <= 1:
        return "Expiring"
    if years_left <= 2:
        return "Mid-term"
    return "Locked"


# ─── Manual player override ───────────────────────────────────────────

def _merge_manual_players(tm_squads: pd.DataFrame) -> pd.DataFrame:
    """
    Merge tm_manual_players.csv into the squads DataFrame.

    Manual entries take priority over scraped data — useful for players
    who transferred out of Serie A mid-season and are no longer in any
    team's kader page.

    CSV columns: tm_player_name, tm_team_name, market_value_eur, contract_expires
    market_value_eur: number in EUR (e.g. 18000000)
    contract_expires: year (e.g. 2028)
    """
    if not MANUAL_PLAYERS.exists():
        return tm_squads

    manual = pd.read_csv(MANUAL_PLAYERS)
    manual = manual.dropna(subset=["tm_player_name", "market_value_eur"])

    if manual.empty:
        return tm_squads

    # Manual entries override any scraped row with the same player name
    scraped = tm_squads[~tm_squads["tm_player_name"].isin(manual["tm_player_name"])]
    merged  = pd.concat([scraped, manual], ignore_index=True)
    print(f"[TM] Merged {len(manual)} manual player(s) from {MANUAL_PLAYERS.name}")
    return merged


# ─── Enrichment join ──────────────────────────────────────────────────

def enrich_chance_creators(
    df: pd.DataFrame,
    tm_squads: pd.DataFrame,
    mapping: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join Transfermarkt data onto the chance creators DataFrame.
    Adds: market_value_eur, contract_expires, transfer_feasibility.
    Only uses mapping rows verified as 'auto' or 'manual'.
    """
    usable = mapping[mapping["verified"].isin(["auto", "manual"])].copy()
    usable["player_id"] = usable["player_id"].astype(str)

    df = df.copy()
    df["player_id"] = df["player_id"].astype(str)

    df = df.merge(usable[["player_id", "tm_player_name"]], on="player_id", how="left")

    tm_slim = (
        tm_squads[["tm_player_name", "market_value_eur", "contract_expires"]]
        .drop_duplicates("tm_player_name")
    )
    df = df.merge(tm_slim, on="tm_player_name", how="left")
    df = df.drop(columns=["tm_player_name"], errors="ignore")

    df["transfer_feasibility"] = df["contract_expires"].apply(compute_transfer_feasibility)
    return df


# ─── Pipeline entry point ─────────────────────────────────────────────

def run_enrichment(refresh: bool = False) -> None:
    clustered_path = config.DATA_FINAL / "chance_creators_clustered.csv"
    base_path      = config.DATA_FINAL / "chance_creators.csv"
    output_path    = config.DATA_FINAL / "chance_creators_enriched.csv"

    input_path = clustered_path if clustered_path.exists() else base_path
    if not input_path.exists():
        print("ERROR: No chance creators data found. Run the feature engineering pipeline first.")
        sys.exit(1)

    df = pd.read_csv(input_path)
    print(f"[TM] Loaded {len(df)} players from {input_path.name}")

    tm_squads = fetch_tm_squad_data(refresh=refresh)
    tm_squads = _merge_manual_players(tm_squads)
    mapping   = _load_mapping()
    mapping   = build_name_mapping(df, tm_squads, mapping)
    _save_mapping(mapping)

    enriched  = enrich_chance_creators(df, tm_squads, mapping)

    matched = enriched["market_value_eur"].notna().sum()
    print(f"[TM] Matched: {matched}/{len(enriched)} players")
    if matched < len(enriched):
        unmatched = enriched[enriched["market_value_eur"].isna()]["player_name"].tolist()
        print(f"     Unmatched: {', '.join(unmatched)}")
        print(f"     Fix in: {MAPPING_FILE}")

    enriched.to_csv(output_path, index=False)
    print(f"[TM] Saved → {output_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Transfermarkt enrichment scraper")
    parser.add_argument(
        "--refresh", action="store_true",
        help="Force re-scrape from Transfermarkt even if cache exists",
    )
    args = parser.parse_args()

    run_enrichment(refresh=args.refresh)
