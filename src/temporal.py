"""
temporal.py  —  Step 5: WHEN does illegal parking choke the city, and what
patrol schedule does that imply? Turns the system from reactive to proactive.

Outputs:
  outputs/temporal_hour_dow.png     - hour x weekday demand heatmap
  outputs/violation_mix.png         - violation-type + vehicle-type breakdown
  outputs/patrol_schedule.csv       - per top-zone recommended enforcement window
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR

LABELLED_PARQUET = OUT_DIR / "violations_labelled.parquet"
HOTSPOTS_CSV = OUT_DIR / "hotspots.csv"
DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def shift_for_hour(h):
    if 6 <= h < 11:  return "A -Morning (06-11)"
    if 11 <= h < 16: return "B -Midday (11-16)"
    if 16 <= h < 20: return "C -Evening (16-20)"
    if 20 <= h < 24: return "D -Night (20-24)"
    return "E -Late-night (00-06)"


def hour_dow_heatmap(df):
    pivot = (df.assign(w=df["severity"])
               .pivot_table(index="dow_name", columns="hour", values="w",
                            aggfunc="sum", fill_value=0)
               .reindex(DOW_ORDER))
    fig, ax = plt.subplots(figsize=(13, 4.6))
    im = ax.imshow(pivot.values, aspect="auto", cmap="inferno")
    ax.set_xticks(range(24)); ax.set_xticklabels(range(24), fontsize=8)
    ax.set_yticks(range(7)); ax.set_yticklabels(DOW_ORDER, fontsize=9)
    ax.set_xlabel("Hour of day (IST)"); ax.set_title(
        "Illegal-parking congestion pressure  (severity-weighted volume)  - hour × weekday",
        fontsize=11, weight="bold")
    cbar = fig.colorbar(im, ax=ax, pad=0.01); cbar.set_label("severity-weighted tickets")
    # mark the single hottest cell
    yi, xi = np.unravel_index(np.argmax(pivot.values), pivot.shape)
    ax.add_patch(plt.Rectangle((xi-.5, yi-.5), 1, 1, fill=False, edgecolor="cyan", lw=2))
    fig.tight_layout(); fig.savefig(OUT_DIR / "temporal_hour_dow.png", dpi=130)
    plt.close(fig)
    return pivot


def violation_mix(df):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    vc = df["primary_violation"].value_counts().head(8)[::-1]
    axes[0].barh(vc.index, vc.values, color="#f03b20")
    axes[0].set_title("Primary violation type", weight="bold", fontsize=11)
    axes[0].tick_params(labelsize=8)
    for i, v in enumerate(vc.values):
        axes[0].text(v, i, f" {v:,}", va="center", fontsize=8)

    vt = df["vehicle_type"].value_counts().head(10)[::-1]
    axes[1].barh(vt.index, vt.values, color="#3182bd")
    axes[1].set_title("Vehicle type", weight="bold", fontsize=11)
    axes[1].tick_params(labelsize=8)
    for i, v in enumerate(vt.values):
        axes[1].text(v, i, f" {v:,}", va="center", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT_DIR / "violation_mix.png", dpi=130)
    plt.close(fig)


def patrol_schedule(df, hot):
    """For each top zone, find its busiest (hour, weekday) windows -> a shift."""
    top = hot.head(60).copy()
    z = df[df["zone"].isin(top["zone"])]
    rows = []
    for _, r in top.iterrows():
        sub = z[z["zone"] == r["zone"]]
        by_hour = sub.groupby("hour").size()
        # contiguous 3-hour window with the most tickets
        best_h, best_v = 0, -1
        for h in range(24):
            v = sum(by_hour.get((h + k) % 24, 0) for k in range(3))
            if v > best_v:
                best_h, best_v = h, v
        window = f"{best_h:02d}:00-{(best_h+3)%24:02d}:00"
        rows.append({
            "rank": int(r["rank"]), "CIS": round(r["CIS"], 1), "tier": r["tier"],
            "junction_name": r["junction_name"], "police_station": r["police_station"],
            "n_tickets": int(r["n_tickets"]),
            "busiest_weekday": sub["dow_name"].mode().iloc[0],
            "patrol_window": window,
            "recommended_shift": shift_for_hour(best_h),
            "window_share_%": round(best_v / len(sub) * 100, 1),
            "lat": round(r["lat"], 6), "lon": round(r["lon"], 6),
        })
    out = pd.DataFrame(rows)
    out.to_csv(OUT_DIR / "patrol_schedule.csv", index=False)
    return out


def main():
    df = pd.read_parquet(LABELLED_PARQUET)
    hot = pd.read_csv(HOTSPOTS_CSV)

    pivot = hour_dow_heatmap(df)
    violation_mix(df)
    sched = patrol_schedule(df, hot)

    print("Wrote temporal_hour_dow.png, violation_mix.png, patrol_schedule.csv")
    peak = df.groupby("hour").size()
    print(f"\nCitywide peak hour : {peak.idxmax():02d}:00  ({peak.max():,} tickets)")
    print("Hourly profile (severity-weighted share):")
    hp = (df.assign(w=df['severity']).groupby('hour')['w'].sum())
    hp = (hp / hp.sum() * 100)
    bars = "".join("#" if hp[h] > hp.mean() else "." for h in range(24))
    print("  00" + " "*6 + "06" + " "*6 + "12" + " "*6 + "18" + " "*4 + "23")
    print("  " + bars)

    print("\nShift load (severity-weighted):")
    sl = df.assign(sh=df["hour"].map(shift_for_hour), w=df["severity"]) \
           .groupby("sh")["w"].sum().sort_values(ascending=False)
    for k, v in sl.items():
        print(f"  {k:24s} {v/sl.sum()*100:5.1f}%")

    print("\nSample patrol schedule (top 8 zones):")
    print(sched[["rank","junction_name","patrol_window","busiest_weekday",
                 "recommended_shift","window_share_%"]].head(8).to_string(index=False))


if __name__ == "__main__":
    main()
