"""
Content Evidence — SquadLens World Cup Content Support Layer
------------------------------------------------------------
An isolated, manually-driven layer that turns per-match fullback observation
tags into a compact "content pack" for short-form video production. It exists
to support a specific editorial claim:

    "The modern fullback is no longer just the player who gives width on the
    touchline; in tournament matches they carry central support, transition
    security and direction-changing at the same time."

WHAT THIS IS
    A deterministic pipeline over a hand-filled observation CSV. Each row is a
    single tagged in-match action (an overlap, an inverted step, a rest-defense
    cover, a recovery run, ...) with an evidence strength, a clip reference and
    a freeze-frame note. The layer summarises those tags per
    (match_id, team, player_name), picks the top evidence scenes, and writes a
    Markdown pack that can be dropped straight into a vertical-video brief.

WHAT THIS IS NOT (safety / methodology boundaries)
    - It does NOT produce a player overall quality score.
    - It does NOT produce a World Cup performance ranking.
    - It does NOT produce xG / xA or any expected-value model.
    - It does NOT analyse goalkeepers.
    - It does NOT generalise a single-match observation to season-long quality.
    - Its output is content SUPPORT, not a scouting decision.

The layer is fully isolated: it reads nothing from config, the player pipeline,
the team pipeline or the merged score files. It only reads its own observation
CSV. This keeps the editorial content path decoupled from the analytics scores.

Usage:
    python -m src.features.content_evidence \\
        --input data/content_evidence/world_cup_2026/fullback_observations.csv \\
        --competition World_Cup_2026 \\
        --output output/content_packs/world_cup_2026/fullback_content_pack.md

    # optional narrowing
    python -m src.features.content_evidence --input <csv> \\
        --competition World_Cup_2026 --match-id WC26_M1 --team "Team X" \\
        --player "Player Y" --output <md>

Both a summary CSV (fullback_content_summary.csv, next to the output Markdown)
and the Markdown pack are written on every run.
"""

import argparse
from pathlib import Path

import pandas as pd

# ─── Schema ──────────────────────────────────────────────────────────

REQUIRED_COLUMNS: list[str] = [
    "observation_id",
    "match_id",
    "match_date",
    "competition",
    "stage",
    "team",
    "opponent",
    "player_name",
    "player_id_optional",
    "side",
    "minute",
    "phase",
    "game_state",
    "x",
    "y",
    "end_x",
    "end_y",
    "possession_context",
    "fullback_lane",
    "fullback_behavior",
    "support_role",
    "transition_role",
    "action_type",
    "outcome",
    "evidence_strength",
    "clip_ref",
    "freeze_frame_note",
    "content_note",
]

# Allowed values per categorical column. Enum violations are a hard error so a
# mistyped tag never silently changes a count. Free-text and coordinate columns
# are intentionally absent from this map.
ENUM_COLUMNS: dict[str, set[str]] = {
    "phase": {
        "build_up", "progression", "final_third",
        "rest_defense", "defensive_transition", "settled_defense",
    },
    "game_state": {"level", "leading", "trailing", "extra_time", "unknown"},
    "fullback_lane": {
        "touchline", "wide_channel", "half_space",
        "central", "back_line", "unknown",
    },
    "fullback_behavior": {
        "overlap", "underlap", "inverted_support", "width_holding",
        "rest_defense_cover", "recovery_run", "crossing_action",
        "progressive_carry", "progressive_pass", "recycle", "unknown",
    },
    "support_role": {
        "width_provider", "midfield_support", "third_man_option",
        "switch_receiver", "counterpress_cover", "none", "unknown",
    },
    "transition_role": {
        "first_pressure", "cover_shadow", "rest_defense",
        "recovery", "second_ball", "none", "unknown",
    },
    "action_type": {
        "pass", "carry", "cross", "reception", "defensive_action",
        "positioning", "shot_assist", "reset", "unknown",
    },
    "outcome": {"positive", "neutral", "negative", "unknown"},
    "evidence_strength": {"1", "2", "3"},
}

