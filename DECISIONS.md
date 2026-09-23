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

## Star schema
fct_lap at driver x lap x session grain.
Four dimensions: dim_driver, dim_team, dim_compound, dim_session.

Team on the fact, not on dim_driver: drivers change teams, and a lap
must record the team it was driven for at the time. Storing team on
the driver would relabel historical laps.

Circuit flattened into dim_session rather than a separate dim_circuit.
Keeps every dimension one hop from the fact.


## dim_session
One row per session, not per event. A race weekend is one event with
five sessions; the key must be year + round + session type so that
qualifying and race laps from the same weekend stay separate.

year and session_type are not in session.event. They come from the
get_session() arguments and are stamped on when the dimension is built.

## Circuit identifier
FastF1 gives Location ("Barcelona"), not a circuit name. Using Location
as the circuit identifier rather than inventing a track name that is
not in the source.

## Scope: five races
2025 rounds 20 to 24, named explicitly so the scope is a list to check
against rather than a rule that grows:

- Round 20, Mexico City Grand Prix, Mexico City, conventional
- Round 21, Sao Paulo Grand Prix, Sao Paulo, sprint_qualifying
- Round 22, Las Vegas Grand Prix, Las Vegas, conventional
- Round 23, Qatar Grand Prix, Lusail, sprint_qualifying
- Round 24, Abu Dhabi Grand Prix, Yas Island, conventional

Chosen for circuit variety, since the degradation question compares
across circuits and one race cannot answer it. Race sessions only;
the sprint sessions at rounds 21 and 23 are not loaded.

2023 Spanish GP was the original single race and is dropped from the
scope. Its verification work (grain arithmetic, exclusion rule proved
against IsAccurate) stands and is recorded above.

Adding more races is a separate decision after this releases, not an
extension of this one.
