"""
briefing.py  —  the field artifact: a printable ONE-PAGE ENFORCEMENT BRIEFING per
top hotspot that a patrol commander can hand out at roll-call. Bundled into a
single PDF (outputs/briefing_pack.pdf).

Each page answers, for one zone: where, why it's a hotspot, what it costs traffic,
when to be there, what to expect next week, whether enforcing it just moves the
problem, and the recommended action. A locator map and the zone's hourly profile
give the officer instant context.

Built with matplotlib's PdfPages so it has zero extra dependencies and renders
identically everywhere.
"""
import sys
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR

LABELLED = OUT_DIR / "violations_labelled.parquet"
TOP_N = 20
TIER_COLOR = {"Critical": "#b10026", "High": "#f03b20", "Medium": "#fb9a29", "Low": "#4e79a7"}


def opt(path, key=None):
    p = OUT_DIR / path
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    return df


def shift_for_hour(h):
    if 6 <= h < 11:  return "Morning shift (06:00-11:00)"
    if 11 <= h < 16: return "Midday shift (11:00-16:00)"
    if 16 <= h < 20: return "Evening shift (16:00-20:00)"
    if 20 <= h < 24: return "Night shift (20:00-24:00)"
    return "Late-night shift (00:00-06:00)"


def recommend(row, ctx, disp_flag, fcast):
    acts = []
    if disp_flag:
        acts.append("CORRIDOR action: enforce this point AND adjacent streets "
                    "(within 400 m) together — isolated enforcement here historically "
                    "pushed parking next door.")
    else:
        acts.append("Targeted action: station a unit in the peak window; "
                    "tow/penalise repeat offenders.")
    if "Market" in ctx:
        acts.append("Coordinate with market association on loading bays / timed parking.")
    elif "Metro" in ctx or "Transit" in ctx:
        acts.append("Push last-mile parking to sanctioned lots; mark no-parking on approaches.")
    elif "Mall" in ctx or "Shopping" in ctx:
        acts.append("Engage mall management on valet overflow and feeder-road clearance.")
    elif "Hospital" in ctx:
        acts.append("Reserve emergency-vehicle lanes; designate visitor drop-off.")
    if fcast and fcast > 0:
        acts.append(f"Forecast: ~{fcast:.0f} violations expected here next week — pre-plan.")
    return acts


def page(pdf, r, allpts, zser, ctx, disp_flag, fcast):
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.patch.set_facecolor("white")
    tier = str(r.get("tier", "—"))
    tcol = TIER_COLOR.get(tier, "#555")

    # ---- header band ----
    ax = fig.add_axes([0, 0.90, 1, 0.10]); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.02, 0.05), 0.96, 0.9, boxstyle="round,pad=0.01",
                                fc=tcol, ec="none", transform=ax.transAxes))
    ax.text(0.04, 0.62, f"ENFORCEMENT BRIEFING  ·  Priority #{int(r['rank'])}",
            color="white", fontsize=13, weight="bold", transform=ax.transAxes)
    ax.text(0.04, 0.22, str(r["junction_name"]), color="white", fontsize=17,
            weight="bold", transform=ax.transAxes)
    ax.text(0.98, 0.5, f"{tier}\nCIS {r['CIS']:.0f}/100", color="white", fontsize=13,
            weight="bold", ha="right", va="center", transform=ax.transAxes)

    # ---- key facts (left) ----
    axl = fig.add_axes([0.04, 0.50, 0.46, 0.37]); axl.axis("off")
    lines = [
        ("Police station", str(r["police_station"])),
        ("Demand generator", ctx),
        ("Total violations", f"{int(r['n_tickets']):,} in study period"),
        ("Mean severity", f"{r.get('sev_mean', 0):.2f} (flow-blocking)"),
        ("Top violation", str(r.get("top_violation", "—"))),
        ("Top vehicle", str(r.get("top_vehicle", "—"))),
        ("At a junction", f"{r.get('junction_share',0)*100:.0f}% of tickets"),
    ]
    y = 0.98
    for k, v in lines:
        axl.text(0.0, y, f"{k}", fontsize=9.5, color="#666", transform=axl.transAxes)
        axl.text(0.0, y - 0.035, f"{v}", fontsize=11.5, weight="bold", color="#111",
                 transform=axl.transAxes)
        y -= 0.105

    # ---- locator map (right) ----
    axm = fig.add_axes([0.54, 0.62, 0.42, 0.25])
    axm.scatter(allpts["lon"], allpts["lat"], s=2, c="#ccc", alpha=0.5)
    axm.scatter([r["lon"]], [r["lat"]], s=180, marker="*", c=tcol,
                edgecolor="black", zorder=5)
    axm.set_title("Location (red = this hotspot)", fontsize=9)
    axm.set_xticks([]); axm.set_yticks([])
    for s in axm.spines.values(): s.set_edgecolor("#ddd")

    # ---- hourly profile (right, below map) ----
    axh = fig.add_axes([0.54, 0.50, 0.42, 0.09])
    hours = range(24); vals = [zser.get(h, 0) for h in hours]
    peakh = int(r.get("peak_hour", np.argmax(vals)))
    axh.bar(hours, vals, color=["#f03b20" if h == peakh else "#bbb" for h in hours])
    axh.set_title("When (hour of day)", fontsize=9)
    axh.set_xticks([0, 6, 12, 18, 23]); axh.set_yticks([])
    axh.tick_params(labelsize=7)

    # ---- timing band ----
    axt = fig.add_axes([0.04, 0.39, 0.92, 0.08]); axt.axis("off")
    axt.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0.0",
                                 fc="#f4f6f8", ec="#dde3e9", transform=axt.transAxes))
    win = f"{peakh:02d}:00-{(peakh+3)%24:02d}:00"
    axt.text(0.02, 0.62, "DEPLOY WHEN", fontsize=9.5, color="#666", transform=axt.transAxes)
    axt.text(0.02, 0.2, f"{win}  ·  busiest {r.get('peak_dow','—')}  ·  "
             f"{shift_for_hour(peakh)}", fontsize=12.5, weight="bold",
             color="#111", transform=axt.transAxes)

    # ---- recommended action ----
    axa = fig.add_axes([0.04, 0.10, 0.92, 0.26]); axa.axis("off")
    axa.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0.0",
                                 fc="#fff6f4", ec=tcol, lw=1.5, transform=axa.transAxes))
    axa.text(0.02, 0.9, "RECOMMENDED ACTION", fontsize=11, weight="bold",
             color=tcol, transform=axa.transAxes)
    if disp_flag:
        axa.text(0.98, 0.9, "⚠ DISPLACEMENT RISK", fontsize=10, weight="bold",
                 color="#b10026", ha="right", transform=axa.transAxes)
    yy = 0.74
    for a in recommend(r, ctx, disp_flag, fcast):
        axa.text(0.03, yy, "•  " + a, fontsize=10.5, color="#222", wrap=True,
                 transform=axa.transAxes, va="top")
        yy -= 0.14

    # ---- footer ----
    fig.text(0.04, 0.05, "Gridlock — Parking Congestion Intelligence", fontsize=8,
             color="#888")
    fig.text(0.96, 0.05, f"Generated {date.today().isoformat()}", fontsize=8,
             color="#888", ha="right")
    pdf.savefig(fig); plt.close(fig)


