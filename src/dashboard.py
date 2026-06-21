"""
dashboard.py  —  Step 6: a single self-contained executive dashboard
(outputs/index.html) that a traffic-ops chief can open with no tooling:
KPIs, the top enforcement-priority table, the demand charts, and a link to the
interactive map. Charts are embedded as base64 so the file is fully portable.
"""
import sys, base64
from pathlib import Path
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR, CLEAN_PARQUET, GRID_SIZE_M, CIS_WEIGHTS

HOTSPOTS_CSV = OUT_DIR / "hotspots.csv"
SCHED_CSV = OUT_DIR / "patrol_schedule.csv"


def b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def opt_csv(path):
    return pd.read_csv(path) if Path(path).exists() else pd.DataFrame()


def main():
    df = pd.read_parquet(CLEAN_PARQUET)
    hot = pd.read_csv(HOTSPOTS_CSV)
    sched = pd.read_csv(SCHED_CSV)
    fc = opt_csv(OUT_DIR / "forecast_hotspots.csv")
    impact = opt_csv(OUT_DIR / "impact_report.csv")
    disp = opt_csv(OUT_DIR / "displacement_report.csv")
    ctx = opt_csv(OUT_DIR / "zone_context.csv")
    plan = opt_csv(OUT_DIR / "deployment_plan.csv")
    events = opt_csv(OUT_DIR / "events.csv")
    ai = opt_csv(OUT_DIR / "ai_event_forecast.csv")

    n_viol = len(df)
    n_zones = len(hot)
    n_crit = (hot["tier"] == "Critical").sum()
    n_high = (hot["tier"] == "High").sum()
    peak_hour = int(df.groupby("hour").size().idxmax())
    junc_share = df["at_junction"].mean() * 100
    days = (df["ts_ist"].max() - df["ts_ist"].min()).days
    # concentration: share of all tickets sitting in the top 5% of zones
    top5 = hot.head(max(1, int(0.05 * n_zones)))["n_tickets"].sum()
    conc = top5 / hot["n_tickets"].sum() * 100

    def kpi(v, label, sub=""):
        return (f"<div class='kpi'><div class='kv'>{v}</div>"
                f"<div class='kl'>{label}</div><div class='ks'>{sub}</div></div>")

    kpis = "".join([
        kpi(f"{n_viol:,}", "Parking violations", f"over {days} days"),
        kpi(f"{n_zones:,}", "Enforcement zones", f"{GRID_SIZE_M} m grid"),
        kpi(f"{n_crit}", "Critical hotspots", "CIS &gt; 65"),
        kpi(f"{n_high}", "High hotspots", "CIS 45-65"),
        kpi(f"{peak_hour:02d}:00", "Citywide peak hour", "IST"),
        kpi(f"{conc:.0f}%", "Tickets in top 5% zones", "spatial concentration"),
    ])

    # top hotspot table
    th = ("<tr><th>#</th><th>CIS</th><th>Tier</th><th>Junction / Area</th>"
          "<th>Police station</th><th>Tickets</th><th>Top violation</th>"
          "<th>Peak</th></tr>")
    rows = ""
    tier_cls = {"Critical": "tc", "High": "th2", "Medium": "tm", "Low": "tl"}
    for _, r in hot.head(15).iterrows():
        rows += (f"<tr><td>{int(r['rank'])}</td>"
                 f"<td><b>{r['CIS']:.1f}</b></td>"
                 f"<td class='{tier_cls.get(r['tier'],'tl')}'>{r['tier']}</td>"
                 f"<td>{r['junction_name']}</td><td>{r['police_station']}</td>"
                 f"<td>{int(r['n_tickets']):,}</td><td>{r['top_violation']}</td>"
                 f"<td>{int(r['peak_hour']):02d}:00</td></tr>")
    hot_table = f"<table>{th}{rows}</table>"

    # patrol schedule table
    ths = ("<tr><th>#</th><th>Junction / Area</th><th>Patrol window</th>"
           "<th>Busiest day</th><th>Shift</th><th>% load in window</th></tr>")
    srows = ""
    for _, r in sched.head(12).iterrows():
        srows += (f"<tr><td>{int(r['rank'])}</td><td>{r['junction_name']}</td>"
                  f"<td><b>{r['patrol_window']}</b></td><td>{r['busiest_weekday']}</td>"
                  f"<td>{r['recommended_shift']}</td><td>{r['window_share_%']}%</td></tr>")
    sched_table = f"<table>{ths}{srows}</table>"

    # ---- forecast section (optional) ------------------------------------
    fc_section = ""
    if len(fc):
        frows = ""
        for _, r in fc.head(10).iterrows():
            frows += (f"<tr><td>{int(r['rank'])}</td><td><b>{r['pred_week']:.0f}</b></td>"
                      f"<td>{r['junction_name']}</td><td>{r['police_station']}</td></tr>")
        acc_b64 = b64(OUT_DIR / "forecast_accuracy.png")
        fc_section = f"""
 <h2>🔮 Predicted hotspots — next 7 days</h2>
 <div class="grid2">
   <table><tr><th>#</th><th>Pred. tickets</th><th>Junction / Area</th>
     <th>Police station</th></tr>{frows}</table>
   <img src="data:image/png;base64,{acc_b64}">
 </div>
 <div class="note">A gradient-boosted model forecasts each zone's ticket load 7
   days ahead (features use only history ≥7 days old — no leakage). It beats a
   same-weekday-last-week baseline and predicts <b>which</b> zones will be hot
   with per-zone weekly correlation r≈0.85 — the signal enforcement planning
   needs.</div>"""

    # ---- impact section (optional) --------------------------------------
    impact_section = ""
    if len(impact):
        vc = impact["verdict"].value_counts()
        best = impact.sort_values("did_change_%").head(8)
        irows = ""
        for _, r in best.iterrows():
            irows += (f"<tr><td>{r['junction_name']}</td><td>{r['police_station']}</td>"
                      f"<td>{r['intervention_date']}</td><td>{r['before_mean']:.1f}</td>"
                      f"<td>{r['after_mean']:.1f}</td>"
                      f"<td class='tc'>{r['did_change_%']:+.0f}%</td>"
                      f"<td>{r['p_value']}</td></tr>")
        demo_b64 = b64(OUT_DIR / "impact_demo.png")
        impact_section = f"""
 <h2>📉 Before / after enforcement impact (Difference-in-Differences)</h2>
 <div class="kpis" style="grid-template-columns:repeat(3,1fr)">
   {kpi(int(vc.get('Strong reduction',0)), 'Strong reductions', 'DiD ≤ -25%, significant')}
   {kpi(int(vc.get('Reduction',0)), 'Reductions', 'DiD ≤ -10%')}
   {kpi(int(vc.get('Worsened / rebound',0)), 'Rebounds', 'DiD ≥ +10% (watch-list)')}
 </div>
 <table><tr><th>Junction / Area</th><th>Police station</th><th>Intervention</th>
   <th>Before/day</th><th>After/day</th><th>DiD change</th><th>p</th></tr>{irows}</table>
 <img src="data:image/png;base64,{demo_b64}">
 <div class="note">DiD change subtracts the citywide trend, so a zone only counts
   as improved if illegal parking fell <b>more than the city did</b>. Interventions
   here are auto-detected level-shifts (a screen); feed real crackdown dates into
   <code>measure_impact()</code> for audit-grade numbers.</div>"""

    # ---- displacement section (optional) --------------------------------
    disp_section = ""
    if len(disp):
        vc = disp["verdict"].value_counts()
        wm = disp[disp["verdict"].str.startswith("Displacement")] \
            .sort_values("displacement_%", ascending=False)
        drows = ""
        for _, r in wm.head(6).iterrows():
            drows += (f"<tr><td>{r['junction_name']}</td><td>{r['police_station']}</td>"
                      f"<td>-{r['treated_drop']:.0f}/day</td>"
                      f"<td>+{r['neigh_gain']:.0f}/day</td>"
                      f"<td class='tc'>{r['displacement_%']:.0f}%</td></tr>")
        if not drows:
            drows = "<tr><td colspan='5'>No whack-a-mole among top zones — benefit held.</td></tr>"
        ddemo_b64 = b64(OUT_DIR / "displacement_demo.png")
        disp_section = f"""
 <h2>🔀 Displacement check — did enforcement solve it or just move it?</h2>
 <div class="kpis" style="grid-template-columns:repeat(3,1fr)">
   {kpi(int(vc.get('Genuine reduction',0)), 'Genuine reductions', 'benefit, neighbours held/fell')}
   {kpi(int(vc.get('Partial displacement',0))+int(vc.get('Displacement (whack-a-mole)',0)), 'Displacement cases', 'cars hopped next door')}
   {kpi(int(vc.get('Inconclusive (no drop)',0)), 'Inconclusive', 'no clear treated drop')}
 </div>
 <table><tr><th>Junction / Area</th><th>Police station</th><th>Treated change</th>
   <th>Neighbour change</th><th>Displacement</th></tr>{drows}</table>
 <img src="data:image/png;base64,{ddemo_b64}">
 <div class="note">For each crackdown we compare the treated zone's drop with the
   DiD-adjusted change in zones within 400 m. <b>Displacement &gt; 40%</b> = cars
   moved next door → treat the <b>corridor</b>, not the single block. Genuine
   reductions show benefit even spilling to neighbours.</div>"""

    # (traffic-flow cost section removed)
    cost_section = ""

    # ---- deployment / ROI section (optional) ----------------------------
    deploy_section = ""
    if len(plan):
        K = min(25, len(plan))
        locK = plan["cum_located_%"].iloc[K - 1]
        capK = plan["cum_captured_%"].iloc[K - 1]
        prows = ""
        for _, r in plan.head(12).iterrows():
            corr = " 🔁" if r.get("corridor", False) else ""
            prows += (f"<tr><td>{int(r['priority'])}</td><td>{r['junction_name']}{corr}</td>"
                      f"<td>{r['police_station']}</td><td><b>{r['window']}</b></td>"
                      f"<td>{r['busiest_dow']}</td><td>{int(r['violations']):,}</td>"
                      f"<td>{r['cum_located_%']:.0f}%</td></tr>")
        ob = b64(OUT_DIR / "optimize_coverage.png")
        deploy_section = f"""
 <h2>🎯 Optimised enforcement deployment (ROI)</h2>
 <div class="kpis" style="grid-template-columns:repeat(3,1fr)">
   {kpi(f"{K}", "Patrol-shifts/day", "to allocate")}
   {kpi(f"{locK:.0f}%", "Of all violations", f"sit in these {K} points")}
   {kpi(f"~{capK:.0f}%", "Realistically captured", "after capture-rate")}
 </div>
 <table><tr><th>#</th><th>Enforcement point</th><th>Police station</th>
   <th>Window</th><th>Busiest day</th><th>Violations</th><th>Cum. %</th></tr>{prows}</table>
 <img src="data:image/png;base64,{ob}">
 <div class="note">Cells are merged into distinct deployable points, ranked by the
   violations a patrol can capture in the zone's peak 3-hour window. 🔁 = whack-a-mole
   point — deploy as a <b>corridor</b>. The curve is the targeting argument: a
   handful of points dominate the violations.</div>"""

    # ---- demand-generator context section (optional) --------------------
    ctx_section = ""
    if len(ctx) and "context" in ctx.columns:
        by = (ctx.groupby("context")
                 .agg(zones=("zone", "size"), tickets=("n_tickets", "sum"))
                 .sort_values("tickets", ascending=False))
        total_t = by["tickets"].sum()
        xrows = ""
        for cat, r in by.head(8).iterrows():
            xrows += (f"<tr><td>{cat}</td><td>{int(r['zones'])}</td>"
                      f"<td>{int(r['tickets']):,}</td>"
                      f"<td>{r['tickets']/total_t*100:.1f}%</td></tr>")
        xb = b64(OUT_DIR / "context_summary.png")
        ctx_section = f"""
 <h2>📍 Why the hotspots exist — demand-generator attribution</h2>
 <table><tr><th>Demand generator</th><th>Zones</th><th>Violations</th>
   <th>Share</th></tr>{xrows}</table>
 <img src="data:image/png;base64,{xb}">
 <div class="note">Each hotspot is tagged to the land use pulling the parking
   (metro/market/mall/hospital/…) from its address + junction text — the
   "commercial areas, metro stations, events" the brief calls out. This tells you
   <b>what to fix</b> (e.g. sanctioned parking near a market) not just where.</div>"""

    # ---- event / anomaly section (optional) -----------------------------
    event_section = ""
    if len(events):
        erows = ""
        for _, r in events.head(10).iterrows():
            erows += (f"<tr><td>{r['date']}</td><td>{r['dow']}</td>"
                      f"<td>{r['junction_name']}</td><td>{r['police_station']}</td>"
                      f"<td>{int(r['count'])}</td><td>{r['normal_day']}</td>"
                      f"<td class='tc'>{r['z_score']:.0f}σ</td></tr>")
        eb = b64(OUT_DIR / "events_timeline.png")
        event_section = f"""
 <h2>📅 Event / surge detection</h2>
 <table><tr><th>Date</th><th>Day</th><th>Junction / Area</th><th>Police station</th>
   <th>Tickets</th><th>Normal</th><th>Spike</th></tr>{erows}</table>
 <img src="data:image/png;base64,{eb}">
 <div class="note">Robust z-score (median/MAD) flags days a zone's load suddenly
   surges — festivals, sales, matches, rallies (e.g. 31 Dec). Lets enforcement
   pre-position instead of reacting. <i>Caveat: surges partly reflect enforcement
   drives, not only true demand.</i></div>"""

    # ---- AI event-aware forecast section (optional) ---------------------
    ai_section = ""
    if len(ai):
        mode = ai["source"].iloc[0] if "source" in ai.columns else "offline"
        mode_txt = ("🟢 LIVE — events fetched via web search and reasoned by Claude"
                    if mode == "live" else
                    "🟡 OFFLINE sample — set <code>ANTHROPIC_API_KEY</code> and rerun "
                    "<code>python src/ai_agent.py</code> for live events")
        dot = {"Severe": "tc", "High": "th2", "Elevated": "tm"}
        arows = ""
        for _, r in ai.head(12).iterrows():
            arows += (f"<tr><td>{r['date']}</td>"
                      f"<td class='{dot.get(r['risk_level'],'tl')}'>{r['risk_level']}</td>"
                      f"<td>{r['junction_name']}</td><td>{r['event_name']}</td>"
                      f"<td>{r['reasoning']}</td></tr>")
        ai_section = f"""
 <h2>🤖 AI event-aware forecast — what's happening this week</h2>
 <div class="note" style="margin-bottom:10px">{mode_txt}. An internet-connected
   Claude agent finds real upcoming demand drivers (festivals, matches, sales,
   rallies) and reasons about which hotspots they'll overload — turning the
   statistical forecast into an explained, day-ahead one police can prepare for.</div>
 <table><tr><th>Date</th><th>Risk</th><th>Hotspot</th><th>Event</th>
   <th>Why (AI reasoning)</th></tr>{arows}</table>
 <div class="note">Full reasoned brief: <code>outputs/ai_briefings.md</code>.
   This is the layer that makes the system <b>predictive of specific days</b>, not
   just historically average — "tomorrow is a festival near KR Market, pre-deploy."</div>"""

    # ---- system architecture diagram (inline SVG) -----------------------
    def node(x, y, w, t, c="#1f2c3c"):
        return (f"<rect x='{x}' y='{y}' width='{w}' height='46' rx='8' fill='{c}' "
                f"stroke='#3a4d63'/><text x='{x+w/2}' y='{y+28}' fill='#e7edf3' "
                f"font-size='13' text-anchor='middle'>{t}</text>")
    def arrow(x1, x2, y):
        return (f"<line x1='{x1}' y1='{y}' x2='{x2}' y2='{y}' stroke='#f03b20' "
                f"stroke-width='2' marker-end='url(#a)'/>")
    arch_svg = f"""
 <h2>🧭 System architecture</h2>
 <svg viewBox="0 0 1140 250" style="width:100%;background:#0c131c;border:1px solid #243245;border-radius:10px">
   <defs><marker id='a' markerWidth='9' markerHeight='9' refX='7' refY='3'
     orient='auto'><path d='M0,0 L7,3 L0,6 Z' fill='#f03b20'/></marker></defs>
   <text x='20' y='28' fill='#9fb0c0' font-size='13'>RAW DATA</text>
   {node(20,40,150,'298k police tickets')}
   {arrow(170,210,63)}
   <text x='230' y='28' fill='#9fb0c0' font-size='13'>PIPELINE</text>
   {node(210,40,160,'clean + features')}
   {arrow(370,410,63)}
   {node(410,40,160,'150 m grid zoning')}
   {arrow(570,610,63)}
   <text x='630' y='28' fill='#9fb0c0' font-size='13'>INTELLIGENCE</text>
   {node(610,40,150,'CIS score',c='#5a1d22')}
   {node(610,110,150,'demand context',c='#5a1d22')}
   {node(610,180,150,'severity weighting',c='#5a1d22')}
   {node(800,40,150,'7-day forecast',c='#5a1d22')}
   {node(800,110,150,'AI event agent 🤖',c='#3a2a5a')}
   {node(800,180,150,'DiD + displacement',c='#5a1d22')}
   {arrow(950,990,63)}{arrow(950,990,133)}{arrow(950,990,203)}
   <text x='1000' y='28' fill='#9fb0c0' font-size='13'>ACTION</text>
   {node(990,40,140,'patrol optimiser',c='#1d4023')}
   {node(990,110,140,'live command centre 🚦',c='#1d4023')}
   {node(990,180,140,'app · API · briefings',c='#1d4023')}
 </svg>
 <div class="note">Detect → score → explain → forecast → deploy → measure
   impact → check displacement → re-target. A closed enforcement loop, not a
   one-off report.</div>"""

    wtxt = " · ".join(f"{k} {int(v*100)}%" for k, v in CIS_WEIGHTS.items())
    heat_b64 = b64(OUT_DIR / "temporal_hour_dow.png")
    mix_b64 = b64(OUT_DIR / "violation_mix.png")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Gridlock · Parking Congestion Intelligence</title>
