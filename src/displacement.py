"""
displacement.py  —  the "whack-a-mole" detector.

THE QUESTION
  When we enforce a hotspot, does illegal parking actually go away — or does it
  just hop to the next street? A drop at the treated zone is only a real win if
  the cars don't reappear next door.

METHOD
  For each intervention (zone X, date D) we:
    1. find X's spatial NEIGHBOURS — zones whose centroid is within RADIUS_M;
    2. measure the treated zone's before/after drop (tickets/day removed);
    3. measure the neighbours' before/after change, DiD-adjusted against the
       citywide trend (so we don't blame enforcement for a city-wide rise);
    4. displacement_% = neighbour DiD gain / treated drop.

  Verdict:
    * Displacement (whack-a-mole) : treated fell but neighbours rose to absorb it
    * Genuine reduction           : treated fell, neighbours flat/also fell
                                    (= diffusion of benefit — the ideal outcome)
    * Inconclusive                : treated didn't fall, or no neighbours

WHY it matters
  It tells enforcement whether to treat a hotspot in ISOLATION or as a CORRIDOR
  (saturate the zone + its neighbours together). That is the difference between
  moving the problem and solving it.

OUTPUTS
  outputs/displacement_report.csv   - per-intervention displacement verdict
  outputs/displacement_demo.png     - treated vs neighbours, before/after
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR, EARTH_RADIUS_M
from impact import daily_panel, detect_change_point, WINDOW, MIN_SIDE

RADIUS_M = 400          # a zone's "neighbourhood" — adjacent blocks/approaches
LABELLED = OUT_DIR / "violations_labelled.parquet"


def zone_centroids(df):
    z = df[df["zone"] != "__noise__"]
    c = z.groupby("zone").agg(lat=("latitude", "mean"), lon=("longitude", "mean"),
                              n=("id", "size"),
                              junction_name=("junction_name", lambda s: s.mode().iloc[0]),
                              police_station=("police_station", lambda s: s.mode().iloc[0]))
    return c


def neighbours_within(centroids, zone, radius_m=RADIUS_M):
    """Zones whose centroid is within radius_m of `zone` (excluding itself)."""
    lat0, lon0 = np.radians(centroids.loc[zone, ["lat", "lon"]].astype(float))
    lat = np.radians(centroids["lat"].to_numpy())
    lon = np.radians(centroids["lon"].to_numpy())
    d = 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(
        np.sin((lat - lat0) / 2) ** 2 +
        np.cos(lat0) * np.cos(lat) * np.sin((lon - lon0) / 2) ** 2))
    out = centroids.index[(d <= radius_m) & (d > 0)]
    return list(out)


def series_for(panel, zones):
    """Daily summed series for a set of zones, indexed by date."""
    sub = panel[panel["zone"].isin(zones)]
    return sub.groupby("date")["y"].sum()


def measure_displacement(panel, city, centroids, zone, d, window=WINDOW):
    neigh = neighbours_within(centroids, zone)
    if not neigh:
        return None
    d = pd.Timestamp(d)
    b0, b1 = d - pd.Timedelta(days=window), d - pd.Timedelta(days=1)
    a0, a1 = d, d + pd.Timedelta(days=window - 1)

    tz = panel[panel["zone"] == zone].set_index("date")["y"]
    nz = series_for(panel, neigh)
    if len(tz.loc[b0:b1]) < MIN_SIDE or len(tz.loc[a0:a1]) < MIN_SIDE:
        return None

    tb, ta = tz.loc[b0:b1].mean(), tz.loc[a0:a1].mean()
    nb, na = nz.loc[b0:b1].mean(), nz.loc[a0:a1].mean()
    cb, ca = city.loc[b0:b1].mean(), city.loc[a0:a1].mean()
    cratio = ca / cb if cb else 1.0

    treated_drop = tb - ta                       # tickets/day removed at X
    neigh_expected = nb * cratio                 # what neighbours would do anyway
    neigh_gain = na - neigh_expected             # DiD-adjusted neighbour change
    disp_pct = (neigh_gain / treated_drop * 100) if treated_drop > 0.5 else np.nan

    if treated_drop <= 0.5:
        verdict = "Inconclusive (no drop)"
    elif disp_pct >= 40:
        verdict = "Displacement (whack-a-mole)"
    elif disp_pct <= 10:
        verdict = "Genuine reduction"
    else:
        verdict = "Partial displacement"

    return {
        "zone": zone, "intervention_date": d.date(), "n_neighbours": len(neigh),
        "treated_before": round(tb, 2), "treated_after": round(ta, 2),
        "treated_drop": round(treated_drop, 2),
        "neigh_before": round(nb, 2), "neigh_after": round(na, 2),
        "neigh_expected": round(neigh_expected, 2),
        "neigh_gain": round(neigh_gain, 2),
        "displacement_%": round(disp_pct, 1) if not np.isnan(disp_pct) else np.nan,
        "verdict": verdict, "_neigh": neigh,
    }


def main():
    df = pd.read_parquet(LABELLED)
    panel, city = daily_panel(df)
    centroids = zone_centroids(df)
    print(f"Daily panel: {panel['zone'].nunique():,} zones; neighbourhood "
          f"radius {RADIUS_M} m")

    top_zones = (panel.groupby("zone")["y"].sum()
                       .sort_values(ascending=False).head(60).index)
    rows = []
    for z in top_zones:
        s = panel[panel["zone"] == z].set_index("date")["y"]
        cp = detect_change_point(s)
        if cp is None:
            continue
        r = measure_displacement(panel, city, centroids, z, cp)
        if r is None:
            continue
        r["junction_name"] = centroids.loc[z, "junction_name"]
        r["police_station"] = centroids.loc[z, "police_station"]
        rows.append(r)

    rep = pd.DataFrame(rows)
    cols = ["zone", "junction_name", "police_station", "intervention_date",
            "n_neighbours", "treated_before", "treated_after", "treated_drop",
            "neigh_before", "neigh_after", "neigh_gain", "displacement_%", "verdict"]
    rep[cols].to_csv(OUT_DIR / "displacement_report.csv", index=False)

    print("\nVerdict spread:")
    print(rep["verdict"].value_counts().to_string().replace("\n", "\n  "))

    print("\nClearest whack-a-mole cases (violations moved next door):")
    wm = rep[rep["verdict"].str.startswith("Displacement")] \
        .sort_values("displacement_%", ascending=False)
    show = wm.head(6)[["junction_name", "police_station", "treated_drop",
                       "neigh_gain", "displacement_%"]]
    print(show.to_string(index=False) if len(show) else "  (none in top zones)")

    # ---- demo plot: clearest whack-a-mole (else clearest genuine) --------
    if len(wm):
        best = wm.iloc[0]; title_tag = "Displacement"
    else:
        gr = rep[rep["verdict"] == "Genuine reduction"]
        best = (gr.iloc[0] if len(gr) else rep.iloc[0]); title_tag = best["verdict"]

    z = best["zone"]; d = pd.Timestamp(best["intervention_date"])
    tz = panel[panel["zone"] == z].set_index("date")["y"].rolling(7, min_periods=1).mean()
    nz = series_for(panel, best["_neigh"]).rolling(7, min_periods=1).mean()
    fig, ax = plt.subplots(figsize=(12, 4.4))
    ax.plot(tz.index, tz.values, color="#111", lw=2, label=f"treated zone ({z})")
    ax.plot(nz.index, nz.values, color="#3182bd", lw=2, label=f"neighbours (≤{RADIUS_M} m)")
    ax.axvline(d, color="#f03b20", ls="--", lw=2, label="enforcement start")
    ax.set_title(f"{title_tag} — {best['junction_name']}  "
                 f"(treated −{best['treated_drop']:.0f}/day, "
                 f"neighbours {best['neigh_gain']:+.0f}/day, "
                 f"displacement {best['displacement_%']:.0f}%)",
                 weight="bold", fontsize=10.5)
    ax.set_ylabel("7-day avg tickets/day"); ax.legend(fontsize=9)
    fig.tight_layout(); fig.savefig(OUT_DIR / "displacement_demo.png", dpi=130)
    plt.close(fig)

    print("\nWrote displacement_report.csv, displacement_demo.png")


if __name__ == "__main__":
    main()
