"""
hotspots.py  —  Step 3: detect illegal-parking HOTSPOTS (enforcement zones) and
score each one's CONGESTION IMPACT. This is the heart of the solution.

HOW
  1. Snap every violation to a ~150 m grid cell. Each cell with enough tickets
     is a "zone" — a bounded, patrol-able piece of road. (We tried DBSCAN first;
     density chaining merged entire commercial corridors into 1.8 km blobs that
     no patrol could action, so a uniform grid is the correct unit here.)
  2. For every zone we compute five signals, each a proxy for how much that zone
     hurts traffic flow:
         volume      - weighted ticket count (chronic pressure)
         severity    - how flow-blocking its violations are
         junction    - share of tickets at/near an intersection
         vehicle     - how large/blocking the parked vehicles are
         persistence - spread across days & hours (chronic vs one-off event)
  3. Each signal is min-max normalised across zones, then combined with the
     weights in config.CIS_WEIGHTS into a 0-100 Congestion Impact Score (CIS).

WHY a composite score
  The brief asks us to "quantify impact on traffic flow." We have no live speed
  feed, so we build a transparent, weight-tunable index from the signals that DO
  drive congestion. Every component is auditable and the weights live in config.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import (
    CLEAN_PARQUET, OUT_DIR, M_PER_DEG_LAT,
    GRID_SIZE_M, MIN_ZONE_TICKETS, CIS_WEIGHTS,
    BLR_LAT_MIN, BLR_LAT_MAX, BLR_LON_MIN,
)

HOTSPOTS_CSV = OUT_DIR / "hotspots.csv"
LABELLED_PARQUET = OUT_DIR / "violations_labelled.parquet"


def minmax(s):
    lo, hi = s.min(), s.max()
    if hi - lo < 1e-12:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo)


def mode_or_na(s):
    m = s.mode()
    return m.iloc[0] if len(m) else np.nan


def assign_grid(df):
    """Snap lat/lon to a GRID_SIZE_M cell; return integer (row, col) ids.

    The grid is anchored to a FIXED origin (the Bengaluru bounding box), not the
    data's min — so adding records (ingestion) never reshuffles existing zone
    ids; it only adds new cells. Stable, reproducible zoning across rebuilds."""
    lat0, lon0 = BLR_LAT_MIN, BLR_LON_MIN
    mid_lat = np.radians((BLR_LAT_MIN + BLR_LAT_MAX) / 2)
    cell_lat = GRID_SIZE_M / M_PER_DEG_LAT
    cell_lon = GRID_SIZE_M / (M_PER_DEG_LAT * np.cos(mid_lat))
    row = np.floor((df["latitude"] - lat0) / cell_lat).astype(int)
    col = np.floor((df["longitude"] - lon0) / cell_lon).astype(int)
    return row, col


def main():
    df = pd.read_parquet(CLEAN_PARQUET)
    print(f"Loaded {len(df):,} violations.")

    # ---- grid zoning -----------------------------------------------------
    row, col = assign_grid(df)
    df["zone"] = row.astype(str) + "_" + col.astype(str)
    counts = df["zone"].value_counts()
    valid_zones = counts[counts >= MIN_ZONE_TICKETS].index
    df["zone"] = df["zone"].where(df["zone"].isin(valid_zones), other="__noise__")

    n_zones = len(valid_zones)
    noise = (df["zone"] == "__noise__").sum()
    print(f"Grid zoning (cell={GRID_SIZE_M} m, min={MIN_ZONE_TICKETS} tickets):")
    print(f"  enforcement zones : {n_zones:,}")
    print(f"  sparse/noise      : {noise:,} ({noise/len(df)*100:.1f}%)")

    df.to_parquet(LABELLED_PARQUET, index=False)

    # ---- aggregate per zone ---------------------------------------------
    total_days = max((df["ts_ist"].max() - df["ts_ist"].min()).days, 1)
    z = df[df["zone"] != "__noise__"].copy()

    g = z.groupby("zone")
    agg = pd.DataFrame({
        "n_tickets":      g.size(),
        "w_tickets":      g["conf_weight"].sum(),       # rejected discounted
        "lat":            g["latitude"].mean(),
        "lon":            g["longitude"].mean(),
        "sev_mean":       g["severity"].mean(),
        "junction_share": g["at_junction"].mean(),
        "veh_mean":       g["vehicle_block"].mean(),
        "n_days":         g["date"].nunique(),
        "n_hours":        g["hour"].nunique(),
        "approved_share": g["is_approved"].mean(),
        "rejected_share": g["is_rejected"].mean(),
        "top_violation":  g["primary_violation"].agg(mode_or_na),
        "top_vehicle":    g["vehicle_type"].agg(mode_or_na),
        "police_station": g["police_station"].agg(mode_or_na),
        "junction_name":  g["junction_name"].agg(mode_or_na),
        "address":        g["location"].agg(mode_or_na),
        "peak_hour":      g["hour"].agg(mode_or_na),
        "peak_dow":       g["dow_name"].agg(mode_or_na),
    }).reset_index()

    # persistence: how spread across the calendar and the clock (0-1 each)
    agg["persistence"] = (
        0.6 * (agg["n_days"] / total_days) + 0.4 * (agg["n_hours"] / 24.0)
    )

    # ---- five normalised components -------------------------------------
    agg["c_volume"]      = minmax(np.log1p(agg["w_tickets"]))
    agg["c_severity"]    = minmax(agg["sev_mean"])
    agg["c_junction"]    = agg["junction_share"]           # already 0-1
    agg["c_vehicle"]     = minmax(agg["veh_mean"])
    agg["c_persistence"] = minmax(agg["persistence"])

    w = CIS_WEIGHTS
    agg["CIS"] = 100 * (
        w["volume"]      * agg["c_volume"] +
        w["severity"]    * agg["c_severity"] +
        w["junction"]    * agg["c_junction"] +
        w["vehicle"]     * agg["c_vehicle"] +
        w["persistence"] * agg["c_persistence"]
    )
    agg = agg.sort_values("CIS", ascending=False).reset_index(drop=True)
    agg.insert(0, "rank", np.arange(1, len(agg) + 1))

    # enforcement priority tier
    agg["tier"] = pd.cut(agg["CIS"], bins=[-1, 25, 45, 65, 101],
                         labels=["Low", "Medium", "High", "Critical"])

    agg.to_csv(HOTSPOTS_CSV, index=False)
    print(f"\nWrote {HOTSPOTS_CSV}  ({len(agg):,} zones)")

    # ---- console summary -------------------------------------------------
    print("\nTier counts:")
    print(agg["tier"].value_counts().reindex(["Critical","High","Medium","Low"])
          .to_string().replace("\n", "\n  "))

    cols = ["rank", "CIS", "tier", "n_tickets", "sev_mean", "junction_share",
            "peak_hour", "top_violation", "police_station", "junction_name"]
    pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30)
    print("\nTOP 15 ENFORCEMENT-PRIORITY HOTSPOTS:")
    show = agg[cols].head(15).copy()
    show["CIS"] = show["CIS"].round(1)
    show["sev_mean"] = show["sev_mean"].round(2)
    show["junction_share"] = (show["junction_share"]*100).round(0).astype(int).astype(str) + "%"
    print(show.to_string(index=False))


if __name__ == "__main__":
    main()
