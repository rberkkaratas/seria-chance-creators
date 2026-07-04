"""
Fixture Audit
-------------
Reports manifest/processed completeness by competition phase without mutating
pipeline inputs.

Usage:
    python -m src.processing.fixture_audit --season 2025-2026 --competition all
    python -m src.processing.fixture_audit --season 2025-2026 --competition Belgium_Pro_League
"""

import argparse

import numpy as np
import pandas as pd

import config


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Audit fixture manifest and processed match completeness"
    )
    parser.add_argument(
        "--season",
        default=config.SEASON,
        help="Season string, e.g. 2025-2026 (default: %(default)s)",
    )
    parser.add_argument(
        "--competition",
        action="append",
        default=None,
        help="Competition key to audit (repeatable). Use all or omit for domestic leagues.",
    )
    return parser.parse_args()


def _resolve_competitions(competitions: list[str] | None) -> list[str]:
    if not competitions or "all" in competitions:
        return list(config.LEAGUES.keys())
    return competitions


def _normalize_manifest(df: pd.DataFrame, competition_key: str) -> pd.DataFrame:
    df = df.copy()
    for col in config.MANIFEST_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["match_id"] = df["match_id"].astype(str)
    df["scraped"] = df["scraped"].fillna(False).astype(bool)

    # Scrub CSV round-trip artifacts (float NaN → "nan", stage id → "24580.0")
    # so audit phase classification never keys on corrupted strings.
    for col in config.MANIFEST_COLUMNS:
        if col in ("match_id", "scraped"):
            continue
        df[col] = df[col].fillna("").astype(str).replace("nan", "")
    df["source_stage_id"] = df["source_stage_id"].str.replace(r"\.0$", "", regex=True)

    competition = config.COMPETITIONS.get(competition_key, {})
    df["competition_key"] = df["competition_key"].replace("", pd.NA).fillna(competition_key)
    df["competition_type"] = df["competition_type"].replace("", pd.NA).fillna(
        competition.get("competition_type", config.COMPETITION_TYPE_DOMESTIC)
    )
    df["competition_phase"] = df["competition_phase"].replace("", pd.NA).fillna(
        config.PHASE_REGULAR_SEASON
    )
    df["validation_status"] = df["validation_status"].replace("", pd.NA).fillna(
        config.VALIDATION_PENDING
    )
    return df[config.MANIFEST_COLUMNS]


def _load_manifest(competition_key: str, season: str) -> pd.DataFrame:
    path = config.get_match_ids_path(competition_key, season)
    if not path.exists():
        return pd.DataFrame(columns=config.MANIFEST_COLUMNS)
    return _normalize_manifest(
        pd.read_csv(path, dtype={"match_id": str, "source_stage_id": str}),
        competition_key,
    )


def _ensure_match_columns(df: pd.DataFrame, competition_key: str) -> pd.DataFrame:
    df = df.copy()
    defaults = {
        "competition_key": competition_key,
        "competition_type": config.COMPETITION_TYPE_DOMESTIC,
        "competition_phase": config.PHASE_REGULAR_SEASON,
        "phase_table_scope": config.TABLE_SCOPE_REGULAR,
        "validation_status": config.VALIDATION_PENDING,
    }
    for col, value in defaults.items():
        if col not in df.columns:
            df[col] = value
        else:
            df[col] = df[col].replace("", pd.NA).fillna(value)
    df["match_id"] = df["match_id"].astype(str)
    return df


def _load_matches(competition_key: str, season: str) -> pd.DataFrame:
    path = config.get_processed_path(competition_key, season) / "matches.csv"
    if not path.exists():
        return pd.DataFrame()
    return _ensure_match_columns(pd.read_csv(path, dtype={"match_id": str}), competition_key)


def _load_scored_team_keys(season: str) -> set[str]:
    for filename in (
        f"all_leagues_{season}_enriched.csv",
        f"all_leagues_{season}.csv",
    ):
        path = config.DATA_FINAL / filename
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if {"league", "team_id"}.issubset(df.columns):
            team_ids = pd.to_numeric(df["team_id"], errors="coerce").astype("Int64").astype(str)
            return set(df["league"].astype(str) + "||" + team_ids)
    return set()


def _team_key(df: pd.DataFrame, team_col: str) -> pd.Series:
    team_ids = pd.to_numeric(df[team_col], errors="coerce").astype("Int64").astype(str)
    return df["league"].astype(str) + "||" + team_ids


