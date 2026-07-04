"""Validate home/away orientation of processed matches against fixturedownload truth.

Truth feeds: one JSON per league from
https://fixturedownload.com/feed/json/{slug}-{year} (slugs: epl, championship,
bundesliga, serie-a, la-liga, ligue-1, eredivisie, primeira-liga, super-lig —
Belgium is not covered), saved into --truth-dir as {League_Key}.json.

Dry-run by default; pass --apply to rewrite processed matches.csv / teams.csv
and fill manifest validation columns. Run once per season after the scrape
completes (pre-metadata scrapes assigned home/away arbitrarily), then re-run
`python -m src.features.team_features`.

Caveat: postponed matches keep their original date and a null score in the
feed; those are venue-validated via the scoreless fallback and keep our
event-derived score.
"""
import argparse
import json
import sys
import unicodedata
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import config  # noqa: E402
LEAGUES = [
    "Premier_League", "Championship", "Bundesliga", "Serie_A", "La_Liga",
    "Ligue_1", "Eredivisie", "Primeira_Liga", "Super_Lig",
]

ALIASES = {  # WhoScored name -> truth feed name
    "Tottenham": "Spurs",
    "Nottingham Forest": "Nott'm Forest",
    "QPR": "Queens Park Rangers",
    "Sheff Utd": "Sheffield United",
    "Sheff Wed": "Sheffield Wednesday",
    "WBA": "West Bromwich Albion",
    "PSG": "Paris Saint-Germain",
    "Le Havre": "Havre Athletic Club",
    "Rennes": "Stade Rennais FC",
    "AVS Futebol SAD": "AFS",
    "Estrela da Amadora": "Estrela Amadora",
    "Vitoria de Guimaraes": "Vitória SC",
    "Barcelona": "FC Barcelona",
    "Borussia M.Gladbach": "Borussia Mönchengladbach",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("ı", "i").replace("ß", "ss").replace("ø", "o"))
    s = s.encode("ascii", "ignore").decode().lower()
    return "".join(c for c in s if c.isalnum())


def build_mapping(ws_names, truth_names, league):
    """WhoScored name -> truth name; returns (mapping, unmapped_ws)."""
    tn = {norm(t): t for t in truth_names}
    mapping, unmapped = {}, []
    for w in ws_names:
        if w in ALIASES and ALIASES[w] in truth_names:
            mapping[w] = ALIASES[w]
            continue
        nw = norm(w)
        if nw in tn:
            mapping[w] = tn[nw]
            continue
        subs = [t for k, t in tn.items() if nw in k or k in nw]
        if len(subs) == 1:
            mapping[w] = subs[0]
        else:
            unmapped.append(w)
    # bijectivity check
    used = list(mapping.values())
    dupes = {v for v in used if used.count(v) > 1}
    if dupes:
        raise SystemExit(f"{league}: mapping not one-to-one for {dupes}")
    return mapping, unmapped


def parse_ws_date(v):
    return pd.to_datetime(str(int(v)).zfill(8), format="%d%m%Y")


# Championship promotion-playoff matches sat in the manifest/scrape as
# regular_season (their stage id was never captured). Verified manually:
# 1979299/1979301 Hull-Millwall legs, 1979300/1979302 Boro-Southampton
# legs, 1979932 final.
PLAYOFF_IDS = {"Championship": {1979299, 1979300, 1979301, 1979302, 1979932}}
# Wrong-competition leakage confirmed by fixture_audit + truth feeds.
WRONG_COMP = {"Premier_League": {1903233}, "Belgium_Pro_League": {1904939}}

COMP_DEFAULTS = {
    "competition_key": None,  # filled with league key
    "competition_type": config.COMPETITION_TYPE_DOMESTIC,
    "competition_phase": config.PHASE_REGULAR_SEASON,
    "phase_table_scope": config.TABLE_SCOPE_REGULAR,
    "source_stage_id": "",
    "validation_status": config.VALIDATION_PENDING,
}


