# Known Data Gaps — 2025/26 Season

Last updated: 2026-07-04 (post fixture-forensics pass). Kept current manually;
regenerate the completeness numbers with
`python -m src.processing.fixture_audit --season 2025-2026` and the venue
validation with `python scripts/validate_fixtures.py --truth-dir <feeds>`.

## Resolved in the forensics pass (for context)

- **Home/away orientation** was arbitrary in all pre-metadata scrapes
  (~53% of matches reversed). Fixed for 9 leagues against fixturedownload.com
  truth feeds; all 9 now have zero duplicate (home, away) pairings and points
  tables identical to official results. Future scrapes carry venue metadata
  from the extractor, so this does not recur.
- **Own goals** were credited to the scorer's team (and to the scorer as goal
  + shot). `build_tables.py` now handles `OwnGoal`; match/team scores were
  corrected from truth feeds (239 matches).
- Championship playoff matches (1979299/300/301/302/932) reclassified
  `promotion_playoff` and excluded from the regular-season table.
- Wrong-competition matches marked: PL 1903233 (a Bundesliga fixture),
  Belgium 1904939.

## Open gaps

### Missing matches (need scraping)

| League | Processed | Missing | Detail |
|---|---|---|---|
| Premier League | 379/380 | 1 | **Liverpool 0–3 Nott'm Forest (2025-11-22)** — its manifest slot was taken by wrong-competition id 1903233; the true match id must be rediscovered from the fixtures page |
| Championship | 462/552 | 90 | 7 ids pending in the manifest, ~83 never discovered; full list via `scripts/validate_fixtures.py` dry-run |
| Primeira Liga | 302/306 | 4 | Gil Vicente–Santa Clara (03.11), Alverca–Rio Ave (08.11), Alverca–Nacional (07.12), Alverca–Porto (22.12) |
| Belgium Pro League | 218/240 | 22+ | 35 ids pending in manifest; all playoff phases (championship/europe/relegation) entirely unscraped |

Points tables for incomplete leagues are partial-season snapshots;
`points_per_match` is the comparable figure and `low_coverage` flags guard the
ratings side.

### Belgium venue validation

Belgium is not covered by fixturedownload.com (and football-data.co.uk is
unreachable from this network; TheSportsDB free tier caps responses at 5
events). Its 218 processed matches still have unvalidated home/away
(54 duplicated pairings). Resolve during the Belgium re-scrape via extractor
metadata, or find a truth feed.

### Player goal counts (own-goal inflation)

The committed player finals (`data/final/all_leagues_*.csv`) were built before
the own-goal fix: a player who scored an own goal was credited +1 goal and
+1 shot in that match. Roughly 239 matches across 9 leagues contain such a
shift. Raw event CSVs are only ~54% local, so a full correction requires
re-scraping events and re-running `build_tables` → `player_features` →
`merge_leagues` → `transfermarkt` → `team_features`. Note this will slightly
shift the (currently approved) player scores. Until then, treat individual
`goals` figures for known own-goal scorers with care.

### Süper Lig postponed matches

1915288 (Beşiktaş–Konyaspor) and 1915291 (Başakşehir–Rizespor) were postponed
fixtures; the truth feed never recorded their scores, so their venue is
validated but scores remain event-derived (post own-goal fix logic was not
applicable — scores came from the corrected truth pass for all other matches).