<style>
 body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;
      background:#0f1620;color:#e7edf3}}
 .wrap{{max-width:1180px;margin:0 auto;padding:28px}}
 h1{{margin:0;font-size:26px}} h1 span{{color:#f03b20}}
 .sub{{color:#9fb0c0;margin:4px 0 22px}}
 .kpis{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:26px}}
 .kpi{{background:#18222f;border:1px solid #243245;border-radius:10px;padding:14px}}
 .kv{{font-size:24px;font-weight:700;color:#fff}} .kl{{font-size:12px;margin-top:3px}}
 .ks{{font-size:11px;color:#7e90a2}}
 h2{{font-size:17px;margin:26px 0 10px;border-left:4px solid #f03b20;padding-left:9px}}
 table{{width:100%;border-collapse:collapse;background:#18222f;border-radius:8px;
        overflow:hidden;font-size:12.5px}}
 th,td{{padding:7px 9px;text-align:left;border-bottom:1px solid #243245}}
 th{{background:#1f2c3c;color:#bcd}} tr:hover td{{background:#1d2937}}
 .tc{{color:#ff5a5a;font-weight:700}} .th2{{color:#ffa24c;font-weight:700}}
 .tm{{color:#ffd27f}} .tl{{color:#9ecae1}}
 img{{width:100%;border-radius:8px;border:1px solid #243245;margin-top:8px}}
 a.map{{display:inline-block;background:#f03b20;color:#fff;text-decoration:none;
        padding:11px 18px;border-radius:8px;font-weight:600;margin-top:6px}}
 .note{{color:#8aa;font-size:12px;background:#141d28;border:1px solid #243245;
        border-radius:8px;padding:11px 13px;margin-top:10px}}
 .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
 @media(max-width:820px){{.kpis{{grid-template-columns:repeat(2,1fr)}}.grid2{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
 <h1>Grid<span>lock</span> — Parking Congestion Intelligence</h1>
 <div class="sub">AI-driven detection of illegal-parking hotspots and their impact
   on traffic flow · Bengaluru Traffic Police data</div>
 <div class="kpis">{kpis}</div>

 <a class="map" href="portal.html">🔐 Open role-gated Control Portal (admin / viewer) →</a>
 <a class="map" href="congestion_command.html" style="background:#1f2c3c">🚦 Live Command Centre</a>
 <a class="map" href="parking_congestion_map.html" style="background:#1f2c3c">🗺️ Congestion heatmap</a>
 <a class="map" href="briefing_pack.pdf" style="background:#1f2c3c">📄 Enforcement briefing pack (PDF)</a>
 <a class="map" href="daily_digest.md" style="background:#1f2c3c">🗞️ Daily ops digest</a>
 <a class="map" href="ingest_console.html" style="background:#1f2c3c">📥 Data ingestion &amp; retraining</a>
 <div style="color:#7e90a2;font-size:12px;margin-top:8px">Live app: <code>streamlit run app.py</code>
   &nbsp;·&nbsp; REST API: <code>uvicorn api:app</code> (docs at <code>/docs</code>)
   &nbsp;·&nbsp; Tests: <code>pytest</code></div>
 {arch_svg}
 {ai_section}
 {cost_section}

 <h2>Top 15 enforcement-priority hotspots (by Congestion Impact Score)</h2>
 {hot_table}
 <div class="note"><b>Congestion Impact Score (CIS)</b> = weighted blend of
   {wtxt}. Each component is normalised 0-1 across all zones, then scaled to
   0-100. Rejected tickets are down-weighted to discount false positives.</div>
 {ctx_section}
 {deploy_section}

 <h2>Recommended patrol schedule (proactive, data-driven)</h2>
 {sched_table}
 <div class="note">Each window is the contiguous 3-hour block capturing the most
   violations in that zone — i.e. when to be there to catch the most offenders.</div>
 {fc_section}
 {impact_section}
 {disp_section}
 {event_section}

 <h2>When does the city choke?</h2>
 <img src="data:image/png;base64,{heat_b64}">

 <h2>What & who blocks the road?</h2>
 <img src="data:image/png;base64,{mix_b64}">

 <div class="note" style="margin-top:24px"><b>Data caveat:</b> tickets are created
   by patrols, so timing reflects enforcement effort as well as true violation
   load (note the after-2pm drop = patrols off, not roads clear). Spatial hotspots
   are robust; once deployed, the system closes this loop by directing patrols to
   under-watched high-CIS zones.</div>
</div></body></html>"""

    out = OUT_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