# ─── Classification thresholds (deterministic, tunable) ──────────────
# All shares are computed against a player's own observation count in the group.

# central_or_halfspace_share at/above this marks a central-tilt fullback.
CENTRAL_SHARE_THRESHOLD: float = 0.40

# Share of inverted-support behaviour at/above this marks inverted context.
INVERTED_BEHAVIOR_SHARE_THRESHOLD: float = 0.30

# Share of attacking behaviour (overlap/underlap/progressive carry/cross) or
# final-third actions at/above this marks attacking context.
ATTACKING_SHARE_THRESHOLD: float = 0.30

# Share of rest-defense / transition-cover actions at/above this marks
# rest-defense context.
REST_DEFENSE_SHARE_THRESHOLD: float = 0.30

# Behaviours counted as "attacking" for role classification.
ATTACKING_BEHAVIORS: set[str] = {
    "overlap", "underlap", "progressive_carry", "crossing_action",
}
# Behaviours counted as "overlap/underlap" for the summary counter.
OVERLAP_UNDERLAP_BEHAVIORS: set[str] = {"overlap", "underlap"}
# Lanes counted as central-tilt for central_or_halfspace_share.
CENTRAL_LANES: set[str] = {"central", "half_space"}
# Transition_role values that count as transition cover.
TRANSITION_COVER_ROLES: set[str] = {
    "first_pressure", "cover_shadow", "rest_defense", "recovery",
}

# Minimum evidence_strength for a scene to enter the top-evidence selection.
DEFAULT_MIN_STRENGTH: int = 2
# Number of hero evidence scenes surfaced in the content pack.
TOP_EVIDENCE_SCENES: int = 3

# User-facing pack text is Turkish: the pack feeds the "Sahanın Dili"
# vertical-video brief directly. Enum values stay English (schema language).
CONTENT_CLAIM: str = (
    "Modern bek artık sadece çizgide genişlik veren oyuncu değil; turnuva "
    "maçlarında merkeze destek, geçiş güvenliği ve yön değiştirme rolünü "
    "aynı anda taşıyan oyuncu."
)

RISK_NOTE: str = (
    "Bu output maç içi gözlem etiketlerinden gelir; oyuncunun genel kalite "
    "puanı değildir. İçerik desteğidir, scouting kararı değildir; tek maçlık "
    "örneklem sezonluk kaliteye genellenemez."
)

# Turkish display names for behaviour enums (voiceover/on-screen text only).
BEHAVIOR_TR: dict = {
    "overlap": "bindirme (overlap)",
    "underlap": "iç bindirme (underlap)",
    "inverted_support": "içe katılıp merkez desteği",
    "width_holding": "genişlik tutma",
    "rest_defense_cover": "geçiş güvenliği (rest defense)",
    "recovery_run": "geri koşu",
    "crossing_action": "orta aksiyonu",
    "progressive_carry": "ileri taşıma",
    "progressive_pass": "ileri pas",
    "recycle": "topu döndürme",
    "unknown": "bilinmeyen davranış",
}


class ContentEvidenceValidationError(ValueError):
    """Raised when the observation frame is missing columns or has bad enums."""


# ─── Load / validate ─────────────────────────────────────────────────

