# Methodology

## Objective

Profile all qualified midfielders in Serie A 2025/26 across six tactical roles using match event data, producing a scouting tool that a sporting director or head scout can use to identify players by role fit, not just raw output.

Each player receives a 0–100 role score for every role. The `primary_role` is the role with the highest score. A legacy composite chance-creation score is retained for backward compatibility and radar chart display.

## Data Sources

### Match Event Data — WhoScored
Match event data is extracted from WhoScored using a semi-automated pipeline. Match IDs are manually collected for all Serie A 2025/26 fixtures; the pipeline extracts structured event data per match and normalises it into three tables (matches, players, teams).

**Why WhoScored?** Following FBref's loss of Opta access, WhoScored remains one of the few publicly accessible sources of detailed match event data, including pass types, dribble events, and defensive actions.

### Transfer Data — Transfermarkt
Market value, contract expiry, and transfer feasibility are scraped from Transfermarkt team squad pages using SeleniumBase (the same UC-mode browser used for WhoScored). Data is cached locally in `data/enrichment/tm_squads_cache.csv` so scraping only runs on explicit refresh.

Player names are matched between WhoScored and Transfermarkt using fuzzy string matching (rapidfuzz WRatio). Matches above 85% confidence are auto-verified; ambiguous matches are flagged in `data/enrichment/tm_player_mapping.csv` for manual review. Players who transfer out of Serie A mid-season and are no longer on any team's squad page can be added manually via `data/enrichment/tm_manual_players.csv`.

**Transfer feasibility tiers** are derived from contract expiry relative to the current season end year:
- **Expiring** — ≤1 year remaining (out of contract or final year)
- **Mid-term** — 1–2 years remaining (negotiable window)
- **Locked** — 2+ years remaining (premium buy-out required)

## Player Selection

Players are filtered using the following criteria:
- **Positions:** AMC, AML, AMR, MC, ML, MR (midfield and attacking midfield roles)
- **Minimum minutes:** 600+ (approximately 7 full matches) to ensure a meaningful sample while retaining emerging players and those returning from injury
- **League:** Serie A 2025/26 only

**Important:** Minutes are counted only from appearances where the player was classified in a midfield position. A player logging 800 minutes as a centre-back and 200 minutes as a midfielder does not qualify — their midfield sample (200 min) is below the threshold. This prevents defenders who occasionally played in midfield from inflating the rankings.

## Feature Engineering

### Per-90 Normalisation
All counting stats are converted to per-90-minute rates to allow fair comparison between players with different playing time.

### Rate Metrics
Non-counting stats (pass accuracy, tackle success rate, dribble success rate, aerial win rate, cross accuracy, forward pass %) are computed as raw ratios and used directly without per-90 normalisation.

### Metrics Included

**Attacking / chance creation**

| Metric | Type | What it captures |
|--------|------|-----------------|
| Key passes | Per-90 | Passes directly leading to a shot |
| Through balls | Per-90 | Line-breaking passes into space |
| Assists | Per-90 | Direct goal contributions |
| Passes into penalty area | Per-90 | High-value delivery into the box |
| Half-space passes | Per-90 | Deliveries into the most dangerous off-centre attacking zones (x ≥ 66, y < 37 or y > 63) |
| Penalty area touches | Per-90 | Touches inside the opposition box |
| Successful dribbles | Per-90 | Chance creation through individual ball-carrying |
| Carries into final third | Per-90 | Ball carries that cross the final-third line (inferred from sequential event coordinates — see note below) |
| Possession won (att. third) | Per-90 | Possession regained at x ≥ 66.7 — pressing and counter-press output |
| Forward pass % | Rate | Share of total passes directed forward — directional intent |

**Progression**

| Metric | Type | What it captures |
|--------|------|-----------------|
| Progressive passes | Per-90 | Passes moving the ball ≥25% closer to the opponent's goal |
| Total passes | Per-90 | Volume and orchestration |
| Passes into final third | Per-90 | Passes from behind the final-third line to endX ≥ 66.7 |
| Crosses | Per-90 | Deliveries from wide positions |
| Pass accuracy | Rate | Accurate passes as a share of total |
| Cross accuracy | Rate | Accurate crosses as a share of total |

**Defensive**

