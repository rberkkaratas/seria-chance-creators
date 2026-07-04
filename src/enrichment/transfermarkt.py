"""
Transfermarkt enrichment module.

Scrapes market value and contract data from Transfermarkt squad pages using
seleniumbase UC mode — the same approach used by the WhoScored scraper.

Results are cached locally so scraping only runs when you explicitly refresh.

Pipeline step (run after merge_leagues.py):
    python -m src.enrichment.transfermarkt            # use cache if available
    python -m src.enrichment.transfermarkt --refresh  # force re-scrape

Output:
    data/final/all_leagues_{season}_enriched.csv
    data/enrichment/tm_squads_cache.csv      ← scraped TM data, commit to git
    data/enrichment/tm_player_mapping.csv    ← name mapping, commit to git
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import re
import sys
import time
import unicodedata
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

TM_BASE         = "https://www.transfermarkt.com"
TM_KADER_SEASON = int(config.SEASON.split("-")[0])   # e.g. 2025 from "2025-2026"

# Substrings that identify the contract-expiry column header in both EN and DE.
# In-season kader pages label it "Contract" / "Contract until" / "Vertrag bis";
# past-season pages drop the column entirely (contract data is then unavailable).
_CONTRACT_HEADER_KEYWORDS = {"contract", "vertrag"}


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


def _dedupe_mapping_by_player_id(mapping: pd.DataFrame) -> pd.DataFrame:
    """Keep one best mapping row per WhoScored player_id."""
    if mapping.empty or "player_id" not in mapping.columns:
        return mapping
    mapping = mapping.copy()
    mapping["player_id"] = mapping["player_id"].astype(str)
    priority = {"manual": 0, "auto": 1, "manual_needed": 2}
    mapping["_priority"] = mapping["verified"].map(priority).fillna(3)
    if "confidence" in mapping.columns:
        mapping["confidence"] = pd.to_numeric(mapping["confidence"], errors="coerce")
        mapping = mapping.sort_values(
            ["player_id", "_priority", "confidence"],
            ascending=[True, True, False],
        )
    else:
        mapping = mapping.sort_values(["player_id", "_priority"])
    return mapping.drop_duplicates("player_id", keep="first").drop(columns=["_priority"])


# ─── Scraping ─────────────────────────────────────────────────────────

def _resolve_league_keys(leagues: Optional[list[str]]) -> list[str]:
    if not leagues:
        return list(config.TM_LEAGUE_URLS)

    requested: list[str] = []
    for raw in leagues:
        requested.extend(part.strip() for part in raw.split(",") if part.strip())

    if not requested or "all" in requested:
        return list(config.TM_LEAGUE_URLS)

    invalid = sorted(set(requested) - set(config.TM_LEAGUE_URLS))
    if invalid:
        valid = ", ".join(config.TM_LEAGUE_URLS)
        raise ValueError(f"Unknown Transfermarkt league(s): {', '.join(invalid)}. Valid: {valid}")

    return list(dict.fromkeys(requested))


def _season_pinned_league_url(league_url: str) -> str:
    """
    Pin a TM competition page to the configured season.

    Without saison_id, TM serves the *current* season's team set — at season
    boundaries that is the following season, which silently drops relegated /
    otherwise-departed clubs from the scrape and leaves their players unmatched.
    """
    return f"{league_url.rstrip('/')}/plus/?saison_id={TM_KADER_SEASON}"


def _scrape_league_with_driver(driver, league_key: str) -> list[dict]:
    league_url = _season_pinned_league_url(config.TM_LEAGUE_URLS[league_key])
    display = config.LEAGUES[league_key]["display_name"]
    league_players: list[dict] = []

    print(f"[TM] Opening {display} page …")
    driver.get(league_url)
    time.sleep(config.PAGE_LOAD_WAIT)
    team_urls = _parse_team_urls(driver.page_source)
    if not team_urls:
        # Cloudflare interstitials / slow loads can leave an empty page — retry once
        logger.warning("No team URLs parsed for %s — retrying once …", display)
        driver.get(league_url)
        time.sleep(config.PAGE_LOAD_WAIT + config.PAGE_LOAD_WAIT_EXTENDED)
        team_urls = _parse_team_urls(driver.page_source)
    print(f"[TM] Found {len(team_urls)} teams in {display}.")

    if not team_urls:
        logger.warning(
            "Could not parse any team URLs for %s — skipping. "
            "The page structure may have changed.", display
        )
        return league_players

    for i, (team_name, kader_url) in enumerate(team_urls.items(), 1):
        print(f"[TM] {display} ({i}/{len(team_urls)}) Scraping {team_name} …")
        driver.get(kader_url)
        time.sleep(config.PAGE_LOAD_WAIT)

        players = _parse_kader_table(driver.page_source, team_name)
        if not players:
            logger.warning("[%s] No players parsed — retrying once …", team_name)
            driver.get(kader_url)
            time.sleep(config.PAGE_LOAD_WAIT + config.PAGE_LOAD_WAIT_EXTENDED)
            players = _parse_kader_table(driver.page_source, team_name)
        for player in players:
            player["tm_league_key"] = league_key
        league_players.extend(players)
        print(f"         → {len(players)} players parsed")

    return league_players


def _scrape_single_league(league_key: str) -> pd.DataFrame:
    from seleniumbase import Driver

    driver = Driver(uc=True, headless=False)
    try:
        return pd.DataFrame(_scrape_league_with_driver(driver, league_key))
    finally:
        driver.quit()


def _merge_scraped_squads_with_cache(scraped: pd.DataFrame, league_keys: list[str]) -> pd.DataFrame:
    if not SQUADS_CACHE.exists():
        return scraped

    existing = pd.read_csv(SQUADS_CACHE)
    if existing.empty:
        return scraped

    if "tm_league_key" in existing.columns:
        existing = existing[~existing["tm_league_key"].isin(league_keys)].copy()

    if "tm_team_name" in scraped.columns and "tm_team_name" in existing.columns:
        scraped_teams = set(scraped["tm_team_name"].dropna())
        existing = existing[~existing["tm_team_name"].isin(scraped_teams)].copy()

    merged = pd.concat([existing, scraped], ignore_index=True)
    sort_cols = [
        col for col in ["tm_league_key", "tm_team_name", "tm_player_name"]
        if col in merged.columns
    ]
    if sort_cols:
        merged = merged.sort_values(sort_cols, kind="stable").reset_index(drop=True)
    return merged


def fetch_tm_squad_data(
    refresh: bool = False,
    leagues: Optional[list[str]] = None,
    parallel: bool = False,
    workers: Optional[int] = None,
) -> pd.DataFrame:
    """
    Return a DataFrame of squad players from configured leagues with market
    value and contract expiry. Uses a local cache; pass refresh=True to re-scrape.

    Columns: tm_player_name, tm_team_name, market_value_eur, contract_expires
    """
    if not refresh and SQUADS_CACHE.exists():
        logger.info("Loading TM squads from cache: %s", SQUADS_CACHE)
        return pd.read_csv(SQUADS_CACHE)

    league_keys = _resolve_league_keys(leagues)
    all_league_keys = list(config.TM_LEAGUE_URLS)
    refresh_all = set(league_keys) == set(all_league_keys)

    if parallel and len(league_keys) > 1:
        max_workers = min(workers or len(league_keys), len(league_keys))
        print(f"[TM] Parallel refresh for {len(league_keys)} league(s), workers={max_workers}")
        frames: list[pd.DataFrame] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_scrape_single_league, league_key): league_key
                for league_key in league_keys
            }
            for future in as_completed(futures):
                league_key = futures[future]
                try:
                    frames.append(future.result())
                except Exception:
                    logger.exception("Transfermarkt scrape failed for %s", league_key)
                    raise
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    else:
        from seleniumbase import Driver

        all_players: list[dict] = []
        # headless=False: TM is stricter than WhoScored about headless detection.
        # A browser window will be visible during the scrape, then close.
        driver = Driver(uc=True, headless=False)
        try:
            for league_key in league_keys:
                all_players.extend(_scrape_league_with_driver(driver, league_key))
        finally:
            driver.quit()
        df = pd.DataFrame(all_players)

    if not refresh_all:
        df = _merge_scraped_squads_with_cache(df, league_keys)

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
            # /plus/1 requests the detailed squad view — the compact default
            # no longer carries the "Contract until" column.
            kader_url = (
                f"{TM_BASE}/{slug}/kader/verein/{verein_id}"
                f"/saison_id/{TM_KADER_SEASON}/plus/1"
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
            th_text = th.get_text(strip=True).lower()
            if any(keyword in th_text for keyword in _CONTRACT_HEADER_KEYWORDS):
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
        tm_player_id: Optional[str] = None
        for td in tds:
            classes = td.get("class") or []
            if "hauptlink" in classes and "rechts" not in classes:
                a_tag = td.find("a")
                if a_tag:
                    name = a_tag.get_text(strip=True)
                    href = a_tag.get("href", "")
                    m = re.search(r"/profil/spieler/(\d+)", href)
                    if m:
                        tm_player_id = m.group(1)
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

        # Contract expiry: only from an explicitly detected contract column.
        # Never scan other cells for years — the "Joined" column also holds
        # dates, and misreading a January signing date as a contract expiry
        # silently corrupts transfer_feasibility.
        contract_until: Optional[int] = None
        if contract_col is not None and contract_col < len(tds):
            contract_until = _parse_contract_year(tds[contract_col].get_text(strip=True))

        players.append({
            "tm_player_name":  name,
            "tm_player_id":    tm_player_id,
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

def _normalize_name(name: str) -> str:
    """
    Fold Unicode diacritics to ASCII and lowercase for fuzzy comparison.
    Handles common WhoScored/TM divergences like é→e, ö→o, ı→i, š→s.
    """
    if not name:
        return ""
    # Pre-substitute characters that NFD can't decompose to ASCII
    _PRE_SUB = {
        "\u0131": "i",   # ı (dotless i, Turkish)
        "\u00f8": "o",   # ø (Scandinavian)
        "\u00d8": "O",   # Ø
        "\u00df": "ss",  # ß (German)
        "\u00e6": "ae",  # æ
        "\u00c6": "AE",  # Æ
        "\u0142": "l",   # ł (Polish)
        "\u0141": "L",   # Ł
    }
    for char, sub in _PRE_SUB.items():
        name = name.replace(char, sub)
    # NFD decomposes accented chars into base + combining marks; ASCII encode drops the marks
    normalized = unicodedata.normalize("NFD", name)
    return normalized.encode("ascii", "ignore").decode("ascii").lower().strip()


# WhoScored uses short/abbrev team names that fuzzy-matching can't resolve
# (or worse, resolves to the wrong club: "Sporting Charleroi" → "Sporting CP").
# Map them explicitly to the TM full name.
_WS_TEAM_ALIASES: dict[str, str] = {
    "PSG":       "Paris Saint-Germain",
    "Man Utd":   "Manchester United",
    "Man City":  "Manchester City",
    "West Ham":  "West Ham United",
    "Wolves":    "Wolverhampton Wanderers",
    "Burnley":   "Burnley FC",
    "Rennes":    "Stade Rennais FC",
    "RBL":       "RB Leipzig",
    "FC Koln":   "1.FC Köln",
    "Borussia M.Gladbach": "Borussia Mönchengladbach",
    "Athletic Club":       "Athletic Bilbao",
    "QPR":       "Queens Park Rangers",
    "WBA":       "West Bromwich Albion",
    "Sheff Utd": "Sheffield United",
    "Sheff Wed": "Sheffield Wednesday",
    "OH Leuven":          "Oud-Heverlee Leuven",
    "Sporting Charleroi": "Royal Charleroi SC",
    "St.Truiden":         "Sint-Truidense VV",
    "Union St.Gilloise":  "Union Saint-Gilloise",
    "Estrela da Amadora": "CF Estrela Amadora",
    "Vitoria de Guimaraes": "Vitória Guimarães SC",
    "Istanbul Basaksehir":  "Basaksehir FK",
}


def _build_team_map(
    ws_teams: list[str],
    tm_squads: pd.DataFrame,
) -> dict[str, list[str]]:
    """
    Fuzzy-match each WhoScored team name to a list of TM player names from
    the best-matching TM team. Returns {ws_team → [tm_player_name, ...]}.

    Uses normalized names for matching so "Bayern" → "FC Bayern München" etc.
    Aliases in _WS_TEAM_ALIASES bypass fuzzy matching for known short names.
    """
    tm_team_names   = tm_squads["tm_team_name"].dropna().unique().tolist()
    norm_tm_teams   = [_normalize_name(t) for t in tm_team_names]
    team_map: dict[str, list[str]] = {}

    for ws_team in ws_teams:
        # Check alias first
        tm_team_override = _WS_TEAM_ALIASES.get(ws_team)
        if tm_team_override and tm_team_override in tm_team_names:
            team_map[ws_team] = (
                tm_squads[tm_squads["tm_team_name"] == tm_team_override]["tm_player_name"]
                .dropna().tolist()
            )
            logger.debug("Team alias: %s → %s", ws_team, tm_team_override)
            continue

        norm_ws = _normalize_name(ws_team)
        result  = process.extractOne(norm_ws, norm_tm_teams, scorer=fuzz.WRatio)
        if result is None or result[1] < 60:
            team_map[ws_team] = []
            continue
        _, score, idx = result
        tm_team    = tm_team_names[idx]
        team_players = tm_squads[tm_squads["tm_team_name"] == tm_team][
            "tm_player_name"
        ].dropna().tolist()
        team_map[ws_team] = team_players
        logger.debug("Team map: %s → %s (%.0f)", ws_team, tm_team, score)

    return team_map


def build_name_mapping(
    players_df: pd.DataFrame,
    tm_squads: pd.DataFrame,
    existing_mapping: pd.DataFrame,
) -> pd.DataFrame:
    """
    Fuzzy-match WhoScored player names to Transfermarkt player names.

    Matching strategy (in order):
    1. Exact match on normalized name (diacritics folded) → auto
    2. Team-scoped fuzzy match within the player's own club at threshold 75 → auto
    3. Anything else → manual_needed (best global candidate recorded for review)

    Team-scoped matching dramatically reduces false positives: matching
    "Modrić" within Real Madrid's 25-player squad is far more reliable than
    matching globally against 500+ names. Global fuzzy matches are never
    auto-verified: when a club is absent from the TM cache, a ≥85 global
    score routinely lands on a different player at another club
    (e.g. "Ben Johnson" → "Owen Johnson").
    """
    mapping    = _dedupe_mapping_by_player_id(existing_mapping)
    mapped_ids = set(mapping["player_id"].astype(str).tolist())

    to_match = players_df[
        ~players_df["player_id"].astype(str).isin(mapped_ids)
    ].copy()
    to_match["player_id"] = to_match["player_id"].astype(str)
    to_match = to_match.drop_duplicates("player_id", keep="first")

    if to_match.empty:
        logger.info("All players already in mapping — skipping fuzzy match.")
        return mapping

    print(f"[TM] Fuzzy-matching {len(to_match)} new players …")

    # Pre-build team map for scoped matching
    ws_teams = to_match["team_name"].dropna().unique().tolist() if "team_name" in to_match.columns else []
    team_map = _build_team_map(ws_teams, tm_squads) if ws_teams else {}

    # Pre-normalize all TM names for exact-match lookup
    tm_all_names  = tm_squads["tm_player_name"].dropna().tolist()
    norm_tm_index = {_normalize_name(n): n for n in tm_all_names}  # normalized → original

    new_rows   = []
    manual_log = []

    for _, player in to_match.iterrows():
        ws_name = player["player_name"]
        ws_id   = str(player["player_id"])
        ws_team = player.get("team_name", "") if "team_name" in player.index else ""

        tm_name: Optional[str] = None
        score: float           = 0.0

        # ── Pass 1: exact normalized match ───────────────────────────────
        norm_ws = _normalize_name(ws_name)
        if norm_ws in norm_tm_index:
            tm_name = norm_tm_index[norm_ws]
            score   = 100.0

        # ── Pass 2: team-scoped fuzzy match (threshold 75) ────────────────
        if tm_name is None and ws_team and team_map.get(ws_team):
            team_candidates = team_map[ws_team]
            result = process.extractOne(ws_name, team_candidates, scorer=fuzz.WRatio)
            if result is not None and result[1] >= 75:
                tm_name, score, _ = result

        # ── Determine verification status ─────────────────────────────────
        if tm_name is None:
            # Last-resort: record best global match so the human can judge
            result = process.extractOne(ws_name, tm_all_names, scorer=fuzz.WRatio)
            if result is not None:
                tm_name, score, _ = result
                manual_log.append(f"{ws_name}  →  {tm_name}  ({score:.0f})")
            else:
                manual_log.append(ws_name)
            new_rows.append({
                "player_id": ws_id, "player_name": ws_name,
                "tm_player_id": None, "tm_player_name": tm_name,
                "tm_team_name": None,
                "confidence": round(score, 1), "verified": "manual_needed",
            })
            continue

        # Pick the team-specific row — for duplicate player names this
        # resolves to the correct club via team-scoped matching above.
        _candidates = tm_squads[tm_squads["tm_player_name"] == tm_name]
        tm_row      = _candidates.iloc[0]
        if len(_candidates) > 1 and ws_team:
            # Check alias first — handles abbreviations like "PSG" → "Paris Saint-Germain"
            _alias_tm_team = _WS_TEAM_ALIASES.get(ws_team)
            if _alias_tm_team:
                _alias_match = _candidates[_candidates["tm_team_name"] == _alias_tm_team]
                if not _alias_match.empty:
                    tm_row = _alias_match.iloc[0]
                else:
                    # Alias team found but player not in it — fall back to fuzzy
                    _best_idx = _candidates["tm_team_name"].apply(
                        lambda t: fuzz.WRatio(_normalize_name(ws_team), _normalize_name(str(t)))
                    ).idxmax()
                    tm_row = _candidates.loc[_best_idx]
            else:
                _best_idx = _candidates["tm_team_name"].apply(
                    lambda t: fuzz.WRatio(_normalize_name(ws_team), _normalize_name(str(t)))
                ).idxmax()
                tm_row = _candidates.loc[_best_idx]

        tm_id      = str(tm_row.get("tm_player_id", "")) if pd.notna(tm_row.get("tm_player_id")) else ""
        tm_team    = str(tm_row.get("tm_team_name", ""))
        new_rows.append({
            "player_id": ws_id, "player_name": ws_name,
            "tm_player_id": tm_id, "tm_player_name": tm_name,
            "tm_team_name": tm_team,
            "confidence": round(score, 1), "verified": "auto",
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

    return _dedupe_mapping_by_player_id(
        pd.concat([mapping, pd.DataFrame(new_rows)], ignore_index=True)
    )


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

def enrich_players(
    df: pd.DataFrame,
    tm_squads: pd.DataFrame,
    mapping: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join Transfermarkt data onto the player feature DataFrame.
    Adds: market_value_eur, contract_expires, transfer_feasibility.

    Joins on (tm_player_name + tm_team_name) when tm_team_name is stored in
    the mapping, so players who share the same name at different clubs
    resolve to the correct row. Because the feature table can contain multiple
    rows for the same player_id across position groups, joining by player_id
    enriches each group row consistently.
    """
    usable = mapping[mapping["verified"].isin(["auto", "manual"])].copy()
    usable["player_id"] = usable["player_id"].astype(str)
    usable = _dedupe_mapping_by_player_id(usable)

    df = df.copy()
    df["player_id"] = df["player_id"].astype(str)

    has_team_col = "tm_team_name" in usable.columns

    if has_team_col:
        df = df.merge(
            usable[["player_id", "tm_player_name", "tm_team_name"]],
            on="player_id", how="left",
        )
        # Join TM squads on both name + team — unambiguous even for duplicate names
        tm_slim = (
            tm_squads[["tm_player_name", "tm_team_name", "market_value_eur", "contract_expires"]]
            .drop_duplicates(["tm_player_name", "tm_team_name"], keep="first")
            .copy()
        )
        df = df.merge(tm_slim, on=["tm_player_name", "tm_team_name"], how="left")
        df = df.drop(columns=["tm_player_name", "tm_team_name"], errors="ignore")
    else:
        # Legacy fallback: mapping has no tm_team_name column
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

