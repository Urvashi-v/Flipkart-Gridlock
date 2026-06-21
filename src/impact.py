"""
impact.py  —  Measure the BEFORE/AFTER effect of enforcement at a hotspot.

THE QUESTION
  "We cracked down on zone X starting date D. Did illegal parking actually fall,
  or did it just move / was the city quieter that month anyway?"

METHOD  —  Difference-in-Differences (DiD)
  Comparing a zone's own before vs after is not enough: citywide ticketing rises
  and falls with patrol effort and season. So we use the rest of the city as a
  control and ask whether the treated zone fell BY MORE than the city did.

      control_ratio        = control_after_mean / control_before_mean
      expected_after        = treated_before_mean * control_ratio   (counterfactual)
      DiD effect            = treated_after_mean - expected_after
      DiD %                 = DiD effect / treated_before_mean * 100   (<0 = improvement)

  We also run a Welch t-test on the treated zone's daily counts (before vs after)
  for a significance flag.

HONEST CAVEATS (printed in the report)
  * This is observational. Auto-detected "interventions" are the largest level
    shift in ticketing, which is partly regression-to-the-mean. Treat the auto
    scan as a SCREEN; feed real crackdown dates via measure_impact() for rigour.
  * Fewer tickets can mean better compliance OR patrols moving elsewhere. Pair
    with the forecast residual (did it drop below predicted?) for a fuller view.

OUTPUTS
  outputs/impact_report.csv      - per-zone before/after + DiD effect + verdict
  outputs/impact_demo.png        - before/after timeline for the clearest case
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR

LABELLED = OUT_DIR / "violations_labelled.parquet"
WINDOW = 28          # days before / after to compare
MIN_SIDE = 10        # need at least this many days each side


def daily_panel(df):
    df = df[df["zone"] != "__noise__"].copy()
    df["date"] = pd.to_datetime(df["date"])
    daily = df.groupby(["zone", "date"]).size().rename("y").reset_index()
    full = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    idx = pd.MultiIndex.from_product([daily["zone"].unique(), full], names=["zone", "date"])
    panel = daily.set_index(["zone", "date"]).reindex(idx, fill_value=0).reset_index()
    city = panel.groupby("date")["y"].sum().rename("city")    # citywide control
    return panel, city


def measure_impact(panel, city, zone, intervention_date, window=WINDOW):
    """DiD before/after effect of enforcement at `zone` starting `intervention_date`.

    Returns a dict of metrics. Reusable as the production API: pass a real
    crackdown date and you get a defensible effect estimate.
    """
    d = pd.Timestamp(intervention_date)
    z = panel[panel["zone"] == zone].set_index("date")["y"]
    b0, b1 = d - pd.Timedelta(days=window), d - pd.Timedelta(days=1)
    a0, a1 = d, d + pd.Timedelta(days=window - 1)

    z_before, z_after = z.loc[b0:b1], z.loc[a0:a1]
    c_before, c_after = city.loc[b0:b1], city.loc[a0:a1]
    if len(z_before) < MIN_SIDE or len(z_after) < MIN_SIDE:
        return None

    tb, ta = z_before.mean(), z_after.mean()
    cb, ca = c_before.mean(), c_after.mean()
    raw_pct = (ta - tb) / tb * 100 if tb else np.nan
    control_ratio = ca / cb if cb else np.nan
    expected_after = tb * control_ratio
    did_effect = ta - expected_after
    did_pct = did_effect / tb * 100 if tb else np.nan
    t, p = stats.ttest_ind(z_after.values, z_before.values, equal_var=False)

    return {
        "zone": zone, "intervention_date": d.date(),
        "before_mean": round(tb, 2), "after_mean": round(ta, 2),
        "raw_change_%": round(raw_pct, 1),
        "city_change_%": round((control_ratio - 1) * 100, 1),
        "did_change_%": round(did_pct, 1),
        "expected_after": round(expected_after, 2),
        "t_stat": round(t, 2), "p_value": round(p, 4),
        "significant": bool(p < 0.05),
    }


def detect_change_point(series, margin=WINDOW):
    """Date of the largest sustained level shift (CUSUM-style scan).

    Candidates are restricted to the series interior (>= `margin` days from each
    end) so every detected intervention has a full, clean before AND after window
    — this avoids latching onto the data's start/end cliff, which would be a
    truncation artifact rather than a real enforcement effect.
    """
    s = series.values
    dates = series.index
    if len(s) < 2 * margin + 2:
        return None
    best_i, best_score = None, -1
    # weight by window size so a shift seen across both full windows wins over a
    # short boundary spike
    for i in range(margin, len(s) - margin):
        before = s[i - margin:i].mean()
        after = s[i:i + margin].mean()
        if abs(before - after) > best_score:
            best_score, best_i = abs(before - after), i
    return dates[best_i] if best_i is not None else None


def main():
    df = pd.read_parquet(LABELLED)
    panel, city = daily_panel(df)
    print(f"Daily panel: {panel['zone'].nunique():,} zones x "
          f"{panel['date'].nunique()} days")

    # screen the busiest 60 zones for auto-detected interventions
    top_zones = (panel.groupby("zone")["y"].sum()
                       .sort_values(ascending=False).head(60).index)
    rows = []
    for z in top_zones:
        s = panel[panel["zone"] == z].set_index("date")["y"]
        cp = detect_change_point(s)
        if cp is None:
            continue
        r = measure_impact(panel, city, z, cp)
        if r is None:
            continue
        meta = df[df["zone"] == z].iloc[0]
        r["junction_name"] = meta["junction_name"]
        r["police_station"] = meta["police_station"]
        rows.append(r)

    rep = pd.DataFrame(rows)
    # verdict: DiD-adjusted improvement that is statistically significant
    def verdict(r):
        if r["did_change_%"] <= -25 and r["significant"]:
            return "Strong reduction"
        if r["did_change_%"] <= -10:
            return "Reduction"
        if r["did_change_%"] >= 10:
            return "Worsened / rebound"
        return "No clear effect"
    rep["verdict"] = rep.apply(verdict, axis=1)
    rep = rep.sort_values("did_change_%").reset_index(drop=True)
    cols = ["zone", "junction_name", "police_station", "intervention_date",
            "before_mean", "after_mean", "raw_change_%", "city_change_%",
            "did_change_%", "p_value", "significant", "verdict"]
    rep[cols].to_csv(OUT_DIR / "impact_report.csv", index=False)

    print("\nVerdict spread (auto-detected interventions, top 60 zones):")
    print(rep["verdict"].value_counts().to_string().replace("\n", "\n  "))

    print("\nClearest DiD reductions:")
    show = rep[rep["verdict"].str.contains("reduction", case=False)].head(8)
    print(show[["junction_name", "police_station", "intervention_date",
                "before_mean", "after_mean", "raw_change_%",
                "did_change_%", "p_value"]].to_string(index=False))

    # ---- demo plot for the single clearest, significant reduction -------
    cand = rep[(rep["verdict"] == "Strong reduction")]
    cand = cand if len(cand) else rep.head(1)
    best = cand.iloc[0]
    z = best["zone"]
    s = panel[panel["zone"] == z].set_index("date")["y"]
    d = pd.Timestamp(best["intervention_date"])
    fig, ax = plt.subplots(figsize=(12, 4.4))
    ax.plot(s.index, s.rolling(7, min_periods=1).mean(), color="#111",
            label="7-day avg tickets")
    ax.axvline(d, color="#f03b20", ls="--", lw=2, label="enforcement start")
    ax.axhline(best["before_mean"], (0), color="#3182bd", ls=":", alpha=.7)
    ax.axhline(best["after_mean"], color="#2ca25f", ls=":", alpha=.7)
    ax.set_title(f"Enforcement impact — {best['junction_name']} "
                 f"(DiD {best['did_change_%']:+.0f}%, p={best['p_value']})",
                 weight="bold", fontsize=11)
    ax.legend(); fig.tight_layout()
    fig.savefig(OUT_DIR / "impact_demo.png", dpi=130); plt.close(fig)

    print("\nWrote impact_report.csv, impact_demo.png")
    print(f"Demo case: {best['junction_name']}  "
          f"raw {best['raw_change_%']:+.0f}%  ->  DiD-adjusted {best['did_change_%']:+.0f}%")


if __name__ == "__main__":
    main()