def cover(pdf, hot, n):
    fig = plt.figure(figsize=(8.27, 11.69)); fig.patch.set_facecolor("white")
    fig.text(0.5, 0.78, "GRIDLOCK", fontsize=40, weight="bold", ha="center", color="#b10026")
    fig.text(0.5, 0.73, "Parking Congestion Intelligence", fontsize=16, ha="center", color="#333")
    fig.text(0.5, 0.69, "Enforcement Briefing Pack", fontsize=14, ha="center", color="#666")
    viol = int(hot["n_tickets"].sum()) if len(hot) else 0
    kpis = [
        f"{n} priority hotspots briefed",
        f"{viol:,} illegal-parking violations analysed",
        f"{len(hot):,} enforcement zones",
        f"Generated {date.today().isoformat()}",
    ]
    y = 0.55
    for k in kpis:
        fig.text(0.5, y, k, fontsize=12, ha="center", color="#222"); y -= 0.045
    fig.text(0.5, 0.18, "One page per hotspot · where, why, when, forecast,\n"
             "displacement risk, and recommended action.", fontsize=10.5,
             ha="center", color="#777")
    pdf.savefig(fig); plt.close(fig)


def main():
    df = pd.read_parquet(LABELLED)
    z = df[df["zone"] != "__noise__"]
    hot = pd.read_csv(OUT_DIR / "hotspots.csv")
    ctx = opt("zone_context.csv")
    disp = opt("displacement_report.csv")
    fc = opt("forecast_hotspots.csv")

    # join everything onto the hotspot ranking
    m = hot.copy()
    ctx_map = dict(zip(ctx["zone"], ctx["context"])) if len(ctx) else {}
    fc_map = dict(zip(fc["zone"], fc["pred_week"])) if len(fc) else {}
    disp_wm = set(disp.loc[disp["verdict"].astype(str).str.startswith("Displacement"),
                           "zone"]) if len(disp) else set()

    allpts = z.groupby("zone").agg(lat=("latitude", "mean"), lon=("longitude", "mean")).reset_index()
    hour_by_zone = z.groupby(["zone", "hour"]).size()

    out = OUT_DIR / "briefing_pack.pdf"
    with PdfPages(out) as pdf:
        cover(pdf, hot, min(TOP_N, len(m)))
        for _, r in m.head(TOP_N).iterrows():
            zser = hour_by_zone.loc[r["zone"]] if r["zone"] in hour_by_zone.index.get_level_values(0) else pd.Series(dtype=int)
            page(pdf, r, allpts, zser,
                 ctx_map.get(r["zone"], "Mixed / Other"),
                 r["zone"] in disp_wm, fc_map.get(r["zone"]))
    print(f"Wrote {out}  ({min(TOP_N, len(m))} zone briefings + cover)")


if __name__ == "__main__":
    main()