def load_fullback_observations(path: str | Path) -> pd.DataFrame:
    """Read a fullback observation CSV as strings-first (enum-safe) frame."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Observation CSV not found: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    print(f"  Loaded {len(df)} observation(s) from {path.name}")
    return df


def validate_fullback_observations(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate schema and enum membership. Missing required columns or any value
    outside its enum raises ContentEvidenceValidationError with a clear message.
    Returns the frame unchanged (typed helpers are computed downstream).
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ContentEvidenceValidationError(
            "Observation CSV is missing required column(s): "
            + ", ".join(missing)
        )

    if df.empty:
        raise ContentEvidenceValidationError(
            "Observation CSV has no rows to summarise."
        )

    problems: list[str] = []
    for col, allowed in ENUM_COLUMNS.items():
        values = df[col].astype(str).str.strip()
        bad = sorted(set(values[~values.isin(allowed)]) - {""})
        if bad:
            problems.append(
                f"column '{col}' has value(s) outside the allowed enum: "
                + ", ".join(bad)
            )
    if problems:
        raise ContentEvidenceValidationError(
            "Enum validation failed:\n  - " + "\n  - ".join(problems)
        )

    print(f"  Validated {len(df)} observation(s): schema + enums OK")
    return df


# ─── Summary ─────────────────────────────────────────────────────────

def _classify_primary_content_role(
    central_share: float,
    inverted_share: float,
    attacking_share: float,
    rest_defense_share: float,
) -> str:
    """
    Deterministic role classification from behaviour shares.

    Priority (most specific first):
      1. inverted_fullback_context   — inverted support / central-tilt heavy
      2. attacking_fullback_context  — overlap/underlap/carry/cross/final-third
      3. rest_defense_fullback_context — rest-defense / transition-cover heavy
      4. balanced_fullback_context   — nothing dominates
    """
    inverted_hit = (
        inverted_share >= INVERTED_BEHAVIOR_SHARE_THRESHOLD
        or central_share >= CENTRAL_SHARE_THRESHOLD
    )
    attacking_hit = attacking_share >= ATTACKING_SHARE_THRESHOLD
    rest_defense_hit = rest_defense_share >= REST_DEFENSE_SHARE_THRESHOLD

    # Resolve by the strongest signal when multiple fire, but keep the
    # documented priority as the tie-breaker.
    if inverted_hit and inverted_share >= max(attacking_share, rest_defense_share):
        return "inverted_fullback_context"
    if attacking_hit and attacking_share >= rest_defense_share:
        return "attacking_fullback_context"
    if rest_defense_hit:
        return "rest_defense_fullback_context"
    if inverted_hit:
        return "inverted_fullback_context"
    if attacking_hit:
        return "attacking_fullback_context"
    return "balanced_fullback_context"


def _strongest_behavior(group: pd.DataFrame) -> str:
    """Most frequent non-'unknown' behaviour; falls back to the mode."""
    behaviors = group["fullback_behavior"].astype(str)
    named = behaviors[behaviors != "unknown"]
    pool = named if not named.empty else behaviors
    counts = pool.value_counts()
    if counts.empty:
        return "unknown"
    return str(counts.index[0])


def _content_angle(role: str) -> str:
    """One-line editorial angle keyed off the primary content role."""
    return {
        "inverted_fullback_context": (
            "Bek merkez desteği olarak: içe katılıp sayısal üstünlük kuruyor "
            "ve oyunun yönünü iç koridordan değiştiriyor."
        ),
        "attacking_fullback_context": (
            "Bek hücum genişliği ve ilerletme olarak: bindirme, iç bindirme "
            "ve son üçlükte çizgi kıran taşımalar."
        ),
        "rest_defense_fullback_context": (
            "Bek geçiş sigortası olarak: rest-defense yapısını tutuyor ve top "
            "kaybında ilk güvenlik hattını kuruyor."
        ),
        "balanced_fullback_context": (
            "Bek hibrit profil olarak: aynı maçta genişlik, merkez desteği ve "
            "geçiş güvenliğini karıştırıyor."
        ),
    }.get(role, "Etiketlenen gözlemlerden bek rol profili.")


def build_fullback_content_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate observations to one row per (match_id, team, player_name).

    Returns a deterministically sorted frame with count metrics, shares, the
    classified primary_content_role, the strongest behaviour, an editorial
    angle, and the best (strongest-evidence) freeze-frame note and clip ref.
    """
    df = df.copy()
    df["evidence_strength_num"] = pd.to_numeric(
        df["evidence_strength"], errors="coerce"
    ).fillna(0).astype(int)

    group_cols = ["match_id", "team", "player_name"]
    rows: list[dict] = []

    for keys, group in df.groupby(group_cols, sort=True):
        match_id, team, player_name = keys
        n = len(group)

        behavior = group["fullback_behavior"].astype(str)
        lane = group["fullback_lane"].astype(str)
        phase = group["phase"].astype(str)
        transition = group["transition_role"].astype(str)

        inverted_support_count = int((behavior == "inverted_support").sum())
        width_holding_count = int((behavior == "width_holding").sum())
        overlap_underlap_count = int(behavior.isin(OVERLAP_UNDERLAP_BEHAVIORS).sum())
        rest_defense_cover_count = int((behavior == "rest_defense_cover").sum())
        progressive_action_count = int(
            behavior.isin({"progressive_carry", "progressive_pass"}).sum()
        )
        final_third_action_count = int((phase == "final_third").sum())
        transition_cover_count = int(transition.isin(TRANSITION_COVER_ROLES).sum())
        central_or_halfspace_count = int(lane.isin(CENTRAL_LANES).sum())
        central_or_halfspace_share = round(central_or_halfspace_count / n, 4)
        average_evidence_strength = round(
            float(group["evidence_strength_num"].mean()), 4
        )

        inverted_share = inverted_support_count / n
        attacking_count = int(behavior.isin(ATTACKING_BEHAVIORS).sum())
        attacking_share = max(attacking_count, final_third_action_count) / n
        rest_defense_share = (
            max(rest_defense_cover_count, transition_cover_count) / n
        )

        primary_content_role = _classify_primary_content_role(
            central_share=central_or_halfspace_share,
            inverted_share=inverted_share,
            attacking_share=attacking_share,
            rest_defense_share=rest_defense_share,
        )
        strongest_behavior = _strongest_behavior(group)
        content_angle = _content_angle(primary_content_role)

        # Best scene = highest evidence_strength, earliest minute as tie-break.
        best = group.sort_values(
            ["evidence_strength_num", "minute"], ascending=[False, True]
        ).iloc[0]

        rows.append({
            "competition": str(group["competition"].iloc[0]),
            "stage": str(group["stage"].iloc[0]),
            "match_id": str(match_id),
            "team": str(team),
            "opponent": str(group["opponent"].iloc[0]),
            "player_name": str(player_name),
            "side": str(group["side"].iloc[0]),
            "observations": n,
            "inverted_support_count": inverted_support_count,
            "width_holding_count": width_holding_count,
            "overlap_underlap_count": overlap_underlap_count,
            "rest_defense_cover_count": rest_defense_cover_count,
            "progressive_action_count": progressive_action_count,
            "final_third_action_count": final_third_action_count,
            "transition_cover_count": transition_cover_count,
            "central_or_halfspace_share": central_or_halfspace_share,
            "average_evidence_strength": average_evidence_strength,
            "primary_content_role": primary_content_role,
            "strongest_behavior": strongest_behavior,
            "content_angle": content_angle,
            "best_freeze_frame_note": str(best["freeze_frame_note"]),
            "best_clip_ref": str(best["clip_ref"]),
        })

    summary = pd.DataFrame(rows)
    if not summary.empty:
        summary = summary.sort_values(
            ["match_id", "team", "player_name"], ignore_index=True
        )
    print(f"  Built content summary: {len(summary)} (match, team, player) row(s)")
    return summary


