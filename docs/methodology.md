# Methodology

## The Question This System Is Built to Answer

Clubs waste enormous time and money on signings that fail because the player looked good on the eye but didn't fit the system. A creative midfielder who thrives as a free 8 is a liability in a double-pivot. A box-to-box workhorse will look anonymous in a team that demands a deep builder.

The standard response has been to throw more video at the problem. This system takes a different approach: before any video is pulled, define precisely what you need, score every eligible player against that definition, and rank them. The output is not "the best midfielder" — a meaningless category. It is the best Creator who is under 26, playing in Serie A, and out of contract within 18 months.

---

## Data Sources

### Match Event Data — WhoScored

Every pass, shot, tackle, dribble and aerial contest in every match produces a timestamped event with a player ID, event type, outcome, x/y coordinates, and a list of qualifiers that describe the event's characteristics. This system extracts that raw event stream from WhoScored for all five top European leagues across the 2025/26 season.

**Why WhoScored?** Following FBref's loss of Opta data access, WhoScored remains one of the few publicly accessible sources of granular match event data — including pass types, defensive action coordinates, and carry proxies — without a commercial license.

Data is extracted via a SeleniumBase UC-mode browser (to navigate WhoScored's anti-bot protections), parsed from the embedded `matchCentreData` JSON object in the page source, and saved as per-match CSV files. Fixture URLs contain season-specific IDs and must be updated once per season in `config.py`.

### Transfer Data — Transfermarkt

Market value, contract expiry, and transfer feasibility come from Transfermarkt squad pages. The same SeleniumBase scraper handles this layer, with results cached locally in `data/enrichment/tm_squads_cache.csv` so scraping only re-runs when explicitly refreshed.

**Player name matching** between WhoScored and Transfermarkt uses rapidfuzz `token_set_ratio` with a confidence threshold of 85%. Matches above the threshold are auto-confirmed; borderline cases are logged in `data/enrichment/tm_player_mapping.csv` for manual review. Players not found on any squad page (mid-season transfers, loan gaps) can be added via `data/enrichment/tm_manual_players.csv`.

**Transfer feasibility tiers** are derived from contract expiry relative to the current season end year (`2026`):

| Tier | Contract remaining | What it means |
|------|--------------------|---------------|
| **Expiring** | ≤ 1 year | Out of contract or final year — free or minimal fee |
| **Mid-term** | 1–2 years | Negotiable window — club may sell rather than lose for free |
| **Locked** | 2+ years | Premium buy-out required |

---

## Player Selection

**Positions included:** AMC, AML, AMR, MC, ML, MR — WhoScored's six midfield and attacking midfield classifications.

**Minimum minutes: 600**, counted only from appearances where the player was classified in one of those six positions.

The position-aware counting is the critical detail. The filter first identifies which match appearances were in a qualifying position, sums only those minutes per player, and qualifies anyone whose midfield-position minutes reach 600. A player who logged 800 minutes as a centre-back and 200 minutes as a central midfielder does not qualify — their midfield sample (200 min) is below the threshold. Without this rule, defenders who occasionally covered in midfield would appear in the rankings and score highly on defensive metrics, contaminating the entire comparison group. A regression test guards this behaviour.

The 600-minute floor (roughly seven full matches) is deliberately low. It keeps the sample large enough to include players returning from injury, squad players who lost their place, and young players breaking through mid-season. The dashboard's sidebar filter allows any user to raise this threshold interactively.

---

## From Events to Metrics

### Step 1 — Event Enrichment

Raw events are boolean-flagged in `build_tables.py`. Each flag corresponds to a specific combination of event type, qualifier, and/or spatial coordinate threshold. The flags that matter for midfielder scoring:

**Type-based flags**

| Flag | Event type |
|------|-----------|
| `is_pass` | Pass |
| `is_take_on` | TakeOn |
| `is_shot` | MissedShots, SavedShot, ShotOnPost, Goal |
| `is_tackle` | Tackle |
| `is_interception` | Interception |
| `is_aerial` | Aerial |
| `is_ball_recovery` | BallRecovery |
| `is_clearance` | Clearance |

**Qualifier-based flags**

WhoScored's qualifier `displayName` strings have undocumented casing inconsistencies. Named constants in `build_tables.py` document the exact strings (`_Q_KEY_PASS = "KeyPass"`, `_Q_THROUGH_BALL = "Throughball"` — not `"ThroughBall"`, `_Q_LONG_BALL = "Longball"`, `_Q_CROSS = "Cross"`). Regression tests guard these casings.

| Flag | Signal |
|------|--------|
| `is_key_pass` | `"KeyPass"` qualifier present |
| `is_through_ball` | `"Throughball"` qualifier present |
| `is_cross` | `"Cross"` qualifier present |
| `is_assist` | See note below |

**Assist detection.** WhoScored's `IntentionalAssist` qualifier appears on *all* key passes — every pass leading to any shot, not just goals — making it equivalent to a key pass flag, not an assist flag. Instead, the pipeline reads `satisfiedEventsTypes`: if event-type 92 (goal) appears in a pass's satisfied events, the pass directly preceded a goal and is counted as an assist. The `IntentionalAssist` qualifier is used only as a fallback when `satisfiedEventsTypes` is absent (e.g. in unit tests).

**Spatial flags** (requires `x`, `y`, `endX`, `endY` coordinates — WhoScored 0–100 scale)

| Flag | Condition |
|------|-----------|
| `is_progressive_pass` | Successful pass where `(100 − endX) ≤ 0.75 × (100 − x)` — end point is ≥ 25% closer to goal |
| `is_pass_into_final_third` | Successful pass: `x < 66.7` and `endX ≥ 66.7` |
| `is_pass_into_penalty_area` | Successful pass: `endX ≥ 83` and `21.1 ≤ endY ≤ 78.9` |
| `is_forward_pass` | Successful pass: `endX > x` |
| `is_penalty_area_touch` | Any event: `x ≥ 83` and `21.1 ≤ y ≤ 78.9` |
| `is_half_space_pass` | Successful pass: `endX ≥ 66` and `(endY < 37 or endY > 63)` |
| `is_possession_won_final_third` | `BallRecovery` event: `x ≥ 66.7` |
| `is_touch_final_third` | Touch event: `x ≥ 66.7` |
| `is_carry_into_final_third` | Inferred — see note below |
| `ball_winning_x_contrib` | `x`-coordinate of each interception or ball recovery (accumulated for averaging) |

**Spatial thresholds summary**

| Zone | Threshold |
|------|-----------|
| Final third | x ≥ 66.7 |
| Penalty area | x ≥ 83 and 21.1 ≤ y ≤ 78.9 |
| Half-spaces | x ≥ 66 and (y < 37 or y > 63) |
| Progressive pass | (100 − endX) ≤ 0.75 × (100 − x) |

**Carry inference.** WhoScored does not log `Carry` events. The pipeline infers carries into the final third from sequential per-player events: a carry is flagged when a player's event is inside the final third (x ≥ 66.7) while their previous event ended outside it (prev_end_x < 66.7), the coordinate gap between them is between 0 and 30 pitch units (consistent with carrying rather than receiving a long pass), the events are in the same match period, and the previous event confirms the player retained the ball (`BallTouch`, `BallRecovery`, or a successful `TakeOn`, `Interception`, or `Tackle`). Successful passes are explicitly excluded — after a player passes, the ball is no longer at their feet.

### Step 2 — Aggregation

Boolean flags are summed across all match appearances into season totals per player. The result is one row per player with columns for every counting stat.

### Step 3 — Per-90 Normalisation

All counting stats are divided by `minutes_played / 90`. A player with zero minutes is excluded from division (NaN propagated).

### Step 4 — Rate Metrics

Six dimensionless rate metrics are computed as ratios — no per-90 division:

| Metric | Formula |
|--------|---------|
| `pass_accuracy` | accurate_passes / total_passes × 100 |
| `dribble_success_rate` | successful_dribbles / total_dribbles × 100 |
| `aerial_win_rate` | aerials_won / aerials_total × 100 |
| `tackle_success_rate` | tackles_successful / tackles × 100 |
| `cross_accuracy` | crosses_successful / crosses × 100 |
| `forward_pass_pct` | forward_passes / total_passes × 100 |

### Step 5 — Derived Composite Metrics

Four additional metrics are constructed from combinations of primitives:

| Metric | Formula | Used for |
|--------|---------|---------|
| `possession_won` | ball_recoveries + tackles_successful + interceptions | Combined defensive recovery volume |
| `possession_won_p90` | possession_won ÷ (minutes/90) | Statistical Profiles tab |
| `ball_winning_height` | ball_winning_x_sum / ball_winning_count | Average x-coordinate of interceptions + ball recoveries — higher = wins ball further up the pitch |
| `shot_creating_actions_p90` | key_passes_p90 + successful_dribbles_p90 | Display metric only — excluded from all scoring |
| `def_actions_p90` | tackles_p90 + interceptions_p90 | Display metric only |
| `direct_creation_p90` | key_passes_p90 + assists_p90 | Display metric only |

`shot_creating_actions_p90` is an approximation (true SCA would require tracking shot-chain ancestry) and is excluded from all role scoring and the composite score because it arithmetically double-counts key passes and dribbles that are already individually represented.

---

## Role Scoring

### The Core Idea

After per-90 metrics are computed, every metric used in any role or in the radar chart is percentile-ranked within the filtered midfielder pool. A player at the 80th percentile on key passes receives 80 as their `key_passes_pct` value. Role scores are then weighted averages of these percentile values.

```
role_score = Σ (metric_pct × metric_weight)
```

Because percentiles range from 0 to 100 and all weight sets sum to 1.0, role scores are bounded [0, 100] by construction. A player who is exactly average on every metric scores 50. If a metric column is missing from the data, the score is rescaled by the sum of weights that were present.

`primary_role` is assigned as the role with the highest score (`argmax` across the four role score columns).

### Dual Percentile Modes

Percentiles are computed in two passes:

- **`{metric}_league_pct`** — ranked within the player's own league. Written by `chance_creation.py` and never overwritten.
- **`{metric}_pct`** — starts as a copy of `_league_pct`. The `merge_leagues.py` step overwrites this column with cross-league (global) percentile ranks across the full ~420-player pool.

Role scores and radar charts in the dashboard are computed from `{metric}_pct`. The sidebar **Percentile mode** toggle switches which values feed that column — Global (default) or Within League.

---

## The Four Role Definitions

All weights are exact values from `config.ROLE_WEIGHTS`. Every weight set sums to 1.0 — enforced by a unit test.

---

### Creator

Delivers the ball into dangerous areas regardless of method — central key passes, wide crosses, through balls, or direct assists. `passes_into_penalty_area_p90` leads because it is the universal measure of dangerous delivery that all creator sub-types share, regardless of whether they work centrally or from wide.

| Metric | Weight |
|--------|--------|
| passes_into_penalty_area_p90 | 30% |
| key_passes_p90 | 25% |
| assists_p90 | 20% |
| crosses_p90 | 15% |
| through_balls_p90 | 10% |

---

### Ball Progressor

Drives the team forward through carrying and dribbling. Defined purely by the *action* — beating opponents and crossing pitch zones with the ball — not by what happens after. Distinct from Box Threat (who arrives in the box to shoot) and Deep Builder (who progresses through passing volume).

| Metric | Weight |
|--------|--------|
| carries_into_final_third_p90 | 40% |
| successful_dribbles_p90 | 30% |
| progressive_passes_p90 | 20% |
| progressive_carries_p90 | 10% |

`progressive_carries_p90` captures ball-carries that advance the ball ≥ 25% closer to goal regardless of whether they cross the final-third line. Together with `carries_into_final_third_p90`, these two metrics cover both the zone-crossing and the direction-of-travel dimensions of ball-carrying.

---

### Box Threat

Lives in and around the penalty area — shoots, creates from proximity, and operates in the final third. Fully separated from the Ball Progressor (how you get there) and the Creator (what pass you deliver). The defining question: does this player consistently appear in the most dangerous area and threaten goal directly?

| Metric | Weight |
|--------|--------|
| penalty_area_touches_p90 | 40% |
| shots_p90 | 35% |
| touches_final_third_p90 | 15% |
| passes_into_penalty_area_p90 | 10% |

`touches_final_third_p90` ensures advanced area operation without overlapping the Ball Progressor's carrying metrics. `passes_into_penalty_area_p90` at low weight rewards Box Threats who also set up teammates from close range.

---

### Deep Builder

Enables the team through passing volume, accuracy, and forward intent. The archetype is a midfielder who sees the whole pitch, moves the ball quickly, and consistently drives the team up the pitch through deliberate passing choices rather than physical carries.

| Metric | Weight |
|--------|--------|
| progressive_passes_p90 | 35% |
| pass_accuracy | 25% |
| total_passes_p90 | 20% |
| forward_pass_pct | 10% |
| key_passes_p90 | 10% |

`forward_pass_pct` separates a genuine builder from a recycler who plays it safe under pressure. `key_passes_p90` at low weight separates a creative deep builder from a pure volume passer — the Kroos vs Busquets distinction.

---

## The Composite Score

The composite `chance_creation_score` (0–100) is computed *from role scores*, not from raw metric percentiles. It is a weighted blend of the four role scores:

| Role | Weight |
|------|--------|
| Creator | 35% |
| Ball Progressor | 25% |
| Box Threat | 25% |
| Deep Builder | 15% |

This score is role-agnostic in output — it rewards any midfielder type — but the weights reflect the degree to which each role directly generates scoring opportunities. Creator output leads because key passes, through balls, and box deliveries are the most direct precursors to goals. Deep Builder trails because build-up play enables rather than directly creates.

The composite score powers the radar chart visualisation, the default sort in the Shortlist tab, and the legacy `chance_creators.csv` file.

---

## The Radar Chart

The radar chart in the Scout Report tab displays eight metrics — one per major creative dimension — covering all four roles without redundancy:

| Metric | Primary role it represents |
|--------|---------------------------|
| passes_into_penalty_area_p90 | Creator |
| key_passes_p90 | Creator |
| crosses_p90 | Creator |
| carries_into_final_third_p90 | Ball Progressor |
| successful_dribbles_p90 | Ball Progressor |
| penalty_area_touches_p90 | Box Threat |
| shots_p90 | Box Threat |
| progressive_passes_p90 | Deep Builder |

Each axis shows the player's percentile rank (0–100) on that metric. Hover reveals both the percentile and the raw per-90 value.

---

## Clustering (Optional)

K-Means clustering (k=3, random state 42) is applied to the eight radar chart metrics after standardisation. This is supplementary — roles are the primary classification system and are not derived from clustering. Cluster assignments are stored in `chance_creators_clustered.csv` and are not required by the dashboard.

---

## Known Limitations

**Context blindness.** Per-90 stats do not capture game state, tactical instruction, or role constraints within a match. A holding midfielder with defensive responsibilities and an advanced 8 with freedom to roam are evaluated on the same absolute scale if they share the `MC` position.

**Opponent quality.** No adjustment is made for opponent strength. Accumulating key passes against relegation-threatened sides counts equally with identical output against top-six clubs. Opponent-adjusted metrics are planned for end of season 2025/26 when full standings are available to tier opponents.

**Carry inference.** Carries into the final third are inferred from coordinate transitions, not logged events. The 0–30 unit gap heuristic handles most cases correctly but may occasionally misidentify a long-pass reception as a carry, or miss a carry where the player's next registered event falls outside the gap window.

**progressive_carries_p90 is a placeholder.** The `is_progressive_carry` flag is set to `False` in the current pipeline version — WhoScored does not log carry events natively and the progressive-carry inference has not been implemented. This column will be zero for all players until implemented. The metric is included in the Ball Progressor role at 10% weight as a designed hook for when this is added.

**WhoScored qualifier casing.** Qualifier `displayName` values have undocumented casing inconsistencies (`"Throughball"` not `"ThroughBall"`). Named constants and regression tests guard these. If WhoScored modifies their casing, the affected metric columns silently drop to zero.

**Positional classification.** WhoScored positions reflect the listed position for that match, not the player's actual tactical role. A nominal `MC` who consistently plays as a holder and one who plays as an advanced 8 are classified identically.

**Sample size.** Single season. Players returning from long-term injury or arriving mid-season may not reach the 600-minute threshold regardless of quality.

**Transfer data coverage.** Players who transfer out of a league mid-season are not on any Transfermarkt squad page and require manual entry.

---

## Future Work

**Opponent-adjusted metrics.** Split per-90 stats by opponent tier (top-6 / mid-table / bottom-half) using final league standings. Planned for end of season 2025/26.

**Progressive carry implementation.** Replace the placeholder `is_progressive_carry = False` with a proper inference based on coordinate transitions — analogous to the current carry-into-final-third detection.

**Expected assists.** With higher-resolution pass end-location data, an xA model could complement raw assist counts.

**Role fit scoring.** Score how well a player fits a specific tactical system — not just a generic role profile, but a defined shape, pressing trigger, and defensive block height.