def _wrong_competition_match_ids(matches: pd.DataFrame, scored_team_keys: set[str]) -> set[str]:
    if matches.empty or not scored_team_keys:
        return set()
    required = {"league", "home_team_id", "away_team_id", "match_id"}
    if not required.issubset(matches.columns):
        return set()
    home_valid = _team_key(matches, "home_team_id").isin(scored_team_keys)
    away_valid = _team_key(matches, "away_team_id").isin(scored_team_keys)
    explicit_wrong = matches["validation_status"] == config.VALIDATION_WRONG_COMPETITION
    wrong = explicit_wrong | ~(home_valid & away_valid)
    return set(matches.loc[wrong, "match_id"].astype(str))


def _team_match_min_max(matches: pd.DataFrame) -> tuple[float, float]:
    if matches.empty:
        return np.nan, np.nan
    rows = []
    for row in matches.itertuples(index=False):
        if pd.notna(getattr(row, "home_score", np.nan)) and pd.notna(getattr(row, "away_score", np.nan)):
            rows.append(getattr(row, "home_team_name", ""))
            rows.append(getattr(row, "away_team_name", ""))
    if not rows:
        return np.nan, np.nan
    counts = pd.Series(rows).value_counts()
    return float(counts.min()), float(counts.max())


def _completeness_status(
    expected_matches: int | None,
    processed_count: int,
    pending_count: int,
    wrong_count: int,
) -> str:
    if wrong_count:
        return "invalid_matches"
    if expected_matches is not None and processed_count >= expected_matches and pending_count == 0:
        return "complete"
    if processed_count == 0 and pending_count == 0:
        return "missing"
    return "incomplete"


def build_fixture_audit(
    season: str = config.SEASON,
    competitions: list[str] | None = None,
) -> pd.DataFrame:
    competition_keys = _resolve_competitions(competitions)
    scored_team_keys = _load_scored_team_keys(season)
    rows = []

    for competition_key in competition_keys:
        competition = config.COMPETITIONS.get(competition_key, {})
        manifest = _load_manifest(competition_key, season)
        matches = _load_matches(competition_key, season)
        wrong_ids = _wrong_competition_match_ids(matches, scored_team_keys)

        phases = set(competition.get("phases", {config.PHASE_REGULAR_SEASON: {}}))
        phases.update(manifest["competition_phase"].dropna().astype(str).tolist())
        if not matches.empty:
            phases.update(matches["competition_phase"].dropna().astype(str).tolist())

        for phase in sorted(phases):
            phase_cfg = competition.get("phases", {}).get(phase, {})
            man_phase = manifest[manifest["competition_phase"] == phase]
            match_phase = matches[matches["competition_phase"] == phase] if not matches.empty else matches
            processed_ids = set(match_phase["match_id"].astype(str)) if not match_phase.empty else set()
            pending_ids = man_phase.loc[~man_phase["scraped"].astype(bool), "match_id"].astype(str).tolist()
            manifest_ids = set(man_phase["match_id"].astype(str))
            manifest_not_processed = sorted(manifest_ids - processed_ids)
            wrong_phase_ids = sorted(wrong_ids & processed_ids)
            team_min, team_max = _team_match_min_max(match_phase)
            expected_matches = phase_cfg.get("expected_matches")

            rows.append({
                "competition_key": competition_key,
                "competition_type": competition.get("competition_type", config.COMPETITION_TYPE_DOMESTIC),
                "competition_phase": phase,
                "phase_table_scope": phase_cfg.get("table_scope", competition.get("default_table_scope", "")),
                "expected_matches": expected_matches,
                "expected_team_matches": phase_cfg.get("expected_team_matches"),
                "manifest_matches": len(man_phase),
                "processed_matches": len(processed_ids),
                "pending_count": len(pending_ids),
                "pending_ids": " ".join(pending_ids),
                "manifest_not_processed_count": len(manifest_not_processed),
                "manifest_not_processed_ids": " ".join(manifest_not_processed),
                "wrong_competition_count": len(wrong_phase_ids),
                "wrong_competition_ids": " ".join(wrong_phase_ids),
                "team_matches_min": team_min,
                "team_matches_max": team_max,
                "completeness_status": _completeness_status(
                    expected_matches,
                    len(processed_ids) - len(wrong_phase_ids),
                    len(pending_ids),
                    len(wrong_phase_ids),
                ),
            })

    return pd.DataFrame(rows)


def main() -> None:
    args = parse_arguments()
    audit = build_fixture_audit(season=args.season, competitions=args.competition)
    config.DATA_FINAL.mkdir(parents=True, exist_ok=True)
    output_path = config.DATA_FINAL / f"fixture_audit_{args.season}.csv"
    audit.to_csv(output_path, index=False)
    print(f"Saved → {output_path}")
    if not audit.empty:
        print(audit[[
            "competition_key", "competition_phase", "expected_matches",
            "processed_matches", "pending_count", "wrong_competition_count",
            "expected_team_matches", "team_matches_min", "team_matches_max",
            "completeness_status",
        ]].to_string(index=False))


if __name__ == "__main__":
    main()