| Metric | Type | What it captures |
|--------|------|-----------------|
| Tackles | Per-90 | Tackle attempts |
| Tackle success rate | Rate | Successful tackles as a share of total |
| Interceptions | Per-90 | Interception events |
| Ball winning height | Average x-coordinate | Average pitch position when winning the ball — higher = presses further up the pitch |
| Clearances | Per-90 | Clearance events |
| Shots blocked | Per-90 | Blocked shots/passes |
| Aerial duels | Per-90 | Total aerial contest volume |
| Aerial win rate | Rate | Won aerials as a share of total |

**Note on progressive carries:** WhoScored event data does not include a `Carry` event type, so carries cannot be extracted directly. Carries into the final third are instead inferred from sequential per-player event coordinates: when a player's x-coordinate crosses the 66.7 threshold between two consecutive events, the gap between them is ≤ 30 pitch units (consistent with a carry, not a long-pass reception), and the previous event confirms the player retained possession (ball recovery, successful take-on, etc.), a carry is recorded. Passes are explicitly excluded since after passing, the player no longer holds the ball.

**Note on SCA:** Shot-creating actions are approximated as key passes + successful dribbles per 90, and are included as a display metric only. They are excluded from all scoring formulas (composite and role) because they double-count two metrics already represented individually.

**Note on assists:** Assists are derived from WhoScored's `satisfiedEventsTypes` field — a pass is counted as an assist if event-type 92 (goal) appears in its satisfied events, confirming a goal directly followed that pass. The `IntentionalAssist` qualifier is used as a fallback (e.g. in unit tests) but not as the primary signal, because it appears on all passes leading to shots — effectively duplicating key passes — rather than only on those that led to goals.

## Role Scoring

### Overview
All percentile ranks are computed within the filtered midfielder group (not the full dataset). Role scores are then computed as a weighted average of the relevant per-metric percentile ranks, producing a 0–100 score per role per player.

```
role_score = Σ (metric_percentile_rank × metric_weight)
```

`primary_role` is assigned as the role with the highest score. All role weight sets sum to exactly 1.0.

### Role Definitions

**Playmaker**
Directly creates goal-scoring opportunities through key passes, through balls, and penalty area delivery.

| Metric | Weight |
|--------|--------|
| Key passes p90 | 25% |
| Passes into penalty area p90 | 20% |
| Through balls p90 | 15% |
| Assists p90 | 15% |
| Half-space passes p90 | 15% |
| Successful dribbles p90 | 5% |
| Penalty area touches p90 | 5% |

*SCA removed — it is derived from key passes + dribbles and would double-count both at an effective ~37% for key passes and ~18% for dribbles.*

**Ball Progressor**
Advances the team up the pitch through progressive passing and ball-carrying.

| Metric | Weight |
|--------|--------|
| Progressive passes p90 | 40% |
| Carries into final third p90 | 20% |
| Forward pass % | 15% |
| Total passes p90 | 15% |
| Pass accuracy | 10% |

*Passes into final third removed — it is a near-duplicate of progressive passes. Forward pass % raised because directional intent is the defining trait of a progressor; pass accuracy reduced to prevent safe, sideways passers scoring highly.*

**Ball Winner**
Recovers possession and disrupts opponents through tackles, interceptions, and pressing.

| Metric | Weight |
|--------|--------|
| Interceptions p90 | 30% |
| Tackles p90 | 25% |
| Tackle success rate | 25% |
| Possession won (att. third) p90 | 10% |
| Ball winning height | 10% |

*Possession won (combined) removed — it is a composite of tackles successful + interceptions + recoveries, which would triple-count metrics already represented individually. Interceptions raised to 30%: reading the game is the primary Ball Winner trait.*

**Defensive Shield**
Protects the defensive line through aerial dominance, clearances, and shot-blocking.

| Metric | Weight |
|--------|--------|
| Aerial win rate | 30% |
| Clearances p90 | 25% |
| Interceptions p90 | 15% |
| Aerial duels p90 | 15% |
| Shots blocked p90 | 15% |

*Aerial win rate raised above volume: dominance matters more than aerial contest count. Interceptions added to capture the positional awareness of a true shield. Shots blocked reduced — primarily a centre-back behaviour; high weight risks mis-classifying deep-lying CBs who occasionally play in midfield.*

**Dribbler**
Creates through individual ball-carrying — beating opponents and penetrating the box.

| Metric | Weight |
|--------|--------|
| Successful dribbles p90 | 35% |
| Dribble success rate | 30% |
| Carries into final third p90 | 15% |
| Key passes p90 | 10% |
| Penalty area touches p90 | 10% |

