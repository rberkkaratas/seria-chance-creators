"""Data loading utilities with Streamlit caching."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

import config


class DataLoader:
    # Ordered list of candidate CSV paths (highest to lowest priority).
    # To add a new source, append to this list — no logic changes needed.
    _CANDIDATE_PATHS = [
        config.DATA_FINAL / f"all_leagues_{config.SEASON}_enriched.csv",
        config.DATA_FINAL / f"all_leagues_{config.SEASON}.csv",
        config.DATA_FINAL / "chance_creators_enriched.csv",
        config.DATA_FINAL / "chance_creators_clustered.csv",
        config.DATA_FINAL / "chance_creators.csv",
    ]

    @staticmethod
    @st.cache_data
    def load() -> pd.DataFrame:
        """Load the final player CSV, trying candidates in priority order."""
        for path in DataLoader._CANDIDATE_PATHS:
            if path.exists():
                return pd.read_csv(path)
        st.error(
            "**Data not found.** Run the pipeline first:\n\n"
            "```bash\n"
            "python -m src.processing.build_tables\n"
            "python -m src.features.chance_creation\n"
            "python -m src.features.merge_leagues     # top-5 leagues\n"
            "python -m src.enrichment.transfermarkt   # optional\n"
            "```"
        )
        st.stop()

    @staticmethod
    @st.cache_data
    def load_raw() -> tuple:
        """Load per-match player stats and match metadata from all available leagues."""
        processed_root = config.ROOT_DIR / "data" / "processed"
        all_players: list[pd.DataFrame] = []
        all_matches: list[pd.DataFrame] = []

        if processed_root.exists():
            for league_dir in sorted(processed_root.iterdir()):
                if not league_dir.is_dir():
                    continue
                for season_dir in sorted(league_dir.iterdir()):
                    if not season_dir.is_dir():
                        continue
                    p_path = season_dir / "players.csv"
                    m_path = season_dir / "matches.csv"
                    if p_path.exists():
                        all_players.append(pd.read_csv(p_path))
                    if m_path.exists():
                        all_matches.append(pd.read_csv(m_path))

        raw_players = pd.concat(all_players, ignore_index=True) if all_players else pd.DataFrame()
        matches = (
            pd.concat(all_matches, ignore_index=True).drop_duplicates(subset="match_id")
            if all_matches else pd.DataFrame()
        )
        return raw_players, matches

    @staticmethod
    def _parse_date(date_int):
        """Parse WhoScored date integer (DDMMYYYY, no leading zero) to datetime."""
        try:
            return pd.to_datetime(str(int(date_int)).zfill(8), format="%d%m%Y")
        except Exception:
            return pd.NaT

    @staticmethod
    def build_match_log(
        player_id: float,
        team_id: int,
        matches_df: pd.DataFrame,
        raw_players_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Build a full-season match log for one player.
        Rows for matches the player didn't appear in are included with status='DNP'.
        """
        if matches_df.empty or raw_players_df.empty:
            return pd.DataFrame()

        # All matches where the player's club appeared
        team_matches = matches_df[
            (matches_df["home_team_id"] == team_id) |
            (matches_df["away_team_id"] == team_id)
        ].copy()
        team_matches["date"] = team_matches["date_str"].apply(DataLoader._parse_date)
        team_matches = team_matches.sort_values("date").reset_index(drop=True)

        # Per-match player stats
        stat_cols = [
            "match_id", "minutes_played", "isFirstEleven", "rating",
            "goals", "assists", "key_passes", "through_balls",
            "successful_dribbles", "crosses", "progressive_passes",
            "shots", "tackles", "interceptions",
        ]
        pid = float(player_id)
        player_rows = raw_players_df[raw_players_df["player_id"] == pid].copy()
        available_stat_cols = [c for c in stat_cols if c in player_rows.columns]
        player_rows = player_rows[available_stat_cols]

        log = team_matches.merge(player_rows, on="match_id", how="left")

        log["is_home"] = log["home_team_id"] == team_id
        log["opponent"] = log.apply(
            lambda r: r["away_team_name"] if r["is_home"] else r["home_team_name"], axis=1
        )
        log["venue"] = log["is_home"].map({True: "H", False: "A"})

        def _score(r):
            if pd.isna(r["home_score"]):
                return "?–?"
            return f"{int(r['home_score'])}–{int(r['away_score'])}"

        def _result(r):
            if pd.isna(r["home_score"]):
                return "?"
            hs, as_ = int(r["home_score"]), int(r["away_score"])
            if r["is_home"]:
                return "W" if hs > as_ else ("D" if hs == as_ else "L")
            return "W" if as_ > hs else ("D" if as_ == hs else "L")

        def _status(r):
            if pd.isna(r.get("minutes_played")):
                return "DNP"
            return "Started" if r.get("isFirstEleven") else "Sub"

        log["score"]  = log.apply(_score, axis=1)
        log["result"] = log.apply(_result, axis=1)
        log["status"] = log.apply(_status, axis=1)

        # Fill counting stats with 0 for DNP rows
        count_cols = ["goals", "assists", "key_passes", "through_balls",
                      "successful_dribbles", "crosses", "progressive_passes",
                      "shots", "tackles", "interceptions"]
        for col in count_cols:
            if col in log.columns:
                log[col] = log[col].fillna(0).astype(int)
        log["minutes_played"] = log["minutes_played"].fillna(0).astype(int)

        return log

    @staticmethod
    def load_last_updated() -> str | None:
        """Return the ISO date string from last_updated.txt, or None if missing."""
        path = config.DATA_FINAL / "last_updated.txt"
        if path.exists():
            return path.read_text().strip()
        return None

    @staticmethod
    def enrich(df: pd.DataFrame) -> pd.DataFrame:
        """Add synthetic shot_creating_actions_p90 if missing."""
        if "shot_creating_actions_p90" not in df.columns:
            if "key_passes_p90" in df.columns and "successful_dribbles_p90" in df.columns:
                df["shot_creating_actions_p90"] = df["key_passes_p90"] + df["successful_dribbles_p90"]
        return df
