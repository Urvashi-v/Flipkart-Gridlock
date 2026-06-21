"""
profile_data.py  —  Step 1: understand the raw data before building anything.

Why: every downstream decision (which rows are usable, how to score severity,
how to bucket time) depends on what the data actually contains. We never trust
the spec sheet; we measure the file.
"""
import sys, json, ast
from collections import Counter
import pandas as pd

sys.path.append(str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from config import RAW_CSV, BLR_LAT_MIN, BLR_LAT_MAX, BLR_LON_MIN, BLR_LON_MAX

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 50)

USECOLS = [
    "id", "latitude", "longitude", "vehicle_type", "violation_type",
    "created_datetime", "police_station", "junction_name", "validation_status",
]

def main():
    print(f"Loading {RAW_CSV.name} ...")
    df = pd.read_csv(RAW_CSV, usecols=USECOLS, low_memory=False)
    n = len(df)
    print(f"\nRows: {n:,}   Columns loaded: {len(df.columns)}")

    # ---- geometry validity
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    in_box = (lat.between(BLR_LAT_MIN, BLR_LAT_MAX) & lon.between(BLR_LON_MIN, BLR_LON_MAX))
    print("\n--- GEOMETRY ---")
    print(f"  null lat/lon          : {lat.isna().sum():,} / {lon.isna().sum():,}")
    print(f"  inside Bengaluru box  : {in_box.sum():,} ({in_box.mean()*100:.1f}%)")
    print(f"  outside / bad         : {(~in_box).sum():,}")

    # ---- time range
    dt = pd.to_datetime(df["created_datetime"], errors="coerce", utc=True)
    print("\n--- TIME (created_datetime, UTC) ---")
    print(f"  parsed ok   : {dt.notna().sum():,}  failed: {dt.isna().sum():,}")
    print(f"  range       : {dt.min()}  ->  {dt.max()}")
    # convert to IST for hour-of-day sanity
    ist = dt.dt.tz_convert("Asia/Kolkata")
    print("  hour-of-day (IST) distribution (top 6):")
    print(ist.dt.hour.value_counts().head(6).to_string().replace("\n", "\n      "))

    # ---- validation status
    print("\n--- VALIDATION STATUS ---")
    print(df["validation_status"].fillna("NULL").value_counts().to_string().replace("\n", "\n  "))

    # ---- vehicle types
    print("\n--- VEHICLE TYPE (top 15) ---")
    print(df["vehicle_type"].fillna("NULL").value_counts().head(15).to_string().replace("\n", "\n  "))

    # ---- violation types (the column is a JSON-ish list per row)
    print("\n--- VIOLATION TYPE (exploded, top 20) ---")
    vc = Counter()
    sample = df["violation_type"].dropna()
    for s in sample:
        try:
            for v in ast.literal_eval(s):
                vc[str(v).strip()] += 1
        except Exception:
            vc[str(s)] += 1
    for k, v in sorted(vc.items(), key=lambda x: -x[1])[:20]:
        print(f"  {v:>8,}  {k}")

    # ---- junctions
    print("\n--- JUNCTION ---")
    jn = df["junction_name"].fillna("NULL")
    at_junction = (~jn.isin(["No Junction", "NULL"])).sum()
    print(f"  records tagged to a real junction: {at_junction:,} ({at_junction/n*100:.1f}%)")
    print("  top junctions:")
    print(jn[~jn.isin(['No Junction','NULL'])].value_counts().head(10)
          .to_string().replace("\n", "\n    "))

    # ---- police stations
    print("\n--- POLICE STATION (top 10) ---")
    print(df["police_station"].fillna("NULL").value_counts().head(10)
          .to_string().replace("\n", "\n  "))

    print("\nProfiling complete.")

if __name__ == "__main__":
    main()