def ensure_comp_columns(df, league):
    for col, default in COMP_DEFAULTS.items():
        if col not in df.columns:
            df[col] = league if col == "competition_key" else default
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--truth-dir", required=True,
                    help="Directory holding {League_Key}.json fixturedownload feeds")
    args = ap.parse_args()
    truth_dir = Path(args.truth_dir)

    grand = {"ok": 0, "swapped": 0, "foreign": 0, "score_mismatch": 0}
    missing_report = {}

    for lg in LEAGUES:
        truth = json.load(open(truth_dir / f"{lg}.json"))
        truth_names = sorted({m["HomeTeam"] for m in truth} | {m["AwayTeam"] for m in truth})
        proc_dir = REPO / "data" / "processed" / lg / "2025-2026"
        matches = pd.read_csv(proc_dir / "matches.csv")
        teams = pd.read_csv(proc_dir / "teams.csv")

        ws_names = sorted(set(matches["home_team_name"]) | set(matches["away_team_name"]))
        mapping, unmapped = build_mapping(ws_names, truth_names, lg)

        # truth index: pair-set -> list of (date, home, away, hs, as)
        tindex = {}
        for m in truth:
            d = pd.to_datetime(m["DateUtc"].split(" ")[0])
            key = frozenset((m["HomeTeam"], m["AwayTeam"]))
            tindex.setdefault(key, []).append(
                (d, m["HomeTeam"], m["AwayTeam"], m["HomeTeamScore"], m["AwayTeamScore"])
            )

        swaps, foreign, ok, score_mm = [], [], 0, []
        validated = {}  # match_id -> (truth_home_ws_name, truth_away_ws_name)
        matched_truth = set()

        for _, row in matches.iterrows():
            wh, wa = row["home_team_name"], row["away_team_name"]
            if wh not in mapping or wa not in mapping:
                foreign.append((row["match_id"], wh, wa))
                continue
            th, ta = mapping[wh], mapping[wa]
            cands = tindex.get(frozenset((th, ta)), [])
            wd = parse_ws_date(row["date_str"])
            best = min(cands, key=lambda c: abs((c[0] - wd).days), default=None)
            if best is None or abs((best[0] - wd).days) > 3:
                # Postponed matches keep their original date and a None score
                # in the feed — fall back to a scoreless entry of the same
                # pair for venue-only validation (our event score is kept).
                scoreless = [c for c in cands if c[3] is None]
                if scoreless:
                    best = scoreless[0]
                else:
                    foreign.append((row["match_id"], wh, wa))
                    continue
            matched_truth.add((frozenset((th, ta)), best[0]))
            t_home = best[1]
            if t_home == th:
                ok += 1
                validated[row["match_id"]] = (wh, wa, best[3], best[4])
                hs, as_ = row["home_score"], row["away_score"]
            else:
                swaps.append(row["match_id"])
                validated[row["match_id"]] = (wa, wh, best[3], best[4])
                hs, as_ = row["away_score"], row["home_score"]
            if best[3] is not None and (int(hs) != int(best[3]) or int(as_) != int(best[4])):
                score_mm.append((row["match_id"], f"{hs}-{as_}", f"{best[3]}-{best[4]}"))

        # truth fixtures we never matched (played ones only: score present)
        missing = []
        for key, entries in tindex.items():
            for e in entries:
                if (key, e[0]) not in matched_truth and e[3] is not None:
                    missing.append(f"{e[1]} vs {e[2]} ({e[0].date()}, {e[3]}-{e[4]})")
        missing_report[lg] = missing

        print(f"{lg}: ok={ok} swapped={len(swaps)} foreign/unmatched={len(foreign)} "
              f"score_mismatch={len(score_mm)} unmapped_names={unmapped} "
              f"truth_missing_from_ws={len(missing)}")
        for f in foreign:
            print(f"    FOREIGN: {f}")
        for s in score_mm[:5]:
            print(f"    SCORE MISMATCH: {s}")
        grand["ok"] += ok
        grand["swapped"] += len(swaps)
        grand["foreign"] += len(foreign)
        grand["score_mismatch"] += len(score_mm)

        if args.apply:
            playoff_ids = PLAYOFF_IDS.get(lg, set())
            wrong_ids = WRONG_COMP.get(lg, set())
            swap_set = set(swaps)

            m = ensure_comp_columns(matches.copy(), lg)
            msk = m["match_id"].isin(swap_set)
            for a, b in [("home_team_id", "away_team_id"), ("home_team_name", "away_team_name"),
                         ("home_score", "away_score")]:
                m.loc[msk, [a, b]] = matches.loc[msk, [b, a]].values
            # authoritative scores from the truth feed (also fixes own-goal
            # attribution for matches whose raw events are not local)
            score_writes = 0
            for match_id, (vh, va, ths, tas) in validated.items():
                if ths is None:
                    continue
                sel = m["match_id"] == match_id
                if int(m.loc[sel, "home_score"].iloc[0]) != int(ths) or \
                   int(m.loc[sel, "away_score"].iloc[0]) != int(tas):
                    score_writes += 1
                m.loc[sel, ["home_score", "away_score"]] = [int(ths), int(tas)]
                m.loc[sel, "validation_status"] = config.VALIDATION_OK
            m.loc[m["match_id"].isin(playoff_ids), "competition_phase"] = config.PHASE_PROMOTION_PLAYOFF
            m.loc[m["match_id"].isin(playoff_ids), "phase_table_scope"] = config.TABLE_SCOPE_PLAYOFF
            m.loc[m["match_id"].isin(wrong_ids), "validation_status"] = config.VALIDATION_WRONG_COMPETITION
            m.to_csv(proc_dir / "matches.csv", index=False)

            t = teams.copy()
            t.loc[t["match_id"].isin(swap_set), "is_home"] = ~t.loc[
                t["match_id"].isin(swap_set), "is_home"]
            # per-team goals from truth
            for match_id, (vh, va, ths, tas) in validated.items():
                if ths is None:
                    continue
                sel = t["match_id"] == match_id
                t.loc[sel & (t["team_name"] == vh), "goals"] = int(ths)
                t.loc[sel & (t["team_name"] == va), "goals"] = int(tas)
            t.to_csv(proc_dir / "teams.csv", index=False)

            # manifest validation columns
            mpath = config.get_match_ids_path(lg, "2025-2026")
            if mpath.exists():
                man = pd.read_csv(mpath, dtype={"match_id": str, "source_stage_id": str})
                for col in config.MANIFEST_COLUMNS:
                    if col not in man.columns:
                        man[col] = ""
                man = man.fillna("")
                mid_str = man["match_id"].astype(str)
                for match_id, (vh, va, _, _) in validated.items():
                    sel = mid_str == str(match_id)
                    man.loc[sel, "validated_home_team"] = vh
                    man.loc[sel, "validated_away_team"] = va
                    man.loc[sel, "validation_status"] = config.VALIDATION_OK
                for match_id, _, _ in foreign:
                    if int(match_id) in playoff_ids:
                        continue
                    sel = mid_str == str(match_id)
                    man.loc[sel, "validation_status"] = config.VALIDATION_WRONG_COMPETITION
                man.loc[man["match_id"].astype(str).isin({str(i) for i in playoff_ids}),
                        "competition_phase"] = config.PHASE_PROMOTION_PLAYOFF
                man.to_csv(mpath, index=False)
            print(f"    applied: {len(swaps)} swaps, {score_writes} score corrections, "
                  f"{len(playoff_ids)} playoff reclass, {len(wrong_ids)} wrong-comp marks")

    # Leagues outside the truth-feed loop that still need wrong-comp marks
    if args.apply:
        for lg, wrong_ids in WRONG_COMP.items():
            if lg in LEAGUES:
                continue
            proc = REPO / "data" / "processed" / lg / "2025-2026" / "matches.csv"
            if proc.exists():
                m = ensure_comp_columns(pd.read_csv(proc), lg)
                m.loc[m["match_id"].isin(wrong_ids), "validation_status"] = \
                    config.VALIDATION_WRONG_COMPETITION
                m.to_csv(proc, index=False)
            mpath = config.get_match_ids_path(lg, "2025-2026")
            if mpath.exists():
                man = pd.read_csv(mpath, dtype={"match_id": str, "source_stage_id": str})
                for col in config.MANIFEST_COLUMNS:
                    if col not in man.columns:
                        man[col] = ""
                man = man.fillna("")
                man.loc[man["match_id"].astype(str).isin({str(i) for i in wrong_ids}),
                        "validation_status"] = config.VALIDATION_WRONG_COMPETITION
                man.to_csv(mpath, index=False)
            print(f"{lg}: marked {sorted(wrong_ids)} wrong_competition")

    print()
    print("GRAND TOTAL:", grand)
    print()
    for lg, miss in missing_report.items():
        if miss:
            print(f"{lg} truth matches missing from our data ({len(miss)}):")
            for x in miss[:12]:
                print("   ", x)
            if len(miss) > 12:
                print(f"    ... +{len(miss)-12} more")


if __name__ == "__main__":
    main()
