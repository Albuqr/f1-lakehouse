import pandas as pd
from scipy.stats import linregress

def load_data():
    fct = pd.read_parquet("data/fct_lap.parquet")
    dim_driver = pd.read_parquet("data/dim_driver.parquet")
    dim_session = pd.read_parquet("data/dim_session.parquet")
    dim_team = pd.read_parquet("data/dim_team.parquet")
    dim_compound = pd.read_parquet("data/dim_compound.parquet")

    return fct, dim_driver, dim_session, dim_team, dim_compound

def consistency(fct, dim_driver, dim_session):
    pace = fct[fct["is_pace_lap"]].copy()
    pace['lap_time_s'] = pace["lap_time"].dt.total_seconds()
    stats = pace.groupby(["driver_key", "session_key"])["lap_time_s"].agg(["count", "std"]).reset_index()
    stats = stats[stats["count"] >= 40]

    stats = stats.merge(dim_driver[["driver_key", "driver_code"]], on="driver_key", how="left")
    stats = stats.merge(dim_session[["session_key", "event_name"]], on="session_key", how="left")
    return stats

def stint_slope(group):
    if len(group) < 10:
        return pd.Series({"slope": float("nan"), "r": float("nan"), "stderr": float("nan")})
    result = linregress(group["tyre_life"], group["lap_time_s"])
    return pd.Series({"slope": result.slope, "r": result.rvalue, "stderr": result.stderr})

def pace_trend(fct, dim_compound, dim_session):

    pace = fct[fct["is_pace_lap"]].copy()
    pace["lap_time_s"] = pace["lap_time"].dt.total_seconds()

    slopes = pace.groupby(["driver_key", "session_key", "stint"]).apply(stint_slope, include_groups=False).reset_index()
    stint_compound = pace.groupby(["driver_key", "session_key", "stint"])["compound_key"].first().reset_index()
    slopes = slopes.merge(stint_compound, on=["driver_key", "session_key", "stint"], how="left")

    stintscheck = slopes.groupby(["compound_key", "session_key"])["slope"].agg(
        ["mean", "count"]).reset_index().sort_values("mean")

    stintscheck = stintscheck.merge(dim_compound[["compound_key", "compound_name"]], on="compound_key", how="left")
    stintscheck = stintscheck.merge(dim_session[["session_key", "event_name"]], on="session_key", how="left")
    stintscheck = stintscheck[stintscheck['count'] >= 5]

    return stintscheck