def run_enrichment(
    refresh: bool = False,
    leagues: Optional[list[str]] = None,
    parallel: bool = False,
    workers: Optional[int] = None,
) -> None:
    all_leagues_path = config.DATA_FINAL / f"all_leagues_{config.SEASON}.csv"

    if not all_leagues_path.exists():
        print(
            "ERROR: No merged player feature data found. Run:\n"
            f"  python -m src.features.player_features --league all --season {config.SEASON}"
        )
        sys.exit(1)

    input_path = all_leagues_path
    output_path = config.DATA_FINAL / f"all_leagues_{config.SEASON}_enriched.csv"

    df = pd.read_csv(input_path)
    print(f"[TM] Loaded {len(df)} players from {input_path.name}")

    tm_squads = fetch_tm_squad_data(
        refresh=refresh,
        leagues=leagues,
        parallel=parallel,
        workers=workers,
    )
    tm_squads = _merge_manual_players(tm_squads)

    mapping = _load_mapping()

    # Drop stale manual_needed rows for re-evaluation.
    stale = (mapping["verified"] == "manual_needed").sum()
    if stale:
        print(f"[TM] Dropping {stale} stale manual_needed rows for re-evaluation …")
        mapping = mapping[mapping["verified"] != "manual_needed"].copy()

    # Drop any auto/manual rows whose tm_player_name is ambiguous in the current
    # cache (same name at multiple clubs). These were matched without team context
    # and may point to the wrong player — re-matching uses team-scoped logic.
    dupe_tm_names = set(
        tm_squads[tm_squads.duplicated("tm_player_name", keep=False)]["tm_player_name"].dropna()
    )
    if dupe_tm_names:
        if "tm_team_name" in mapping.columns:
            ambiguous_mask = mapping["tm_player_name"].isin(dupe_tm_names) & mapping["tm_team_name"].isna()
        else:
            ambiguous_mask = mapping["tm_player_name"].isin(dupe_tm_names)
        n_ambiguous = int(ambiguous_mask.sum())
        if n_ambiguous:
            print(f"[TM] Dropping {n_ambiguous} ambiguous name row(s) for re-evaluation …")
            mapping = mapping[~ambiguous_mask].copy()

    # Backfill tm_team_name for rows that predate this column.
    # For unambiguous names (unique in cache) we can safely fill from cache.
    if "tm_team_name" not in mapping.columns:
        mapping["tm_team_name"] = None
    needs_backfill = mapping["tm_player_name"].notna() & mapping["tm_team_name"].isna()
    if needs_backfill.any():
        _unambiguous = tm_squads[~tm_squads.duplicated("tm_player_name", keep=False)]
        _name_to_team = _unambiguous.set_index("tm_player_name")["tm_team_name"].to_dict()
        mapping.loc[needs_backfill, "tm_team_name"] = (
            mapping.loc[needs_backfill, "tm_player_name"].map(_name_to_team)
        )
        filled = mapping.loc[needs_backfill, "tm_team_name"].notna().sum()
        print(f"[TM] Backfilled tm_team_name for {filled} existing mapping rows.")

    mapping = build_name_mapping(df, tm_squads, mapping)
    _save_mapping(mapping)

    enriched  = enrich_players(df, tm_squads, mapping)

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
    parser.add_argument(
        "--league",
        action="append",
        help=(
            "Limit Transfermarkt refresh to one or more league keys. "
            "Repeat the flag or pass comma-separated keys. Use 'all' for every league."
        ),
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Scrape selected leagues concurrently, one Selenium driver per worker.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Maximum parallel Selenium workers. Defaults to the number of selected leagues.",
    )
    args = parser.parse_args()

    run_enrichment(
        refresh=args.refresh,
        leagues=args.league,
        parallel=args.parallel,
        workers=args.workers,
    )
