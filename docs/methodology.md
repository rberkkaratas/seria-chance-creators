# Methodology

## Objective

Identify and profile elite chance-creating midfielders in Serie A 2025/26 using match event data, with the goal of producing a scouting shortlist that a sporting director or head scout could act on.

## Data Source

Match event data is extracted from WhoScored using a semi-automated pipeline. Match IDs are manually collected for all Serie A 2025/26 fixtures; the pipeline then extracts structured event data for each match and normalizes it into three tables (matches, players, teams).

**Why WhoScored?** Following FBref's loss of Opta access, WhoScored remains one of the few publicly accessible sources of detailed match event data, including pass types, dribble events, and defensive actions.

## Player Selection

Players are filtered using the following criteria:
- **Positions:** AMC, AML, AMR, MC, ML, MR (midfield and attacking midfield roles)
- **Minimum minutes:** 900+ (approximately 10 full matches) to ensure statistical stability
- **League:** Serie A 2025/26 only

**Important:** Minutes are counted only from appearances where the player was classified in a midfield position. A player logging 800 minutes as a centre-back and 200 minutes as a midfielder does not qualify — their midfield sample (200 min) is below the threshold. This prevents defenders who occasionally played in midfield from inflating the rankings.

## Feature Engineering

### Per-90 Normalization
All counting stats are converted to per-90-minute rates to allow fair comparison between players with different playing time. This is standard practice in football analytics.

### Chance-Creation Metrics
The following metrics were selected to capture different dimensions of creativity:

| Metric | What it captures |
|--------|-----------------|
| Key passes | Direct chance creation (pass leading to a shot) |
| Through balls | Ability to break defensive lines |
| Passes into final third | Ball progression into dangerous areas |
| Passes into penalty area | High-value delivery into the box |
| Shot-creating actions | Combined measure (key passes + successful dribbles) |
| Successful dribbles | Ability to create through carrying |
| Progressive passes | Forward-moving passes (≥25% closer to goal, derived from x/y coordinates) |

**Note on progressive carries:** WhoScored event data does not include a `Carry` event type, so progressive carries cannot be derived and are excluded from the model. The 5% weight originally allocated to this metric was redistributed to key passes.

### Composite Score
A weighted composite score ranks players by overall chance-creation ability. Weights were assigned based on domain knowledge of what constitutes high-value creativity:

| Metric | Weight |
|--------|--------|
| Key passes | 25% |
| Shot-creating actions | 20% |
| Passes into penalty area | 15% |
| Through balls | 10% |
| Passes into final third | 10% |
| Successful dribbles | 10% |
| Progressive passes | 10% |

These weights prioritize direct chance creation (key passes, SCA, penalty area delivery) over volume progression, reflecting the scouting brief of finding players who directly create goal-scoring opportunities.

## Archetype Clustering

K-Means clustering (k=3) is applied to the standardized per-90 metrics to identify distinct creative profiles. The number of clusters was chosen based on football domain knowledge (there are broadly three types of creative midfielder) and validated using the elbow method.

### Expected Archetypes
- **Final-Ball Specialists:** High key passes, through balls, assists. The classic "number 10" who delivers the final pass.
- **Progressive Carriers:** High progressive carries, dribbles, forward movement. Creates by driving with the ball.
- **Volume Creators:** High touch count, pass volume, tempo control. Creates through sustained possession and orchestration.

*Note: Actual archetype labels are assigned after inspecting cluster centroids and representative players.*

## Limitations

- **Data completeness:** WhoScored event data does not include carry events, so progressive carries cannot be measured. Some other event types available in commercial feeds (Opta, StatsBomb) are also absent.
- **Context blindness:** Per-90 stats don't capture game state, opponent quality, or tactical role constraints.
- **Sample size:** Analysis is limited to a single season. Players with injuries or late transfers may have insufficient data.
- **Positional classification:** WhoScored positions may not perfectly reflect a player's actual tactical role in a given match.
- **SCA approximation:** Shot-creating actions are approximated as key passes + successful dribbles. This underestimates the true SCA count (which would also include progressive passes, defensive actions leading to counter-attacks, etc.).

## Future Improvements

- Integrate Transfermarkt data for contract status, market value, and transfer feasibility
- Add video analysis notes for shortlisted players (qualitative layer)
- Incorporate opponent-adjusted metrics (performance vs. top-6 teams vs. bottom-6)
- Build expected assists model from pass end-locations if coordinate data becomes available
