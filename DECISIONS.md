# Decisions

## Lap grain
One row per driver per completed lap. Lapped drivers have fewer rows.
2023 Spanish GP: 1312 rows = 12 drivers x 66 laps + 8 x 65.

## Pace lap exclusion
Excluded: lap 1 (standing start), in-laps, out-laps.
Verified these exactly match FastF1's IsAccurate flag on this session
(105 laps, zero disagreement in either direction). Implementing the rule
ourselves rather than depending on IsAccurate.
Untested on sessions with safety cars, red flags, or deleted laps.

## Fuel load confound
Lap time improves with tyre age within a stint because fuel burn
outweighs tyre wear. A raw slope of lap time vs TyreLife measures
fuel burn, not degradation.
Handling: restrict comparisons to the same lap-number range, since lap
number proxies fuel load. Stint number rejected as the restriction
because stint boundaries depend on pit strategy, so the same stint
number means different race stages for different drivers.
Cost: windows cut across stints, so some drivers contribute partial
windows. Needs a minimum lap count per window before a slope is
trusted. Threshold not yet chosen.

## Metric naming
Not naming the slope "degradation" - it contains fuel burn and tyre
wear together. Final name deferred until the values have been seen.