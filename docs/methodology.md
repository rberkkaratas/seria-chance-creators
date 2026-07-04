# Methodology

## Selection

The system profiles outfield players only. Goalkeepers are excluded until GK-specific events are parsed.

Players are included per position group:

| Group | Positions |
|-------|-----------|
| DEF | DC |
| FB | DL, DR, DML, DMR |
| MID | DMC, MC, AMC |
| WING | ML, MR, AML, AMR, FWL, FWR |
| FW | FW |

The inclusion threshold is `180` minutes in the active position group. The old `600`-minute threshold is still used, but now as the full-sample confidence point rather than a hard exclusion gate. Minutes outside the active group do not count. A player can appear in more than one group; final outputs then contain one row per `(player_id, position_group)`.

WhoScored labels substitute appearances as `Sub` instead of the player's tactical position. Before group filtering, those rows are assigned to the player's primary outfield position inferred from their non-sub minutes in the same league-season. Sub-only players remain unresolved rather than being forced into an unreliable group.

## Sample Reliability

Low-minute players remain visible, but their scores are calibrated by sample reliability.

```text
sample_reliability =
  0.65 * minutes_component
+ 0.15 * appearances_component
+ 0.15 * starts_component
+ 0.05 * start_rate_component
```

Where:

- `minutes_component` reaches 1.0 at 600 group minutes.
- `appearances_component` reaches 1.0 at 10 group appearances.
- `starts_component` reaches 1.0 at 6 group starts.
- `start_rate_component` is starts divided by appearances.

Before percentile ranking, each metric is shrunk toward the active pool median by this reliability value. Rate metrics listed in `config.RATE_SHRINKAGE` (`aerial_win_rate`, `tackle_success_rate`, `cross_accuracy`, `dribble_success_rate`) use their attempt count instead of minutes: the rate is shrunk toward the pool-average rate with a prior of 15 pseudo-attempts, so a player with 5 aerial duels or 6 crosses cannot post a 0% or 100% rate that outranks a 100-attempt sample. Role scores are then pulled toward the neutral 50-point baseline:

### Possession adjustment (PAdj)

Defensive volume depends on how often the opponent has the ball. Metrics listed in `config.PADJ_METRICS` (tackles, interceptions, and blocks/clearances for DEF; tackles, interceptions, and combined defensive actions for FB and MID) are rescaled to a 50% opponent-possession baseline before percentile ranking:

```text
padj_value = raw_p90 * (0.5 / opponent_possession_share)
```

Opponent possession share is proxied per match by pass counts in `teams.csv` and averaged per player weighted by the minutes they actually played (share is clipped to [0.25, 0.75] before scaling). Only rank sources are adjusted — displayed raw columns keep true per-90 values.

Ball recoveries and final-third regains are deliberately **not** possession-adjusted: they correlate negatively with opponent possession (they scale with a team's own pressing), so adjusting them would double-reward players on dominant sides. Pressing-role metrics in WING and FW are excluded for the same reason.

```text
adjusted_score = 50 + sample_reliability * (raw_score - 50)
```

This prevents a 200-minute hot streak from producing a misleading 95+ score, and prevents a thin low-event sample from collapsing unfairly toward zero.

## Metrics

`build_tables.py` aggregates WhoScored event flags to player-match rows. `player_features.py` then sums those rows to season totals and computes per-90 or rate metrics.

Important feature inputs include:

- `goals`
- `long_balls`
- `shot_creating_actions`
- progressive passes and final-third entries
- dribbles and carries into the final third
- tackles, interceptions, recoveries, clearances, blocks, and aerials
- spatial possession-winning metrics

`shot_creating_actions_p90` uses the real processed column when present. If a dataset predates it, the dashboard can fall back to `key_passes_p90 + successful_dribbles_p90` for display.

## Percentiles

Per-league feature files write:

- `{metric}_league_pct`: within league x position group
- `{metric}_pct`: initially copied from `_league_pct`

`merge_leagues.py` overwrites `{metric}_pct` with global all-leagues percentiles inside each `position_group`, preserving `_league_pct`. Both league and global percentiles use the sample-adjusted metric values described above.

## Role Scores

Roles are defined in `config.POSITION_GROUPS`.

```text
role_score = sum(metric_percentile * metric_weight)
```

All role weights sum to 1.0. The highest role score becomes `primary_role`.

`overall_score` is built in three steps within each position-group pool:

1. Each role score is z-standardized (equal variance), so a role whose score distribution happens to be wider — for example a role with few, strongly correlated metrics — cannot exert more influence than its configured `composite_weights` entry.
2. The standardized scores are blended with the group's composite weights (per-position overrides via `position_composite_weights` still apply).
3. The blend is percentile-ranked back to 0–100 within the pool, so the composite uses the full scale instead of compressing toward the middle.

Pools smaller than 5 rows fall back to a plain weighted average of raw role scores. Overall rankings are group-specific: centre-backs, fullbacks, central midfielders, wingers, and forwards no longer share broad mixed-position formulas. Because the final step is a percentile rank, `overall_score` reads as "better than X% of the pool", not as an absolute quality grade.

## Team Ratings

`src/features/team_features.py` builds one row per club from processed match/team/player tables and the merged player score file. It uses existing data only; no new scrape is required.

The rating input is each scored `(player_id, position_group)` row:

```text
player_z = inverse_normal_cdf(clip(overall_score, 0.5, 99.5) / 100)
team_strength_z = sum(position_group_minutes * player_z) / sum(position_group_minutes)
team_rating = percentile_rank(team_strength_z across all teams) * 100
```

There is deliberately no fixed DEF/FB/MID/WING/FW weighting. The team rating reflects the minutes a club actually played in each group, so wingback systems or striker-light systems are not penalized for a taxonomy artifact. Group ratings (`rating_DEF`, `rating_FB`, `rating_MID`, `rating_WING`, `rating_FW`) are profile indicators only; if a group has fewer than `TEAM_MIN_GROUP_MINUTES`, its sub-rating is blank.

Coverage is guarded but not used as an exclusion rule:

- `rating_coverage` = scored-player minutes divided by processed non-GK minutes.
- `low_coverage` is true when coverage is below `TEAM_MIN_COVERAGE` or qualified player count is below `TEAM_MIN_QUALIFIED_PLAYERS`.
- Low-coverage teams remain in the output.

`perf_delta_rank = league_rank_points - league_rank_rating`. Negative values mean the points-table rank is better than the squad-quality rank; positive values mean the points rank lags the rating rank. League table ranking uses points, goal difference, then goals for, not head-to-head tiebreakers.

## Current Limitations

- GK scouting is out of scope.
- Team ratings exclude goalkeepers.
- Team ratings assign all currently scored player minutes to the current team in the merged player file; mid-season transfers are not split by club unless the upstream player feature file is split.
- Sub-only players with no known outfield position are excluded until a reliable external position source is added.
- WhoScored positions are coarse labels and may not equal a player's real tactical role.
- Winger and forward samples are smaller per league; global percentile mode is usually more stable for wide/forward analysis.
- Historical event-level fixes require raw event files. Existing processed files are sufficient for the current role taxonomy.
