# Data manifest

What the files in this directory were built from, so a rebuild can be checked
against them.

## Retrieval

| | |
|---|---|
| Retrieved | 2026-09-23, 11:24–11:25 (UTC−03:00) |
| Built | 2026-09-30, 10:51 (UTC−03:00) |
| Source | F1 live timing, through FastF1 |
| fastf1 | 3.8.3 |
| pandas | 2.3.3 |
| pyarrow | 25.0.1 |

The retrieval time is the write time of the five sessions' files in
`ff1_cache/`, which FastF1 writes when it downloads a session. The build ran a
week later and read those cached files, not fresh downloads. The build time is
the write time of the files below.

## Sessions

| Year | Round | Event | Location | Session type | Date |
|---|---|---|---|---|---|
| 2025 | 20 | Mexico City Grand Prix | Mexico City | R | 2025-10-26 |
| 2025 | 21 | São Paulo Grand Prix | São Paulo | R | 2025-11-09 |
| 2025 | 22 | Las Vegas Grand Prix | Las Vegas | R | 2025-11-22 |
| 2025 | 23 | Qatar Grand Prix | Lusail | R | 2025-11-30 |
| 2025 | 24 | Abu Dhabi Grand Prix | Yas Island | R | 2025-12-07 |

Session type `R` is the race. The sprint sessions at rounds 21 and 23 are not
loaded.

## Row counts

| Table / measure | Rows |
|---|---|
| `fct_lap` laps | 5,623 |
| pace laps (`is_pace_lap`) | 4,902 |
| stints (driver × race × stint) | 237 |
| `dim_driver` | 20 |
| `dim_team` | 10 |
| `dim_compound` | 5 |
| `dim_session` | 5 |

## Checksums

`sha256sum data/*.parquet data/*.csv`:

```
5bc50d62ea7f71bcac2f76cc46f60a7870a0a8fbc10a51c21657f5b79078cb39 *data/dim_compound.parquet
f79537e54a915bd7a8c673353b5317e067f3e92fda958111654fcb8c1bb73381 *data/dim_driver.parquet
73833c2c0f610225f84a8b07e5276cce8546063e3a633411048828c3b63f6ead *data/dim_session.parquet
3a2d9f3227221e1e6c40a6a9d665ad750191dc6f1ef0de6b1e61cd9e1e6584ae *data/dim_team.parquet
ab5b628bf28e74c76127abe5b1f78dd8e75b04f8d2c9a12785da362f89e5904f *data/fct_lap.parquet
7a1b5585d0a5dcc7f7541eb37274ff846147ecffca2410289ecc7ec675550fe6 *data/dim_compound.csv
6fe38fb4aa72e7bf0dabfb30ee95d7f87941debc47141757480747a2ec58a47f *data/dim_driver.csv
60e066535316fbe128f7a5cdf5fc4da9caeed9b2e0e713e64f4739388bb4c291 *data/dim_session.csv
35be3d692c80c562540c4c0cff28dd063e0add403e45b43498e0bf56664e13d1 *data/dim_team.csv
ca22d8782792d4bdb825177514fd0742f81242388fbeb58419cf58a4773ee375 *data/fct_lap.csv
```

## Checking a rebuild

A different hash means the bytes differ, not necessarily the data. Before
concluding that FastF1's timing data has changed, rule out these:

- **Cache.** A rebuild reads `ff1_cache/` if it exists. To compare against the
  source as it is today, rebuild with an empty cache.
- **Library versions.** Parquet files record the pandas and pyarrow versions that
  wrote them, so a different version changes the Parquet hashes even when the
  data is identical.
- **Line endings.** The CSVs were written on Windows with CRLF line endings, and
  git stores them as written. A clone has these bytes, but a rebuild on macOS or
  Linux writes LF endings and changes every CSV hash.

If the hashes differ, compare the row counts above, then the tables themselves,
before reading anything into the hash alone.
