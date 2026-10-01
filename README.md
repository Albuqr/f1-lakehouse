# f1-lakehouse

A small star schema of Formula 1 race laps built from public timing data with
[FastF1](https://docs.fastf1.dev/), an analysis module that fits a trend to every
tyre stint, and a Streamlit dashboard that shows the results.

The reasoning behind each choice is in [DECISIONS.md](DECISIONS.md). This file
summarises it; where the two differ, DECISIONS.md has the detail and the history.

## Scope: five races

Race sessions from rounds 20 to 24 of the 2025 season:

| Round | Event | Location | Race laps |
|---|---|---|---|
| 20 | Mexico City Grand Prix | Mexico City | 71 |
| 21 | São Paulo Grand Prix | São Paulo | 71 |
| 22 | Las Vegas Grand Prix | Las Vegas | 50 |
| 23 | Qatar Grand Prix | Lusail | 57 |
| 24 | Abu Dhabi Grand Prix | Yas Island | 58 |

They were chosen for circuit variety, because the degradation question compares
circuits and one race cannot answer it. The rounds are listed explicitly so the
scope is a list to check against, not a rule that grows. Only race sessions are
loaded; the sprint sessions at rounds 21 and 23 are not.

## Data model

`fct_lap` holds one row per driver per completed lap, so lapped drivers have
fewer rows. The five races give 5,623 laps from 20 drivers.

Four dimensions hang off it: `dim_driver`, `dim_team`, `dim_compound` and
`dim_session`. The team is stored on the fact, not on the driver, so each lap
records the team it was driven for. The circuit is part of `dim_session` rather
than its own dimension, which keeps every dimension one hop from the fact.
`dim_session` is keyed per session, not per event, so race and qualifying laps
from the same weekend stay separate. The circuit identifier is FastF1's
`Location`. A diagram is in [docs/star_schema.png](docs/star_schema.png).

The tables are written to `data/` twice. Parquet keeps the dtypes and is what the
analysis reads. CSV is kept for Looker Studio, which cannot read Parquet. CSV
loses types on a round trip: `track_status` comes back as a number, and the
exclusion rule below then still runs but no longer means the same thing.

## The three questions

The dashboard has one tab per question:

1. **Stint explorer.** What does one driver's race look like, stint by stint?
   Lap times against tyre age with the fitted line for each stint. This is an
   illustration, not evidence: one driver's stints cannot establish the
   findings in the other two tabs.
2. **Consistency.** How far do a driver's laps scatter around their own stint
   trend, and does that vary by circuit?
3. **Degradation.** How much pace does each compound lose per lap of tyre age,
   at each circuit?

## Which laps are used

A lap is a pace lap unless it falls under one of these rules. Some laps fall
under more than one.

| Excluded | Laps | Why |
|---|---|---|
| Lap 1 | 100 | Standing start |
| In-laps | 164 | Includes the pit-lane entry |
| Out-laps | 159 | Includes the pit-lane exit |
| Track status not exactly `"1"` | 403 | Not green for the whole lap: yellow, safety car, VSC or another non-green status |

That leaves 4,902 pace laps of 5,623.

`TrackStatus` is a string that concatenates codes when the status changes during
a lap, so a fully green lap is exactly `"1"`. The rule excludes everything
FastF1's `IsAccurate` flag excludes, plus 64 laps that FastF1 accepts, all with
status `"12"` (green, then yellow). Those are excluded on purpose: the data does
not say where on the lap the driver lifted, and the trend being measured is in
hundredths of a second. The original rule had no track-status condition. It was
checked on a single race with no cautions and agreed with `IsAccurate` there by
coincidence. On these five races it missed 245 laps.

Before fitting, each stint is also sorted by tyre age and its first 2 laps are
dropped, to keep tyre warm-up out of the trend.

## Fuel correction

A car gets lighter as it burns fuel and goes faster, which hides tyre wear.
Without a correction, every Las Vegas and Qatar slope came out negative, which
would say the tyres got faster with age.

Each lap time is corrected before fitting:

```
corrected = raw + k × fuel_burned
fuel_burned = (fuel_kg / race_laps) × lap_number
```

with `k = 0.03` s/kg and `fuel_kg = 100`. **Both are assumptions, not
measurements.** Real fuel loads are not in public timing data, the burn is
assumed to be linear, and k varies by circuit. The figures below are sensitive to
both values. With the correction removed, the compound averages are 0.042 to
0.060 s/lap lower, and 4 of the 10 turn negative (both compounds at Las Vegas and
at Qatar).

## Thresholds

Each threshold counts the unit its metric aggregates over. When the consistency
threshold counted laps instead of stints, it cut half the Las Vegas field, a
50-lap race, by a single lap (see DECISIONS.md, "Threshold bug").

| Constant (`analysis.py`) | Value | Unit | Applies to |
|---|---|---|---|
| `SKIP_LAPS` | 2 | laps | dropped from the start of every stint before fitting |
| `MIN_FIT_LAPS` | 10 | laps | a stint needs this many after the drop (12 in total) to be fitted; 198 of 237 stints qualify |
| `MIN_COMPOUND_STINTS` | 5 | fitted stints | a compound at a circuit needs this many for a degradation average |
| `MIN_STINTS` | 2 | fitted stints | a driver needs this many in a race to count for consistency |
| `MIN_CIRCUIT_DRIVERS` | 10 | drivers | below this, the dashboard hatches a circuit's consistency average as low confidence; no circuit is currently below it |
| `FUEL_K`, `FUEL_KG` | 0.03, 100 | s/kg, kg | fuel correction, as above |

Two more live in `dashboard.py` and only affect wording:

| Constant | Value | Unit | Effect |
|---|---|---|---|
| `TIE` | 0.001 | s/lap | compounds at a circuit closer than this are reported as level |
| `SPREAD_RATIO` | 3 | ratio | the circuit-average chart is titled "barely varies" when the driver spread within a race is at least this many times the spread between circuits |

## Method

For every stint with enough laps, a straight line is fitted to fuel-corrected
lap time against tyre age (`scipy.stats.linregress`). Fitting per stint, rather
than pooling by compound and circuit, keeps each fit to one car, one tyre set and
a narrow band of fuel load. A pooled slope would mostly measure which drivers ran
that compound.

- **Stint trend** is the slope, in s/lap. The degradation figures average it
  over the stints on a compound at a circuit.
- **Residual scatter** is the standard deviation of a stint's laps around its
  fitted line, in seconds. The consistency figures average it over a driver's
  stints in a race, then over drivers at a circuit.

The metric is called "pace trend" in DECISIONS.md, because before the fuel
correction it combined fuel burn and tyre wear and was negative at two circuits.

## Findings

As read from the current data. The dashboard computes all of these at render
time, so they follow the data if it changes.

### Degradation

| Compound | Circuit | s/lap | Stints |
|---|---|---|---|
| SOFT | São Paulo | +0.115 | 7 |
| MEDIUM | Abu Dhabi | +0.103 | 22 |
| MEDIUM | São Paulo | +0.081 | 34 |
| SOFT | Mexico City | +0.068 | 25 |
| HARD | Abu Dhabi | +0.055 | 21 |
| MEDIUM | Mexico City | +0.051 | 16 |
| MEDIUM | Las Vegas | +0.027 | 11 |
| HARD | Las Vegas | +0.026 | 19 |
| HARD | Qatar | +0.013 | 13 |
| MEDIUM | Qatar | +0.012 | 25 |

- After fuel correction every average is positive.
- The softer compound has the higher slope at Mexico City, São Paulo and Abu
  Dhabi, the three circuits with meaningful degradation, by 0.017, 0.034 and
  0.049 s/lap.
- At Las Vegas the medium and hard are within 0.001 s/lap of each other. At
  Qatar the hard is 0.002 s/lap above the medium. At these two circuits the data
  shows no ordering, so "softer degrades faster" holds at three circuits, not
  five.
- The highest figure, São Paulo soft, rests on 7 stints, the thinnest group
  behind any number in the table.
- For scale: Pirelli has described 0.2 to 0.3 s/lap as very high, and a
  published estimate for Austria 2025 was 0.054 to 0.060.

### Consistency

| Circuit | Residual scatter (s) | Drivers |
|---|---|---|
| Qatar | 0.30 | 18 |
| São Paulo | 0.34 | 16 |
| Abu Dhabi | 0.35 | 20 |
| Las Vegas | 0.36 | 12 |
| Mexico City | 0.38 | 18 |

- Circuit averages span 0.08 s. Within a single race, drivers span 0.39 to
  0.47 s (median 0.43), about five times as much. Once the stint trend is
  removed, drivers are about equally consistent at every circuit.
- The order of the circuits is not reliable. Each pair of neighbouring circuits
  is 0.009 to 0.038 s apart, less than the standard error of their difference
  (0.036 to 0.049 s).
- This reverses the first version of the metric, which used the raw standard
  deviation of lap times over a race. That version ranked Qatar least consistent
  at 1.30 s, but that circuit effect was almost entirely stint trend, not
  driver variability.
- Coverage differs by driver: 8 drivers are counted at all five races, 8 at
  four and 4 at three. An average over fewer races is not directly comparable
  with a full one.

## Limitations

- **Fuel.** The correction rests on two assumed constants and a linear burn.
  Real fuel loads are not public, and k varies by circuit.
- **What the data lacks.** Public timing has no tyre temperatures or pressures
  and no car setup, so temperature effects can't be separated from wear.
- **Residual scatter is not only the driver.** It also picks up traffic, DRS,
  restarts and other one-off events, which this data cannot separate. In one
  documented case (VER, Qatar, stint 3) a 1.2 s step between consecutive laps
  came from something discrete (DRS, traffic or a restart), and the data does
  not say which.
- **A straight line per stint.** Each fit assumes pace changes linearly with tyre
  age.
- **Aggregates of aggregates.** Consistency is a mean of per-stint standard
  deviations, averaged again over drivers. That is defensible while stint
  lengths are similar, and it is still an average of averages.
- **Thin groups.** Some averages rest on few stints or drivers (São Paulo soft:
  7 stints; Las Vegas consistency: 12 drivers). Las Vegas is the shortest race,
  at 50 laps.
- **Sample.** Five races from the end of one season. The findings describe these
  races, not tyres or circuits in general.
- **Stint explorer** shows single stints. They illustrate the method and are not
  evidence for the findings.

## Running it

Built and run with Python 3.14.

```
python -m venv .venv
.venv\Scripts\activate          # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### Build the tables

`build_star.ipynb` loads the five races with FastF1, builds the star schema and
writes it to `data/` as CSV and Parquet. Run it top to bottom in Jupyter, or:

```
jupyter nbconvert --to notebook --execute --inplace build_star.ipynb
```

The first run downloads the race data from the F1 timing service into
`ff1_cache/` (not committed); later runs read from the cache. The built tables
are committed in `data/`, so the build only needs to run again if it changes.

### Run the dashboard

```
streamlit run dashboard.py
```

The dashboard reads `data/*.parquet` and `analysis.py`. It reloads both when
they change, so edits show up on the next rerun without restarting the server. Team colours come
from FastF1 and use `ff1_cache/`. Without a cache or a network connection the
driver card and the consistency charts fall back to grey.

## Credits

Circuit outlines in `data/tracks/` are from
[julesr0y/f1-circuits-svg](https://github.com/julesr0y/f1-circuits-svg),
© 2024–2026 Jules Roy, licensed CC BY 4.0. The licence is alongside them in
`data/tracks/LICENSE.txt`, and the dashboard footer carries the attribution.
Timing data is accessed through FastF1.
