"""
League strength enrichment module.

Fetches club Elo ratings from the ClubElo API and reduces them to one
mean Elo per configured league (config.LEAGUE_CLUBELO maps league keys to
ClubElo's (country_code, level) pairs). merge_leagues.py converts those
means into per-league strength offsets used to anchor cross-league
percentiles.

Only relative offsets matter — the global rerank cancels any constant —
so the mean Elos are stored as-is and offsets are computed at merge time,
centered on whichever leagues are actually in the merge pool.

Results are cached locally so fetching only runs when you explicitly
refresh. The cache CSV is committed, so the pipeline never needs network
access at merge time.

If api.clubelo.com is down (it overloads periodically), the GitHub mirror
https://github.com/tonyelhabr/club-rankings publishes the full ClubElo
table in the same column format as a release asset
(clubelo-club-rankings.csv, one row per club per snapshot date plus a
`date` column) — filter to the latest date and pass it through
compute_league_mean_elos() to rebuild the cache manually.

Pipeline step (run before merge_leagues.py whenever coefficients should
be refreshed, typically once per season):
    python -m src.enrichment.league_strength            # use cache if available
    python -m src.enrichment.league_strength --refresh  # force re-fetch

The same snapshot also yields a per-club Elo cache (compute_club_elos /
load_club_elos), kept for team-analytics code as an optional external
reference column — it is not part of the player cross-league anchoring
in merge_leagues.py and does not change get_league_strength's format.

Output:
    data/enrichment/clubelo_league_strength.csv   ← commit to git
    data/enrichment/clubelo_club_elo.csv          ← commit to git
"""

import argparse
import io
import json
import logging
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config

logger = logging.getLogger(__name__)

STRENGTH_CACHE = config.DATA_ENRICHMENT / "clubelo_league_strength.csv"
CLUB_ELO_CACHE = config.DATA_ENRICHMENT / "clubelo_club_elo.csv"

CLUBELO_API = "http://api.clubelo.com/{date}"
CLUBELO_MIRROR_RELEASE_API = "https://api.github.com/repos/tonyelhabr/club-rankings/releases/latest"
CLUBELO_MIRROR_ASSET_NAME = "clubelo-club-rankings.csv"
CLUBELO_TIMEOUT = 30
CLUBELO_REQUIRED_COLUMNS = {"Club", "Country", "Level", "Elo"}

# A league snapshot with a club count outside this range suggests the
# (country_code, level) mapping caught the wrong division.
_PLAUSIBLE_CLUB_RANGE = (14, 26)


# ─── Fetch & reduce ──────────────────────────────────────────────────

def fetch_clubelo_snapshot(snapshot_date: str) -> pd.DataFrame:
    """Fetch the full ClubElo ranking CSV for one date."""
    url = CLUBELO_API.format(date=snapshot_date)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    print(f"[ClubElo] Fetching {url} …")
    with urllib.request.urlopen(request, timeout=CLUBELO_TIMEOUT) as response:
        raw = response.read().decode("utf-8")

    df = pd.read_csv(io.StringIO(raw))
    missing = CLUBELO_REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise RuntimeError(
            f"ClubElo response is missing columns {sorted(missing)} — "
            f"got header {list(df.columns)}. The API format may have changed."
        )
    return df


def _normalize_clubelo_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Accept either ClubElo's capitalized columns or mirror lower-case names."""
    rename_map = {}
    for col in df.columns:
        lower = col.lower()
        if lower == "club":
            rename_map[col] = "Club"
        elif lower == "country":
            rename_map[col] = "Country"
        elif lower == "level":
            rename_map[col] = "Level"
        elif lower == "elo":
            rename_map[col] = "Elo"
    normalized = df.rename(columns=rename_map)
    missing = CLUBELO_REQUIRED_COLUMNS - set(normalized.columns)
    if missing:
        raise RuntimeError(
            f"ClubElo mirror response is missing columns {sorted(missing)} — "
            f"got header {list(df.columns)}."
        )
    return normalized


