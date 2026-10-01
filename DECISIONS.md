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

## Exclusion rule, corrected on five races
The Barcelona rule (lap 1, in-lap, out-lap) was incomplete. On the
five-race set it missed 245 laps that IsAccurate flags, every one of
them with a non-green track status. Barcelona had no safety cars or
yellows at all, so the two rules agreed there by coincidence.

TrackStatus is a string and concatenates codes when the status changes
during a lap ("12" is green then yellow, "671" is VSC, VSC ending,
green). A fully green lap is exactly "1".

Rule now: lap 1, or in-lap, or out-lap, or TrackStatus != "1".
This is a superset of IsAccurate: it excludes 64 laps that FastF1
accepts, all of them "12".

Those 64 are excluded deliberately. A yellow means the driver lifted
somewhere on the lap, the data does not say where or whether they were
near it, and the degradation metric measures tenths. 64 of 5623 laps
is 1.1%, which is a cheap price for knowing every remaining lap was
green throughout.

Lesson recorded: the original rule was verified on a single clean race
and that was not enough to establish it.

## Output format: Parquet for analysis, CSV for BI
Writing the tables to CSV and reading them back loses every dtype.
Observed on the round trip: all timedelta columns came back as object
(text), the deliberate Int64 casts reverted to plain int64, and
track_status came back as int64 when it was a string.

track_status is the dangerous one. The exclusion rule tests
track_status != "1", and it works because the column is a string that
concatenates codes. Read back as a number the comparison still runs
but no longer means the same thing, and it fails silently.

CSV has no schema. Any pipeline that round-trips through it has to
re-apply types on read, and forgetting one column is invisible.

The build now writes Parquet as well, and analysis reads Parquet.
CSV stays because Looker Studio reads CSV and not Parquet, so the BI
layer needs it.

## Consistency metric: minimum 40 pace laps per group
Standard deviation of green-flag lap time is grouped by driver and
session. Groups with few laps are drivers who retired or crashed out
early.

The problem is not noise, it is bias. Plotting lap count against
standard deviation showed low-count groups sitting at or below the
spread of full-race groups, not scattered around it. The five-lap
group had the lowest standard deviation on the chart. A short sample
has not had time to vary, so those drivers would appear as the most
consistent on the dashboard when they simply stopped early.

Threshold: 40 pace laps. There is a natural gap in the data between
32 and 42 laps. It excludes 7 of 96 groups; a threshold of 30 would
exclude 6, so the stricter floor costs one group.

## Consistency varies by circuit, not mainly by driver
Averaging the per-driver standard deviations by circuit:

  Sao Paulo     0.78 s
  Abu Dhabi     0.84 s
  Mexico City   0.99 s
  Las Vegas     1.02 s
  Qatar         1.30 s

Drivers are about 66% more variable at Qatar than at Sao Paulo, and
the pattern holds across the field. So the headline is the circuit,
not a driver ranking. A driver ranking built from this data would
largely be measuring which circuits each driver happened to run well
at.

What this does not establish: the cause. Qatar is abrasive, so tyres
may degrade fast enough that lap times drift within a stint. The
metric cannot separate a driver varying lap to lap from pace changing
steadily through a stint. A perfectly smooth degradation curve
produces a high standard deviation too.

Averaging standard deviations is defensible here because group lap
counts are similar after the 40-lap threshold, but it is a mean of
aggregates and should be described as such.

## The Qatar variance is not degradation
Hypothesis: Qatar's high lap-time variance is tyre degradation.
Not supported.

VER, Qatar, stint 3, laps 34 to 57 with no gaps. The shape is a V,
not a slope: times fall from 84.8 to 83.5 around laps 45 to 50, then
climb back to 85.0. Between lap 44 (84.701) and lap 45 (83.515) there
is a 1.2 second step in a single lap. Degradation moves in hundredths
per lap, so a step that size is something discrete - DRS, traffic, a
restart - and this data does not say which.

The same driver at Sao Paulo, which has the lower variance overall,
shows the cleaner upward drift: 73.3 to 74.1 over 19 laps. So the
circuit with more variance has the less degradation-like shape.

Consequence for the metric: a standard deviation over a race gives the
same number whether lap times drifted smoothly or stepped once. It
measures lap-time spread, not driver inconsistency, and the spread can
come from degradation, a one-off event, traffic or the driver. The
dashboard labels it as spread and says so.

Evidence is one driver and two stints. This is a counter-example to
the hypothesis, not a general finding about either circuit.

