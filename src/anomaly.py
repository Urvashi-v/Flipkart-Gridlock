"""
anomaly.py  —  detect EVENT-DRIVEN parking surges (festivals, sales, matches,
rallies). The problem statement calls out "events" explicitly: these are the
days a normally-quiet or normally-moderate zone suddenly spikes, and patrols
need a heads-up.

METHOD  —  robust z-score
  For each zone we model its normal daily load with the MEDIAN and the median
  absolute deviation (MAD), which (unlike mean/std) aren't dragged around by the
  very spikes we're hunting. A day is an EVENT if its count exceeds the median by
  more than Z_THRESH robust-sigma AND is materially large (guards against tiny
  zones flagging noise). Citywide spikes are flagged the same way.

OUTPUT
  outputs/events.csv          - zone-level event days, ranked by severity
  outputs/events_timeline.png - citywide daily load with event days marked
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

LABELLED = OUT_DIR / "violations_labelled.parquet"
Z_THRESH = 5.0          # robust sigmas above normal
MIN_COUNT = 25          # ignore spikes smaller than this (noise guard)
MIN_RATIO = 3.0         # and must be >= 3x the zone's normal day
CITY_Z = 2.0            # citywide spike threshold (robust sigmas)


def robust_z(series):
    med = series.median()
    mad = (series - med).abs().median()
    scale = 1.4826 * mad if mad > 0 else (series.std() or 1.0)
    return (series - med) / scale, med


def main():
    df = pd.read_parquet(LABELLED)
    z = df[df["zone"] != "__noise__"].copy()
    z["date"] = pd.to_datetime(z["date"])

    meta = z.groupby("zone").agg(
        junction_name=("junction_name", lambda s: s.mode().iloc[0]),
        police_station=("police_station", lambda s: s.mode().iloc[0]))

    daily = z.groupby(["zone", "date"]).size().rename("count").reset_index()

    events = []
    for zone, sub in daily.groupby("zone"):
        if sub["date"].nunique() < 20:           # need a baseline
            continue
        zs, med = robust_z(sub["count"])
        hits = sub[(zs >= Z_THRESH) & (sub["count"] >= MIN_COUNT) &
                   (sub["count"] >= MIN_RATIO * max(med, 1))]
        for _, r in hits.iterrows():
            events.append({
                "date": r["date"].date(), "zone": zone,
                "junction_name": meta.loc[zone, "junction_name"],
                "police_station": meta.loc[zone, "police_station"],
                "count": int(r["count"]), "normal_day": round(med, 1),
                "z_score": round(zs.loc[r.name], 1),
                "dow": r["date"].day_name(),
            })
    ev = pd.DataFrame(events).sort_values(["z_score", "count"], ascending=False)
    ev.to_csv(OUT_DIR / "events.csv", index=False)

    # citywide anomalies
    city = z.groupby("date").size().rename("count")
    czs, cmed = robust_z(city)
    city_events = city[(czs >= CITY_Z)]

    # ---- timeline plot ---------------------------------------------------
    fig, ax = plt.subplots(figsize=(13, 4.4))
    ax.plot(city.index, city.values, color="#333", lw=1.2, label="citywide daily tickets")
    ax.axhline(cmed, color="#3182bd", ls=":", label="normal day (median)")
    if len(city_events):
        ax.scatter(city_events.index, city_events.values, color="#f03b20", s=45,
                   zorder=5, label="citywide spike day")
    ax.set_title("Event detection — daily illegal-parking load with spikes flagged",
                 weight="bold", fontsize=11)
    ax.legend(fontsize=9); ax.tick_params(axis="x", rotation=30, labelsize=8)
    fig.tight_layout(); fig.savefig(OUT_DIR / "events_timeline.png", dpi=130)
    plt.close(fig)

    print(f"Zone-level event days detected: {len(ev):,}")
    print(f"Citywide spike days: {len(city_events)}")
    if len(ev):
        print("\nTOP 12 EVENT SPIKES (zone had a sudden surge):")
        show = ev.head(12)[["date", "dow", "junction_name", "police_station",
                            "count", "normal_day", "z_score"]]
        print(show.to_string(index=False))
    print("\nWrote events.csv, events_timeline.png")


if __name__ == "__main__":
    main()