# ─── Evidence selection ──────────────────────────────────────────────

def select_top_fullback_evidence(
    df: pd.DataFrame,
    match_id: str | None = None,
    team: str | None = None,
    player_name: str | None = None,
    min_strength: int = DEFAULT_MIN_STRENGTH,
) -> pd.DataFrame:
    """
    Select the strongest individual evidence scenes, optionally filtered.

    Rows below `min_strength` are dropped. Remaining rows are ranked by
    evidence_strength (desc), then outcome quality (positive first), then
    minute (asc) for deterministic ordering.
    """
    work = df.copy()
    work["evidence_strength_num"] = pd.to_numeric(
        work["evidence_strength"], errors="coerce"
    ).fillna(0).astype(int)
    work["minute_num"] = pd.to_numeric(work["minute"], errors="coerce").fillna(0)

    if match_id is not None:
        work = work[work["match_id"].astype(str) == str(match_id)]
    if team is not None:
        work = work[work["team"].astype(str) == str(team)]
    if player_name is not None:
        work = work[work["player_name"].astype(str) == str(player_name)]

    work = work[work["evidence_strength_num"] >= int(min_strength)]

    outcome_rank = {"positive": 0, "neutral": 1, "unknown": 2, "negative": 3}
    work["outcome_rank"] = work["outcome"].astype(str).map(outcome_rank).fillna(2)

    work = work.sort_values(
        ["evidence_strength_num", "outcome_rank", "minute_num", "observation_id"],
        ascending=[False, True, True, True],
        ignore_index=True,
    )
    return work


