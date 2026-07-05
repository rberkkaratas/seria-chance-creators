# World Cup Content Evidence Layer

A small, isolated content-support layer for turning **manual per-match fullback
observation tags** into a short-video **content pack**. It exists to back one
editorial claim for the "Sahanın Dili" Monday vertical video:

> The modern fullback is no longer just the player who gives width on the
> touchline; in tournament matches they carry central support, transition
> security and direction-changing at the same time.

It lives entirely in `src/features/content_evidence.py` and reads only its own
observation CSV. It does **not** touch the player, team, merge, or enrichment
pipelines, and it reads nothing from `config`.

## Why it exists

SquadLens has no World Cup data yet, and building a full tournament scraper is
out of scope. But the video needs *evidence* — freeze frames, clip references,
counts and shares — organised around a claim about how fullbacks play in
tournaments. This layer is the smallest testable thing that produces that
evidence: a human tags scenes while watching matches, the layer aggregates and
ranks them, and writes a pack a video editor can lift into a brief.

It is intentionally an MVP: today the input is hand-filled, but the same schema
can later be populated from event data without changing the summary/export
code.

## How it differs from the main scouting scores

| Main scores (`player_features`, `merge_leagues`, `team_features`) | Content evidence layer |
|---|---|
| 0–100 role scores + overall quality percentiles | No quality score at all |
| Cross-league, season-long, minutes-weighted | Single-match, per-observation tags |
| Derived from scraped WhoScored events | Hand-filled (or later event-fed) observation tags |
| Feeds the analytics dashboard | Feeds a short-video content brief |
| Reads `config.POSITION_GROUPS` role weights | Fully isolated; no config import |

The FB role *names* (Defensive / Attacking / Inverted / Crossing Fullback) are
only a conceptual reference here. This layer classifies a **content role
context** (`inverted_fullback_context`, `attacking_fullback_context`,
`rest_defense_fullback_context`, `balanced_fullback_context`) from tagged
behaviour shares — it does not reuse or reproduce the config role definitions.

## Safety / methodology boundaries

This layer:

- does **not** produce a player overall quality score,
- does **not** produce a World Cup performance ranking,
- does **not** produce xG / xA or any expected-value model,
- does **not** analyse goalkeepers,
- does **not** generalise a single-match observation to season-long quality,
- is content **support**, not a scouting decision.

Every generated pack ends with a printed risk note repeating this.

## The observation schema

Production file (git-ignored by convention, you create it):

```
data/content_evidence/world_cup_2026/fullback_observations.csv
```

A synthetic, enum-clean example ships as
`fullback_observations.sample.csv` in the same folder (real names avoided;
teams/players are labelled "Sample …"). The tests bind to the sample; the
production CLI expects the real file.

One row = one tagged in-match action. Columns:

`observation_id, match_id, match_date, competition, stage, team, opponent,
player_name, player_id_optional, side, minute, phase, game_state, x, y, end_x,
end_y, possession_context, fullback_lane, fullback_behavior, support_role,
transition_role, action_type, outcome, evidence_strength, clip_ref,
freeze_frame_note, content_note`

Categorical columns are enum-validated (a value outside the enum is a **hard
error**, not a warning):

- **phase**: `build_up, progression, final_third, rest_defense, defensive_transition, settled_defense`
- **game_state**: `level, leading, trailing, extra_time, unknown`
- **fullback_lane**: `touchline, wide_channel, half_space, central, back_line, unknown`
- **fullback_behavior**: `overlap, underlap, inverted_support, width_holding, rest_defense_cover, recovery_run, crossing_action, progressive_carry, progressive_pass, recycle, unknown`
- **support_role**: `width_provider, midfield_support, third_man_option, switch_receiver, counterpress_cover, none, unknown`
- **transition_role**: `first_pressure, cover_shadow, rest_defense, recovery, second_ball, none, unknown`
- **action_type**: `pass, carry, cross, reception, defensive_action, positioning, shot_assist, reset, unknown`
- **outcome**: `positive, neutral, negative, unknown`
- **evidence_strength**: `1, 2, 3` (3 = clearest hero-clip evidence)

`clip_ref` and `freeze_frame_note` should point at a real clip/timestamp and
describe what the freeze frame shows — they go straight into the pack.

## How to fill the schema

1. Watch a match. Every time a fullback does something that supports (or
   contradicts) the claim, add a row.
2. Tag the **lane** (where on the pitch), the **behaviour** (what they did),
   the **support_role** / **transition_role** (in/out of possession function),
   the **phase** and **game_state**.
3. Set **evidence_strength** honestly: `3` only for scenes you would actually
   cut into the video.
4. Fill **freeze_frame_note** and **clip_ref** so an editor can find the frame.
5. Keep it single-match honest — do not tag a season narrative onto one game.

## Producing the content pack for the Monday video

```bash
python -m src.features.content_evidence \
    --input data/content_evidence/world_cup_2026/fullback_observations.csv \
    --competition World_Cup_2026 \
    --output output/content_packs/world_cup_2026/fullback_content_pack.md
```

Optional narrowing (any combination):

```bash
python -m src.features.content_evidence --input <csv> \
    --competition World_Cup_2026 \
    --match-id WC26_M1 --team "Team X" --player "Player Y" \
    --output output/content_packs/world_cup_2026/fullback_content_pack.md
```

Each run writes **two** files to the output directory:

- `fullback_content_pack.md` — the human-readable brief (claim, filter, three
  hero evidence scenes, three headline numbers, per-player profiles, risk note),
- `fullback_content_summary.csv` — the per-(match, team, player) metric table.

## Summary metrics (per match × team × player)

`observations, inverted_support_count, width_holding_count,
overlap_underlap_count, rest_defense_cover_count, progressive_action_count,
final_third_action_count, transition_cover_count, central_or_halfspace_share,
average_evidence_strength`, plus `primary_content_role`, `strongest_behavior`,
`content_angle`, and the strongest scene's `best_freeze_frame_note` /
`best_clip_ref`.

`primary_content_role` is a deterministic classification with named thresholds
at the top of the module (`CENTRAL_SHARE_THRESHOLD`,
`INVERTED_BEHAVIOR_SHARE_THRESHOLD`, `ATTACKING_SHARE_THRESHOLD`,
`REST_DEFENSE_SHARE_THRESHOLD`):

- **inverted_fullback_context** — inverted-support share high, or central/
  half-space lane share high.
- **attacking_fullback_context** — overlap/underlap/progressive-carry/cross or
  final-third action share high.
- **rest_defense_fullback_context** — rest-defense-cover or transition-cover
  share high.
- **balanced_fullback_context** — nothing dominates.

## Claims you can and cannot build

**Can build** (supported by tagged evidence):

- "In this match, X% of this fullback's tagged actions were central or in the
  half-space" (from `central_or_halfspace_share`).
- "This fullback showed inverted support / rest-defense cover / overlaps in
  this specific match" (with the clip refs to prove it).
- "Across these tagged matches, fullbacks combined width, central support and
  transition cover" — the qualitative claim the video is built around.

**Cannot build** (out of scope, do not imply):

- "This is the best fullback at the World Cup" (no ranking).
- "This fullback is elite / worth £Xm" (no quality score, no market value).
- "This player creates Y xA per game" (no expected-value model).
- Anything about goalkeepers.
- Any generalisation from one match to season-long quality.

## Output directory note

`output/` is **not** currently in `.gitignore`. If generated content packs
should not be committed, add `output/` to `.gitignore`. This layer creates its
output directories at runtime.
