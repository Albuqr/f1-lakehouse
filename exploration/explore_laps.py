import fastf1
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

fastf1.Cache.enable_cache("ff1_cache")

session = fastf1.get_session(2023, "Spanish Grand Prix", "R")
session.load(laps=True, telemetry=False, weather=False, messages=False)

laps = session.laps

print("SHAPE: ", laps.shape)
print()
print("COLUMNS: ", laps.columns.tolist())
print()
print("DTYPES: ")
print(laps.dtypes)
print()
print("HEAD: ")
print(laps.head())
print(laps.groupby("Driver")["LapNumber"].count().sort_values())
print(laps[["LapNumber", "Stint", "TyreLife", "Position"]].isna().sum())
print(laps["IsAccurate"].value_counts())
print(laps["TrackStatus"].value_counts())
bad = laps[~laps["IsAccurate"]]
print(bad["LapNumber"].value_counts().head())
print(bad[["PitInTime", "PitOutTime"]].notna().sum())
print(len(bad[bad["PitInTime"].notna() & bad["PitOutTime"].notna()]))
print(len(bad[(bad["LapNumber"] == 1) & bad["PitOutTime"].notna()]))
my_rule = (laps["LapNumber"] == 1) | laps["PitInTime"].notna() | laps["PitOutTime"].notna()
print("mine:", my_rule.sum())
print("fastf1 flags but I miss:", (~laps["IsAccurate"] & ~my_rule).sum())
print("I flag but fastf1 accepts:", (laps["IsAccurate"] & my_rule).sum())

laps["is_first_lap"] = laps["LapNumber"] == 1
laps["is_in_lap"] = laps["PitInTime"].notna()
laps["is_out_lap"] = laps["PitOutTime"].notna()
laps["is_pace_lap"] = ~(laps["is_first_lap"] | laps["is_in_lap"] | laps["is_out_lap"])

print(laps["is_pace_lap"].sum())

ver = laps[(laps["Driver"] == "VER") & laps["is_pace_lap"]]
print(ver[["LapNumber", "Stint", "Compound", "TyreLife", "LapTime", "SpeedST", "Position"]].to_string())