# ─── Markdown export ─────────────────────────────────────────────────

def _scene_line(scene: pd.Series) -> list[str]:
    """Render one hero evidence scene as Markdown lines."""
    behavior = str(scene["fullback_behavior"])
    behavior_tr = BEHAVIOR_TR.get(behavior, behavior.replace("_", " "))
    minute = str(scene["minute"])
    on_screen = f"{scene['player_name']} — {behavior_tr} ({minute}')"
    voiceover = (
        f"Burada bek {behavior_tr} davranışını gösteriyor: "
        f"{scene['freeze_frame_note']}."
    )
    return [
        f"- **Freeze-frame:** {scene['freeze_frame_note']}",
        f"  - **Klip ref:** `{scene['clip_ref']}`",
        f"  - **Ekran metni:** {on_screen}",
        f"  - **Voiceover kanıt cümlesi:** {voiceover}",
        f"  - **Gösterdiği rol davranışı:** {behavior} "
        f"(destek: {scene['support_role']}, geçiş: {scene['transition_role']})",
    ]


def _filter_label(match_id, team, player_name) -> str:
    parts = []
    if match_id is not None:
        parts.append(f"match_id={match_id}")
    if team is not None:
        parts.append(f"team={team}")
    if player_name is not None:
        parts.append(f"player={player_name}")
    return ", ".join(parts) if parts else "tüm gözlemler (filtre yok)"


def render_content_pack_markdown(
    summary: pd.DataFrame,
    evidence: pd.DataFrame,
    competition: str,
    filter_label: str,
) -> str:
    """Build the Markdown content pack string from summary + top evidence."""
    lines: list[str] = []
    lines.append("# Dünya Kupası 2026 — Bek İçerik Paketi")
    lines.append("")
    lines.append(f"**Turnuva:** {competition}")
    lines.append(f"**Kullanılan filtre:** {filter_label}")
    lines.append("")
    lines.append("## İçerik iddiası")
    lines.append("")
    lines.append(f"> {CONTENT_CLAIM}")
    lines.append("")

    # Aggregate the three headline numbers across the (filtered) summary.
    if not summary.empty:
        central_share = round(
            float(summary["central_or_halfspace_share"].mean()), 3
        )
        progressive_total = int(summary["progressive_action_count"].sum())
        rest_defense_total = int(summary["rest_defense_cover_count"].sum())
        transition_total = int(summary["transition_cover_count"].sum())
    else:
        central_share = 0.0
        progressive_total = rest_defense_total = transition_total = 0

    lines.append("## Video için üç sayı")
    lines.append("")
    lines.append(
        f"1. **Merkez / iç koridor payı:** %{central_share * 100:.0f} "
        "(etiketlenen bek aksiyonları içinde merkez veya half-space payı)."
    )
    lines.append(
        f"2. **Progressive aksiyonlar:** {progressive_total} ileri taşıma "
        "veya ileri pas etiketlendi."
    )
    lines.append(
        f"3. **Geçiş / rest-defense güvenliği:** {rest_defense_total} "
        f"rest-defense örtmesi ve {transition_total} geçiş-güvenliği aksiyonu "
        "etiketlendi."
    )
    lines.append("")

    lines.append("## Üç ana kanıt sahnesi")
    lines.append("")
    hero = evidence.head(TOP_EVIDENCE_SCENES)
    if hero.empty:
        lines.append(
            "_Mevcut filtrede minimum kanıt gücünü karşılayan sahne yok._"
        )
        lines.append("")
    else:
        for idx, (_, scene) in enumerate(hero.iterrows(), start=1):
            lines.append(f"### Sahne {idx}")
            lines.extend(_scene_line(scene))
            lines.append("")

    lines.append("## Oyuncu içerik profilleri")
    lines.append("")
    for _, row in summary.iterrows():
        lines.append(
            f"- **{row['player_name']}** ({row['team']} vs {row['opponent']}, "
            f"{row['match_id']}) — {row['primary_content_role']}; "
            f"en güçlü davranış: {row['strongest_behavior']}; "
            f"{row['observations']} gözlem."
        )
        lines.append(f"  - {row['content_angle']}")
    lines.append("")

    lines.append("## Risk notu")
    lines.append("")
    lines.append(f"> {RISK_NOTE}")
    lines.append("")

    return "\n".join(lines)