def fetch_clubelo_mirror_snapshot(snapshot_date: str) -> pd.DataFrame:
    """
    Fetch the latest ClubElo mirror release and select one snapshot.

    The mirror asset stores many dates in one CSV. We prefer the latest
    snapshot on or before `snapshot_date`; if the target is before all
    available rows, we use the earliest available snapshot and record the
    actual date in DataFrame.attrs["snapshot_date"].
    """
    request = urllib.request.Request(
        CLUBELO_MIRROR_RELEASE_API,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    print(f"[ClubElo] API unavailable; checking mirror {CLUBELO_MIRROR_RELEASE_API} …")
    with urllib.request.urlopen(request, timeout=CLUBELO_TIMEOUT) as response:
        release = json.loads(response.read().decode("utf-8"))

    assets = release.get("assets", [])
    asset = next((a for a in assets if a.get("name") == CLUBELO_MIRROR_ASSET_NAME), None)
    if asset is None:
        names = [a.get("name", "") for a in assets]
        raise RuntimeError(
            f"Could not find mirror asset {CLUBELO_MIRROR_ASSET_NAME!r}; "
            f"available assets: {names}"
        )

    download_url = asset["browser_download_url"]
    print(f"[ClubElo] Fetching mirror asset {download_url} …")
    request = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=CLUBELO_TIMEOUT) as response:
        raw = response.read().decode("utf-8")

    df = _normalize_clubelo_columns(pd.read_csv(io.StringIO(raw)))
    date_col = next((c for c in df.columns if c.lower() == "date"), None)
    if date_col is None:
        df.attrs["snapshot_date"] = snapshot_date
        df.attrs["source"] = "github.com/tonyelhabr/club-rankings mirror"
        return df

    parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
    target = pd.to_datetime(snapshot_date)
    available = sorted(parsed_dates.dropna().unique())
    if not available:
        raise RuntimeError("ClubElo mirror asset has a date column but no parseable dates.")

    candidates = [d for d in available if d <= target]
    chosen = candidates[-1] if candidates else available[0]
    out = df[parsed_dates == chosen].copy()
    actual = pd.Timestamp(chosen).date().isoformat()
    out.attrs["snapshot_date"] = actual
    out.attrs["source"] = "github.com/tonyelhabr/club-rankings mirror"
    if actual != snapshot_date:
        print(f"  [!] Mirror snapshot {actual} used instead of requested {snapshot_date}.")
    return out


def compute_league_mean_elos(
    elo_df: pd.DataFrame,
    league_clubelo: dict[str, tuple[str, int]] = config.LEAGUE_CLUBELO,
) -> pd.DataFrame:
    """
    Reduce a ClubElo snapshot to one row per configured league:
    league, country_code, level, n_clubs, mean_elo.

    Raises if any league matches zero clubs — that means the country code
    or level mapping is wrong, and a broken cache must not be written.
    """
    rows = []
    for league, (country_code, level) in league_clubelo.items():
        clubs = elo_df[
            (elo_df["Country"] == country_code) & (elo_df["Level"] == level)
        ]
        n_clubs = len(clubs)
        if n_clubs == 0:
            raise RuntimeError(
                f"ClubElo snapshot has no clubs for {league} "
                f"(Country={country_code!r}, Level={level}). "
                f"Check config.LEAGUE_CLUBELO against the API's country codes."
            )
        lo, hi = _PLAUSIBLE_CLUB_RANGE
        if not lo <= n_clubs <= hi:
            print(f"  [!] {league}: {n_clubs} clubs matched — outside the "
                  f"plausible range {lo}-{hi}, check the mapping.")
            logger.warning("%s matched %d clubs in ClubElo snapshot", league, n_clubs)
        rows.append({
            "league": league,
            "country_code": country_code,
            "level": level,
            "n_clubs": n_clubs,
            "mean_elo": round(float(clubs["Elo"].mean()), 1),
        })
    return pd.DataFrame(rows)


def compute_club_elos(
    elo_df: pd.DataFrame,
    league_clubelo: dict[str, tuple[str, int]] = config.LEAGUE_CLUBELO,
) -> pd.DataFrame:
    """
    Reduce a ClubElo snapshot to one row per club within the configured
    leagues: league, club, country_code, level, elo.

    This is the per-club counterpart to compute_league_mean_elos() — same
    (country_code, level) filter, but keeps every club instead of
    collapsing to a mean. Intended as an external reference column for
    team-analytics code, not for the player cross-league anchoring in
    merge_leagues.py.

    Raises if any league matches zero clubs, for the same reason as
    compute_league_mean_elos(): a broken cache must not be written.
    """
    rows = []
    for league, (country_code, level) in league_clubelo.items():
        clubs = elo_df[
            (elo_df["Country"] == country_code) & (elo_df["Level"] == level)
        ]
        if len(clubs) == 0:
            raise RuntimeError(
                f"ClubElo snapshot has no clubs for {league} "
                f"(Country={country_code!r}, Level={level}). "
                f"Check config.LEAGUE_CLUBELO against the API's country codes."
            )
        for _, club_row in clubs.iterrows():
            rows.append({
                "league": league,
                "club": club_row["Club"],
                "country_code": country_code,
                "level": level,
                "elo": float(club_row["Elo"]),
            })
    return pd.DataFrame(rows)


# ─── Cache-first accessor ────────────────────────────────────────────

