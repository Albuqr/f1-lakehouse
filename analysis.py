import pandas as pd
from scipy.stats import linregress

def load_data():
    fct = pd.read_parquet("data/fct_lap.parquet")
    dim_driver = pd.read_parquet("data/dim_driver.parquet")
    dim_session = pd.read_parquet("data/dim_session.parquet")
    dim_team = pd.read_parquet("data/dim_team.parquet")
    dim_compound = pd.read_parquet("data/dim_compound.parquet")

    return fct, dim_driver, dim_session, dim_team, dim_compound

def prepare_laps(fct, k=0.03, fuel_kg=100):
    pace = fct[fct["is_pace_lap"]].copy()
    pace["lap_time_s"] = pace["lap_time"].dt.total_seconds()
    total_laps = fct.groupby(["session_key"])["lap_number"].max().reset_index()
    total_laps = total_laps.rename(columns={"lap_number": "race_laps"})

    pace = pace.merge(total_laps, on=["session_key"], how="left")
    pace["lap_burn_rate"] = fuel_kg / pace["race_laps"]
    pace["fuel_burned"] = pace["lap_burn_rate"] * pace["lap_number"]
    pace["lap_time_corrected"] = pace["lap_time_s"] + k * pace["fuel_burned"]

    return pace

def consistency(fct, dim_driver, dim_session):
    slopes = stint_fits(fct)
    stats = slopes.groupby(["driver_key", "session_key"]).agg({"resid_sd": "mean", "n": "sum"}).reset_index()
    stats = stats[stats["n"] >= 40]

    stats = stats.merge(dim_driver[["driver_key", "driver_code"]], on="driver_key", how="left")
    stats = stats.merge(dim_session[["session_key", "event_name"]], on="session_key", how="left")
    return stats

def stint_slope(group):
    if len(group) < 10:
        return pd.Series({"slope": float("nan"), "r": float("nan"), "stderr": float("nan"), "resid_sd": float("nan"), "n": len(group)})
    result = linregress(group["tyre_life"], group["lap_time_corrected"])
    predicted = result.intercept + result.slope * group["tyre_life"]
    residuals = group["lap_time_corrected"] - predicted
    return pd.Series({"slope": result.slope, "r": result.rvalue, "stderr": result.stderr, "resid_sd": residuals.std(), "n": len(group)})

def pace_trend(fct, dim_compound, dim_session):

    slopes = stint_fits(fct)

    stintscheck = slopes.groupby(["compound_key", "session_key"])["slope"].agg(
        ["mean", "count"]).reset_index().sort_values("mean")

    stintscheck = stintscheck.merge(dim_compound[["compound_key", "compound_name"]], on="compound_key", how="left")
    stintscheck = stintscheck.merge(dim_session[["session_key", "event_name"]], on="session_key", how="left")
    stintscheck = stintscheck[stintscheck['count'] >= 5]

    return stintscheck

def stint_laps(fct, driver_key, session_key, stint):
    pace = prepare_laps(fct)
    pace = pace[(pace['driver_key'] == driver_key) & (pace['session_key'] == session_key) & (pace['stint'] == stint)].copy().sort_values("tyre_life")

    return pace

def stint_fits(fct):
    pace = prepare_laps(fct)
    slopes = pace.groupby(["driver_key", "session_key", "stint"]).apply(stint_slope, include_groups=False).reset_index()
    stint_compound = pace.groupby(["driver_key", "session_key", "stint"])["compound_key"].first().reset_index()
    slopes = slopes.merge(stint_compound, on=["driver_key", "session_key", "stint"], how="left")


    return slopes