*SCA removed — it contained successful dribbles (already at 35%), causing double-counting. Replaced with key passes to add a genuine secondary creative dimension.*

**Wide Creator**
Delivers from wide areas through crosses, half-space passes, and penalty area delivery.

| Metric | Weight |
|--------|--------|
| Crosses p90 | 25% |
| Key passes p90 | 20% |
| Cross accuracy | 20% |
| Passes into penalty area p90 | 20% |
| Half-space passes p90 | 15% |

*Cross volume and cross accuracy both reduced to resolve the volume/rate conflict. Key passes raised to 20% — the cleanest chance-creation signal for a wide player.*

### Composite Score (Legacy)
A weighted composite chance-creation score is retained for backward compatibility and is used in the radar chart visualisation. It ranks players on overall chance-creation output rather than role fit.

| Metric | Weight |
|--------|--------|
| Key passes p90 | 30% |
| Passes into penalty area p90 | 20% |
| Through balls p90 | 15% |
| Assists p90 | 15% |
| Half-space passes p90 | 10% |
| Successful dribbles p90 | 10% |

*Removed from earlier versions: SCA (double-counted key passes + dribbles), passes into final third and progressive passes (ball progression metrics, not chance creation). Added: assists p90 (direct output of chance creation, previously absent) and half-space passes p90 (deliveries from the most dangerous off-centre zones).*

## Clustering (Optional)

K-Means clustering (k=3) is applied to the standardised per-90 chance-creation metrics to identify sub-groups within the filtered midfielder population. Clustering is supplementary — roles are the primary classification. The cluster assignments are stored in `chance_creators_clustered.csv` and are not required for the dashboard to function.

## Spatial Thresholds

All pitch coordinates use a 0–100 scale (x: own goal line → opponent goal line, y: left touchline → right touchline).

| Zone | Threshold |
|------|-----------|
| Final third | x ≥ 66.7 |
| Penalty area | x ≥ 83 and 21.1 ≤ y ≤ 78.9 |
| Half-spaces | x ≥ 66 and (y < 37 or y > 63) |
| Progressive pass | End point ≤ 75% of original distance to goal: `(100 − endX) ≤ 0.75 × (100 − x)` |
| Carry inference gap | ≤ 30 pitch units between consecutive events |

## Limitations

- **Context blindness:** Per-90 stats do not capture game state, opponent quality, or tactical role constraints. A high-press defensive midfielder and a deep-lying playmaker are evaluated on the same absolute scale.
- **Opponent quality:** No adjustment is made for the strength of opponents faced. Accumulating stats against bottom-half teams is weighted equally to performance against top-six sides. Opponent-adjusted metrics are planned for end of season 2025/26 when full standings are available.
- **SCA approximation:** Shot-creating actions are approximated as key passes + successful dribbles and undercount the true total (which would also include progressive passes and defensive actions leading to counter-attacks). SCA is excluded from scoring for this reason.
- **Carry inference accuracy:** Carries into the final third are inferred from coordinate transitions, not logged events. The 30-unit gap heuristic handles most cases but may miss tight carries or, in edge cases, flag a long-pass reception as a carry.
- **Positional classification:** WhoScored positions may not perfectly reflect a player's actual tactical role in a given match. A nominal MC who consistently plays as a box-to-box 8 is classified the same as a holding 6.
- **Sample size:** Analysis covers a single season. Players with injuries or late mid-season transfers may not reach the 600-minute threshold.
- **Transfer data coverage:** Players who transfer out of Serie A mid-season are not on any team's Transfermarkt squad page and require manual data entry.
- **WhoScored qualifier casing:** WhoScored's event qualifier `displayName` values have undocumented casing inconsistencies (e.g. `"Throughball"` not `"ThroughBall"`). These are hardcoded and tested; if WhoScored changes their casing, affected columns silently become zero.

## Future Improvements

- **Opponent-adjusted metrics:** Split per-90 stats by opponent tier (top-6 / mid-table / bottom-6) using final standings; weight top-6 performance more heavily in the composite score. Planned for end of season 2025/26 when full standings are available.
- **Expected assists:** If pass end-location coordinates become available at greater resolution, build an xA model to complement raw assist counts.
- **Role fit score:** How well a player fits a specific tactical system, not just a generic role profile.
- **Video annotation layer:** Add qualitative notes for shortlisted players to contextualise statistical profiles.
