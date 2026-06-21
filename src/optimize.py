"""
optimize.py  —  turn the priority list into an ACTUAL DEPLOYMENT PLAN and prove
its ROI. Given a fixed number of patrol-shifts per day, where and when should
they go to address the most illegal parking?

HOW
  1. Merge the 150 m cells into deployable ENFORCEMENT POINTS — a named junction,
     or (for off-junction spots) a ~100 m location — so one patrol = one real
     place, not six adjacent grid cells of the same junction.
  2. For each point: its total violations, its busiest contiguous 3-hour window,
     and the share of daily violations inside that window.
  3. Capturable impact = point violations × window_share × capture_rate.
  4. Points are independent locations, so the optimal K patrol-shifts are simply
     the top-K points by capturable impact (greedy = optimal). Whack-a-mole
     points are tagged "treat as corridor".
  5. Two ROI numbers: violations CONCENTRATED in the top-K points, and the share
     realistically CAPTURED after the window/capture discount.

OUTPUT
  outputs/deployment_plan.csv      - the roster of distinct enforcement points
  outputs/optimize_coverage.png    - impact concentration vs number of patrols
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR, OPT

LABELLED = OUT_DIR / "violations_labelled.parquet"
HOTSPOTS = OUT_DIR / "hotspots.csv"


def shift_name(h):
    if 6 <= h < 11:  return "A Morning (06-11)"
    if 11 <= h < 16: return "B Midday (11-16)"
    if 16 <= h < 20: return "C Evening (16-20)"
    if 20 <= h < 24: return "D Night (20-24)"
    return "E Late-night (00-06)"


def peak_window(hour_counts):
    total = hour_counts.sum()
    best_h, best_v = 0, -1
    for h in range(24):
        v = sum(hour_counts.get((h + k) % 24, 0) for k in range(3))
        if v > best_v:
            best_h, best_v = h, v
    return best_h, (best_v / total if total else 0.0)


def point_key(row):
    jn = str(row["junction_name"])
    if jn and jn not in ("No Junction", "nan", "NULL"):
        return jn
    return f"@{round(row['lat'], 3)},{round(row['lon'], 3)}"


def main():
    df = pd.read_parquet(LABELLED)
    z = df[df["zone"] != "__noise__"].copy()
    hot = pd.read_csv(HOTSPOTS)

    # cell -> enforcement point
    hot["point"] = hot.apply(point_key, axis=1)
    cell2point = dict(zip(hot["zone"], hot["point"]))
    z["point"] = z["zone"].map(cell2point)
    z = z[z["point"].notna()]

    # aggregate violations + metadata per point
    fp = (hot.groupby("point")
             .agg(violations=("n_tickets", "sum"),
                  lat=("lat", "mean"), lon=("lon", "mean"),
                  junction_name=("junction_name", lambda s: s.mode().iloc[0]),
                  police_station=("police_station", lambda s: s.mode().iloc[0]),
                  cells=("zone", "nunique"))
             .reset_index())

    # peak window per point (from the tickets mapped to it)
    rows = []
    for pt, sub in z.groupby("point"):
        h, share = peak_window(sub["hour"].value_counts())
        rows.append((pt, h, share, sub["dow_name"].mode().iloc[0]))
    win = pd.DataFrame(rows, columns=["point", "peak_h", "window_share", "busiest_dow"])

    plan = fp.merge(win, on="point", how="left")
    cr = OPT["capture_rate"]
    plan["capturable_viol"] = plan["violations"] * plan["window_share"] * cr

    # corridor flag from displacement analysis (map zones -> points)
    dpath = OUT_DIR / "displacement_report.csv"
    if dpath.exists():
        disp = pd.read_csv(dpath)
        wm_pts = {cell2point.get(zn) for zn in
                  disp.loc[disp["verdict"].astype(str).str.startswith("Displacement"), "zone"]}
        plan["corridor"] = plan["point"].isin(wm_pts)
    else:
        plan["corridor"] = False

    plan = plan.sort_values("capturable_viol", ascending=False).reset_index(drop=True)
    plan.insert(0, "priority", np.arange(1, len(plan) + 1))

    total = plan["violations"].sum() or 1.0
    plan["cum_located_%"] = plan["violations"].cumsum() / total * 100      # concentration
    plan["cum_captured_%"] = plan["capturable_viol"].cumsum() / total * 100  # realistic

    plan["window"] = plan["peak_h"].map(lambda h: f"{int(h):02d}:00-{int((h+3)%24):02d}:00")
    plan["shift"] = plan["peak_h"].map(shift_name)

    K = OPT["patrol_slots_per_day"]
    cols = ["priority", "junction_name", "police_station", "window", "shift",
            "busiest_dow", "violations", "capturable_viol",
            "cum_located_%", "cum_captured_%", "corridor", "cells", "lat", "lon"]
    plan[cols].to_csv(OUT_DIR / "deployment_plan.csv", index=False)

    locK = plan["cum_located_%"].iloc[min(K, len(plan)) - 1]
    capK = plan["cum_captured_%"].iloc[min(K, len(plan)) - 1]

    # ---- coverage curve --------------------------------------------------
    fig, ax = plt.subplots(figsize=(8.8, 5))
    n = np.arange(1, len(plan) + 1)
    ax.plot(n, plan["cum_located_%"], color="#3182bd", lw=2,
            label="violations concentrated in top-N points")
    ax.plot(n, plan["cum_captured_%"], color="#2ca25f", lw=2,
            label=f"realistically captured (capture {cr:.0%})")
    ax.axvline(K, color="#f03b20", ls="--", lw=2)
    ax.annotate(f"{K} patrol-shifts/day\ncover {locK:.0f}% of all violations,\ncapture ~{capK:.0f}%",
                (K, locK), xytext=(K + 18, locK - 26), fontsize=10, weight="bold",
                arrowprops=dict(arrowstyle="->", color="#f03b20"))
    ax.set_xlabel("enforcement points covered (ranked by capturable impact)")
    ax.set_ylabel("% of citywide illegal-parking violations")
    ax.set_title("Enforcement ROI — targeted deployment coverage curve",
                 weight="bold", fontsize=12)
    ax.set_xlim(0, min(150, len(plan))); ax.set_ylim(0, 100)
    ax.legend(fontsize=9); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(OUT_DIR / "optimize_coverage.png", dpi=130)
    plt.close(fig)

    print(f"Distinct enforcement points: {len(plan):,}")
    print(f"Citywide violations covered : {int(total):,}")
    print(f"Top {K} points hold {locK:.0f}% of all violations; "
          f"patrolling them captures ~{capK:.0f}%.")
    print(f"\nDEPLOYMENT ROSTER (top {min(K,15)} of {K}):")
    show = plan.head(min(K, 15))[["priority", "junction_name", "police_station",
                                  "window", "busiest_dow", "violations",
                                  "cum_located_%", "corridor"]].copy()
    show["cum_located_%"] = show["cum_located_%"].round(1)
    print(show.to_string(index=False))
    print("\nWrote deployment_plan.csv, optimize_coverage.png")


if __name__ == "__main__":
    main()