def get_league_strength(
    refresh: bool = False,
    snapshot_date: str = config.CLUBELO_SNAPSHOT_DATE,
) -> pd.DataFrame:
    """
    Return the league strength table (one row per league) from cache,
    fetching from ClubElo only when refreshing or no cache exists.
    """
    if not refresh and STRENGTH_CACHE.exists():
        logger.info("Loading league strength from cache: %s", STRENGTH_CACHE)
        return pd.read_csv(STRENGTH_CACHE)

    source = "api.clubelo.com"
    try:
        elo_df = fetch_clubelo_snapshot(snapshot_date)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("ClubElo API fetch failed, trying mirror: %s", exc)
        try:
            elo_df = fetch_clubelo_mirror_snapshot(snapshot_date)
            source = elo_df.attrs.get("source", "github.com/tonyelhabr/club-rankings mirror")
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as mirror_exc:
            if STRENGTH_CACHE.exists():
                print(f"  [!] ClubElo fetch failed ({exc}); mirror failed "
                      f"({mirror_exc}) — falling back to the committed cache "
                      f"{STRENGTH_CACHE.name}.")
                logger.warning("ClubElo fetch and mirror failed, using cache: %s", mirror_exc)
                return pd.read_csv(STRENGTH_CACHE)
            raise RuntimeError(
                f"ClubElo fetch failed ({exc}); mirror failed ({mirror_exc}); "
                f"and no cache exists at {STRENGTH_CACHE}. Run this module "
                f"from a machine with network access and commit the cache CSV."
            ) from mirror_exc

    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    actual_snapshot_date = elo_df.attrs.get("snapshot_date", snapshot_date)

    strength = compute_league_mean_elos(elo_df)
    strength["snapshot_date"] = actual_snapshot_date
    strength["fetched_at"] = fetched_at
    strength["source"] = source

    config.DATA_ENRICHMENT.mkdir(parents=True, exist_ok=True)
    strength.to_csv(STRENGTH_CACHE, index=False)
    logger.info("Cached %d league strengths → %s", len(strength), STRENGTH_CACHE)

    club_elos = compute_club_elos(elo_df)
    club_elos["snapshot_date"] = actual_snapshot_date
    club_elos["fetched_at"] = fetched_at
    club_elos["source"] = source
    club_elos.to_csv(CLUB_ELO_CACHE, index=False)
    logger.info("Cached %d club Elos → %s", len(club_elos), CLUB_ELO_CACHE)

    return strength


# ─── Offsets ─────────────────────────────────────────────────────────

def compute_offsets(
    mean_elos: dict[str, float],
    elo_per_sigma: float = config.ELO_PER_SIGMA,
) -> dict[str, float]:
    """Convert league mean Elos to SD-unit offsets centered on their mean."""
    center = sum(mean_elos.values()) / len(mean_elos)
    return {lg: (elo - center) / elo_per_sigma for lg, elo in mean_elos.items()}


def load_offsets_for(leagues: list[str], refresh: bool = False) -> dict[str, float]:
    """
    Merge-facing entry point: strength offsets for exactly `leagues`,
    centered on that pool. Raises if any league is missing from the
    strength table — a silent zero offset would reintroduce the
    weak-league inflation this adjustment exists to fix.
    """
    strength = get_league_strength(refresh=refresh)
    available = dict(zip(strength["league"], strength["mean_elo"]))
    missing = sorted(set(leagues) - set(available))
    if missing:
        raise KeyError(
            f"No league strength entry for {missing}. "
            f"Run: python -m src.enrichment.league_strength --refresh"
        )
    return compute_offsets({lg: available[lg] for lg in leagues})


def load_club_elos() -> pd.DataFrame | None:
    """
    Team-analytics-facing loader: read the per-club Elo cache.

    Returns None (with a printed warning) if the cache file doesn't exist
    yet — downstream team code should treat the Elo reference column as
    optional, not a hard dependency. Run
    `python -m src.enrichment.league_strength --refresh` to generate it.
    """
    if not CLUB_ELO_CACHE.exists():
        print(f"  [!] No club Elo cache at {CLUB_ELO_CACHE} — run "
              f"`python -m src.enrichment.league_strength --refresh` to "
              f"generate it. Continuing without club Elo data.")
        return None
    return pd.read_csv(CLUB_ELO_CACHE)


# ─── Entry Point ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch ClubElo league strength coefficients"
    )
    parser.add_argument("--refresh", action="store_true",
                        help="Force re-fetch even if a cache exists")
    parser.add_argument("--date", default=config.CLUBELO_SNAPSHOT_DATE,
                        help="Snapshot date YYYY-MM-DD (default: %(default)s)")
    args = parser.parse_args()

    strength = get_league_strength(refresh=args.refresh, snapshot_date=args.date)
    offsets = compute_offsets(dict(zip(strength["league"], strength["mean_elo"])))

    print(f"\nLeague strength (snapshot {strength['snapshot_date'].iloc[0]}, "
          f"{config.ELO_PER_SIGMA:.0f} Elo per σ):")
    print(f"  {'league':<22} {'clubs':>5} {'mean Elo':>9} {'offset σ':>9}")
    for _, row in strength.sort_values("mean_elo", ascending=False).iterrows():
        print(f"  {row['league']:<22} {row['n_clubs']:>5} "
              f"{row['mean_elo']:>9.1f} {offsets[row['league']]:>+9.2f}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