## Pace trend: per driver per stint, minimum 10 laps
The slope of lap time against tyre age is fitted per driver per stint,
not pooled by compound and circuit. Pooling mixes cars, and the gap
between a fast car and a slow one is seconds while degradation is
hundredths per lap, so a pooled slope would mostly measure which
drivers ran that compound.

A lap-number window was considered and rejected. Checking min and max
lap number per compound per circuit showed most compounds spanning
nearly the whole race, because every driver's stints on that compound
are pooled together. The window separates nothing at that grain.
Fitting per stint handles the fuel confound instead: one stint is one
car, one tyre set, and a narrow band of fuel load.

Stint lengths: 237 stints, median 21 laps, quartiles 15 and 25, and a
tail of stints of 5 laps or fewer. Threshold of 10 laps keeps 205
stints; 15 would keep 181. Took 10, since 10 points is enough to fit
a line and the extra 24 stints are worth keeping.

Circuit and compound slopes are then averages of these per-stint
slopes.

## Pace trend per lap of tyre age: results
Slope of lap time against tyre age, fitted per driver per stint with
scipy linregress, minimum 10 laps per stint. 205 of 237 stints
qualified. Groups below 5 stints dropped; the data gaps from 2 to 9,
so the floor costs nothing extra.

  SOFT    Sao Paulo     +0.080 s/lap   (9 stints)
  MEDIUM  Sao Paulo     +0.046         (34)
  MEDIUM  Abu Dhabi     +0.034         (23)
  SOFT    Mexico City   +0.022         (26)
  MEDIUM  Mexico City   +0.013         (16)
  HARD    Abu Dhabi     -0.000         (21)
  HARD    Qatar         -0.036         (13)
  HARD    Las Vegas     -0.044         (19)
  MEDIUM  Qatar         -0.048         (25)
  MEDIUM  Las Vegas     -0.054         (14)

Negative means cars got faster as the tyre aged: fuel burn outweighed
tyre wear. That happens at Las Vegas and Qatar on every compound.
Sao Paulo is the only circuit with a clear positive trend.

Within every circuit that has two compounds, the softer one has the
higher slope. Same direction in all four cases, which is a better
signal than any single number.

Across all 205 stints the median slope is +0.006 with quartiles at
-0.037 and +0.035, so pooled across circuits there is no net
degradation signal at all. The two effects roughly cancel, and which
one wins depends on the circuit.

Fit quality: median absolute r is 0.58, upper quartile 0.74. 49 of 205
stints are below 0.3 and effectively flat.

## Metric name
Not "degradation". The number is negative at two circuits, and a
degradation figure that says tyres improve is a lie. It is a pace
trend per lap of tyre age, and it contains fuel burn and tyre wear
together.

## Dashboard: Streamlit
Three options considered.

Looker Studio: free, good dropdown filtering, no hosting. But it
cannot fit or draw a regression line, blending past two or three
sources is clumsy, scatter plots are weak, and there is no control
over layout. The per-stint drill-down would have to precompute fitted
values as a second series.

Static HTML: total control, deploys to nginx, works untouched for
years. No interactivity without writing it by hand.

Streamlit: interactivity without JavaScript, computation in pandas so
the line fitting can run live, already known from the Credit Risk
system, deploys as Docker on the existing VPS. Cost is a running
process to maintain rather than a static file.

Chose Streamlit because the view has a drill-down: the reader picks a
stint and sees its lap times against tyre age with the fitted line.
That is the part Looker Studio cannot do and static HTML would need
hand-written JS for.

Looker Studio stays available as a separate 8-10 hour item if a
specific posting asks for BI-tool evidence, on the same trigger as the
deferred Power BI port.

## Dashboard scope
Opens with the findings: pace trend by compound and circuit,
consistency by circuit. Then a drill-down where the reader picks a
driver, race and stint and sees the lap times against tyre age with
the fitted line, labelled as illustration rather than evidence.

Not included: driver photos, which are copyrighted and would be
republished on a public site. Track maps, which need telemetry
position data that P1 deliberately does not load, and which do not
change what the reader learns.

The per-stint view is deliberately second. The findings are about
patterns across 205 stints, and opening on a single-stint filter
would invite the reader into exactly the thin slices the thresholds
exclude.

## Track outlines
Source: julesr0y/f1-circuits-svg, CC BY 4.0, (c) 2024-2026 Jules Roy.
Five SVGs in data/tracks/, with the LICENSE file alongside them.
Attribution in the dashboard footer as the licence requires.

Considered and rejected: deriving outlines from FastF1 telemetry
position data, which needs a telemetry download per circuit and is
outside P1's scope. The f1laps bundle with per-sector paths costs
USD 21, which the budget rules do not cover for presentation assets.
