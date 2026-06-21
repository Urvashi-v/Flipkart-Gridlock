"""
pipeline.py  —  Step 2: clean the raw CSV and engineer the features the
hotspot + scoring stages need. Runs once; writes a compact Parquet that every
later script loads in <1s.

Design choices (the "why"):
  * We keep only Bengaluru-valid coordinates — bad GPS would create phantom
    hotspots.
  * The `violation_type` column is a JSON list per row. We explode it to find
    the single most-severe violation on each ticket (a ticket parked "IN A MAIN
    ROAD" + "NO PARKING" is judged by its worst, flow-blocking offence).
  * We drop tickets whose violations are ALL non-parking (number plate, fare,
    seat belt) — they are real police work but irrelevant to congestion.
  * We translate raw timestamps to IST because enforcement is scheduled in
    local time, and bucket into time-of-day windows patrols can act on.
  * `validation_status == rejected` is kept but flagged so scoring can discount
    likely false positives.
"""
import sys, ast
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import (
    RAW_CSV, CLEAN_PARQUET,
    BLR_LAT_MIN, BLR_LAT_MAX, BLR_LON_MIN, BLR_LON_MAX,
    VIOLATION_SEVERITY, DEFAULT_SEVERITY, PARKING_VIOLATION_TYPES,
    VEHICLE_BLOCKING, DEFAULT_VEHICLE_BLOCKING,
)

USECOLS = [
    "id", "latitude", "longitude", "location", "vehicle_type", "violation_type",
    "created_datetime", "police_station", "junction_name", "validation_status",
]


def parse_violation_list(s):
    """Return a clean python list of violation strings from the raw cell."""
    if pd.isna(s):
        return []
    try:
        out = ast.literal_eval(s)
        return [str(x).strip() for x in out] if isinstance(out, (list, tuple)) else [str(out).strip()]
    except Exception:
        return [str(s).strip()]


def time_bucket(hour):
    if 6 <= hour < 11:   return "Morning (06-11)"
    if 11 <= hour < 16:  return "Midday (11-16)"
    if 16 <= hour < 20:  return "Evening (16-20)"
    if 20 <= hour < 24:  return "Night (20-24)"
    return "Late night (00-06)"


def main():
    print(f"Loading {RAW_CSV.name} ...")
    df = pd.read_csv(RAW_CSV, usecols=USECOLS, low_memory=False)
    n0 = len(df)
    print(f"  raw rows: {n0:,}")

    # ---- geometry --------------------------------------------------------
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    geo_ok = (
        df["latitude"].between(BLR_LAT_MIN, BLR_LAT_MAX)
        & df["longitude"].between(BLR_LON_MIN, BLR_LON_MAX)
    )
    df = df[geo_ok].copy()
    print(f"  after geometry filter: {len(df):,}  (dropped {n0-len(df):,})")

    # ---- time ------------------------------------------------------------
    dt = pd.to_datetime(df["created_datetime"], errors="coerce", utc=True)
    df = df[dt.notna()].copy()
    dt = dt[dt.notna()]
    ist = dt.dt.tz_convert("Asia/Kolkata")
    df["ts_ist"]    = ist.dt.tz_localize(None)
    df["date"]      = ist.dt.date
    df["hour"]      = ist.dt.hour.astype("int16")
    df["dow"]       = ist.dt.dayofweek.astype("int16")          # 0=Mon
    df["dow_name"]  = ist.dt.day_name()
    df["is_weekend"] = (df["dow"] >= 5)
    df["time_bucket"] = df["hour"].map(time_bucket)

    # ---- violation parsing ----------------------------------------------
    vlists = df["violation_type"].map(parse_violation_list)
    # keep only the parking-relevant violations on each ticket
    park_lists = vlists.map(lambda lst: [v for v in lst if v in PARKING_VIOLATION_TYPES])
    is_parking = park_lists.map(len) > 0
    df = df[is_parking].copy()
    park_lists = park_lists[is_parking]
    print(f"  after parking-violation filter: {len(df):,}")

    df["n_violations"] = park_lists.map(len).astype("int16")
    # worst (max-severity) violation defines the ticket's flow impact
    def worst(lst):
        sev = [(VIOLATION_SEVERITY.get(v, DEFAULT_SEVERITY), v) for v in lst]
        return max(sev)  # (severity, name)
    worst_pairs = park_lists.map(worst)
    df["severity"] = worst_pairs.map(lambda p: p[0]).astype("float32")
    df["primary_violation"] = worst_pairs.map(lambda p: p[1])

    # ---- vehicle ---------------------------------------------------------
    vt = df["vehicle_type"].fillna("UNKNOWN").str.strip()
    df["vehicle_type"] = vt
    df["vehicle_block"] = vt.map(VEHICLE_BLOCKING).fillna(DEFAULT_VEHICLE_BLOCKING).astype("float32")

    # ---- junction --------------------------------------------------------
    jn = df["junction_name"].fillna("No Junction").str.strip()
    df["junction_name"] = jn
    df["at_junction"] = ~jn.isin(["No Junction", "NULL", ""])

    # ---- validation ------------------------------------------------------
    vs = df["validation_status"].fillna("pending").str.strip().str.lower()
    df["validation_status"] = vs
    df["is_rejected"] = (vs == "rejected")
    df["is_approved"] = (vs == "approved")
    # confidence weight: rejected tickets are likely false positives -> discount
    df["conf_weight"] = np.where(vs == "rejected", 0.25,
                          np.where(vs == "duplicate", 0.10, 1.0)).astype("float32")

    df["police_station"] = df["police_station"].fillna("UNKNOWN").str.strip()

    keep = [
        "id", "latitude", "longitude", "location", "police_station",
        "junction_name", "at_junction", "vehicle_type", "vehicle_block",
        "primary_violation", "severity", "n_violations",
        "ts_ist", "date", "hour", "dow", "dow_name", "is_weekend", "time_bucket",
        "validation_status", "is_rejected", "is_approved", "conf_weight",
    ]
    out = df[keep].reset_index(drop=True)
    out.to_parquet(CLEAN_PARQUET, index=False)

    print(f"\nWrote {CLEAN_PARQUET}  ({len(out):,} rows, {len(keep)} cols)")
    print("\nSeverity distribution (primary_violation):")
    print(out["primary_violation"].value_counts().to_string().replace("\n", "\n  "))
    print(f"\n  at a junction : {out['at_junction'].mean()*100:.1f}%")
    print(f"  rejected      : {out['is_rejected'].mean()*100:.1f}%")
    print(f"  mean severity : {out['severity'].mean():.3f}")


if __name__ == "__main__":
    main()