def export_content_pack(
    summary: pd.DataFrame,
    evidence: pd.DataFrame,
    output_path: str | Path,
    competition: str = "World_Cup_2026",
    filter_label: str = "all observations (no filter)",
) -> Path:
    """
    Write the Markdown content pack and the summary CSV.

    The summary CSV is written next to the Markdown as
    fullback_content_summary.csv. Output directories are created at runtime.
    Returns the Markdown path.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    markdown = render_content_pack_markdown(
        summary, evidence, competition, filter_label
    )
    output_path.write_text(markdown, encoding="utf-8")

    summary_csv = output_path.parent / "fullback_content_summary.csv"
    summary.to_csv(summary_csv, index=False)

    print(f"  Wrote content pack:   {output_path}")
    print(f"  Wrote summary CSV:    {summary_csv}")
    return output_path


# ─── CLI ─────────────────────────────────────────────────────────────

def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Build a fullback content-evidence pack from manual observation "
            "tags (content support only — not a scouting score)."
        )
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to the fullback observation CSV.",
    )
    parser.add_argument(
        "--competition", default="World_Cup_2026",
        help="Competition label for the pack header (default: %(default)s).",
    )
    parser.add_argument("--match-id", default=None, help="Optional match_id filter.")
    parser.add_argument("--team", default=None, help="Optional team filter.")
    parser.add_argument("--player", default=None, help="Optional player_name filter.")
    parser.add_argument(
        "--min-strength", type=int, default=DEFAULT_MIN_STRENGTH,
        help="Minimum evidence_strength for a hero scene (default: %(default)s).",
    )
    parser.add_argument(
        "--output",
        default="output/content_packs/world_cup_2026/fullback_content_pack.md",
        help="Output Markdown path (summary CSV is written alongside it).",
    )
    return parser.parse_args()


def run_content_evidence(
    input_path: str | Path,
    output_path: str | Path,
    competition: str = "World_Cup_2026",
    match_id: str | None = None,
    team: str | None = None,
    player_name: str | None = None,
    min_strength: int = DEFAULT_MIN_STRENGTH,
) -> Path:
    """End-to-end: load → validate → summarise → select → export."""
    df = load_fullback_observations(input_path)
    validate_fullback_observations(df)

    scoped = df.copy()
    if match_id is not None:
        scoped = scoped[scoped["match_id"].astype(str) == str(match_id)]
    if team is not None:
        scoped = scoped[scoped["team"].astype(str) == str(team)]
    if player_name is not None:
        scoped = scoped[scoped["player_name"].astype(str) == str(player_name)]

    summary = build_fullback_content_summary(scoped)
    evidence = select_top_fullback_evidence(
        df,
        match_id=match_id,
        team=team,
        player_name=player_name,
        min_strength=min_strength,
    )
    label = _filter_label(match_id, team, player_name)
    return export_content_pack(
        summary, evidence, output_path,
        competition=competition, filter_label=label,
    )


def main():
    args = parse_arguments()
    print("Building fullback content-evidence pack...")
    run_content_evidence(
        input_path=args.input,
        output_path=args.output,
        competition=args.competition,
        match_id=args.match_id,
        team=args.team,
        player_name=args.player,
        min_strength=args.min_strength,
    )
    print("Done.")


if __name__ == "__main__":
    main()
