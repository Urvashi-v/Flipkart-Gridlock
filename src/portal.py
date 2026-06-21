"""
portal.py  —  generates the web front-end as THREE files:
  * portal.html     — the LOGIN PAGE ONLY. On sign-in (or "continue as viewer")
                      it opens dashboard.html.
  * dashboard.html  — the role-adaptive app (dark fintech style: left sidebar,
                      top bar w/ search + avatar, mint-green bar-chart widgets).
                      Admin sees the Data-Ingestion section; viewer does not.
                      If you open it without logging in, it bounces to portal.html.
  * index.html      — a tiny redirect to portal.html, so the site root = login
                      (no more competing interfaces).

Auth is enforced by the API; analytics are embedded so viewing works offline.
A sidebar officer chatbot answers quantitatively in plain language.
"""
import sys, base64, json, math
from pathlib import Path
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR, CLEAN_PARQUET, GRID_SIZE_M
from src import chat as chatmod

# severity / traffic-state palette
C_CRIT, C_HIGH, C_MED, C_LOW = "#ff5d6c", "#ff9f45", "#ffd166", "#4ee3b8"
MINT, PURPLE = "#4ee3b8", "#a78bfa"


def b64img(name):
    p = OUT_DIR / name
    return (f'<img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}">'
            if p.exists() else "")


def opt(name):
    p = OUT_DIR / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


# ---------------------------------------------------------------- widgets (SVG/HTML)
def _esc(s):
    return str(s).replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def barchart(vals, color=MINT, h=120, w=320, labels=None):
    """Bar chart where every bar carries a hover tooltip (data-t) that quantifies
    what it depicts. labels[i] is the bar's name (e.g. a junction or hour)."""
    if not vals:
        return ""
    mx = max(vals) or 1
    n = len(vals); bw = w / n
    bars = ""
    for i, v in enumerate(vals):
        bh = max(2, (v / mx) * (h - 14))
        lab = _esc(labels[i]) if labels and i < len(labels) else f"#{i+1}"
        tip = f"{lab} · {v:,} violations"
        # full-height transparent hit-area so the thin bar is easy to hover
        bars += (f'<rect class="hit" data-t="{tip}" x="{i*bw:.1f}" y="0" '
                 f'width="{bw:.1f}" height="{h}" fill="transparent"/>'
                 f'<rect class="bar" x="{i*bw+bw*0.18:.1f}" y="{h-bh:.1f}" width="{bw*0.64:.1f}" '
                 f'height="{bh:.1f}" rx="2.5" fill="{color}"/>')
    return f'<svg viewBox="0 0 {w} {h}" class="barc">{bars}</svg>'


def spark(vals, color=MINT, w=120, h=34):
    if not vals or len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals); rng = (mx - mn) or 1
    pts = [(i / (len(vals) - 1) * w, h - 3 - (v - mn) / rng * (h - 6)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return (f'<svg viewBox="0 0 {w} {h}" class="spark" preserveAspectRatio="none">'
            f'<polygon points="0,{h} {line} {w},{h}" fill="{color}" opacity=".10"/>'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2"/></svg>')


def statpair(items):
    cells = "".join(f"<div class='sp-c'><div class='sp-l'>{l}</div>"
                    f"<div class='sp-v' style='color:{c}'>{v}</div></div>" for l, v, c in items)
    return f"<div class='statpair'>{cells}</div>"


def _arc(cx, cy, r, f0, f1, color, wd):
    a0, a1 = math.pi * (1 - f0), math.pi * (1 - f1)
    x0, y0 = cx + r * math.cos(a0), cy - r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy - r * math.sin(a1)
    return (f'<path d="M{x0:.1f},{y0:.1f} A{r},{r} 0 0 1 {x1:.1f},{y1:.1f}" fill="none" '
            f'stroke="{color}" stroke-width="{wd}" stroke-linecap="round"/>')


def gauge(segs, top, subt):
    cx, cy, r, wd = 110, 112, 86, 15
    tot = sum(v for _, v, _ in segs) or 1
    out = _arc(cx, cy, r, 0, 1, "#1b2433", wd)
    acc = 0
    for _, v, color in segs:
        if v > 0:
            out += _arc(cx, cy, r, acc / tot + 0.006, (acc + v) / tot - 0.006, color, wd)
        acc += v
    legend = " ".join(f"<span class='lg'><i style='background:{c}'></i>{l} {v}</span>"
                      for l, v, c in segs)
    return (f"<div class='gauge-wrap'><svg viewBox='0 0 220 128'>{out}"
            f"<text x='110' y='100' text-anchor='middle' class='g-v'>{top}</text>"
            f"<text x='110' y='119' text-anchor='middle' class='g-s'>{subt}</text></svg>"
            f"<div class='g-lg'>{legend}</div></div>")


def barlist(items, color=MINT, unit="violations"):
    if not items:
        return "<p class='muted'>No data.</p>"
    mx = max(v for _, v in items) or 1
    tot = sum(v for _, v in items) or 1
    rows = "".join(
        f"<div class='brow{' hl' if i == 0 else ''}' "
        f"data-t='{_esc(l)} · {v:,} {unit} ({v/tot*100:.1f}% of total)'>"
        f"<span class='b-l'>{l}</span>"
        f"<span class='b-trk'><span class='b-fill' style='width:{v/mx*100:.0f}%;background:{color}'></span></span>"
        f"<span class='b-v'>{v:,} <i>{v/tot*100:.1f}%</i></span></div>"
        for i, (l, v) in enumerate(items))
    return f"<div class='barlist'>{rows}</div>"


def rank_list(rows):
    if not rows:
        return "<p class='muted'>No data.</p>"
    mx = max(r["bar"] for r in rows) or 1
    out = "".join(
        f"<div class='rl-row' data-t='#{r['n']} {_esc(r['name'])} ({_esc(r['sub'])}) · {_esc(r['v'])}'>"
        f"<span class='rl-n'>{r['n']}</span>"
        f"<span class='rl-name'>{r['name']}<i>{r['sub']}</i></span>"
        f"<span class='rl-bar'><span style='width:{r['bar']/mx*100:.0f}%;background:{r.get('color',MINT)}'></span></span>"
        f"<span class='rl-v'>{r['v']}</span></div>" for r in rows)
    return f"<div class='rank-list'>{out}</div>"


def joblist(rows):
    """Latest-jobs style list: name · sub · status badge · time."""
    if not rows:
        return "<p class='muted'>None flagged.</p>"
    out = "".join(
        f"<div class='jl-row'><span class='jl-name'>{r['name']}<i>{r['sub']}</i></span>"
        f"<span class='badge {r['cls']}'>{r['status']}</span><span class='jl-t'>{r['t']}</span></div>"
        for r in rows)
    return f"<div class='joblist'>{out}</div>"


def table(df, cols, headers=None, n=15, classes=None):
    if not len(df):
        return "<p class='muted'>Not available — run the pipeline.</p>"
    cols = [c for c in cols if c in df.columns]
    headers = headers or cols
    th = "".join(f"<th>{h}</th>" for h in headers)
    rows = ""
    for _, r in df.head(n).iterrows():
        tds = ""
        for c in cols:
            v = r[c]
            cls = classes(c, v) if classes else ""
            if isinstance(v, float):
                v = f"{v:,.1f}" if abs(v) < 1000 else f"{v:,.0f}"
            tds += f"<td class='{cls}'>{v}</td>"
        rows += f"<tr>{tds}</tr>"
    return f"<table><tr>{th}</tr>{rows}</table>"


# ---------------------------------------------------------------- panes
def build_panes():
    df = pd.read_parquet(CLEAN_PARQUET) if CLEAN_PARQUET.exists() else pd.DataFrame()
    hot = opt("hotspots.csv"); plan = opt("deployment_plan.csv")
    fc = opt("forecast_hotspots.csv"); ai = opt("ai_event_forecast.csv")
    impact = opt("impact_report.csv"); disp = opt("displacement_report.csv")
    ctx = opt("zone_context.csv"); events = opt("events.csv")

    n_viol = len(df) if len(df) else (int(hot["n_tickets"].sum()) if len(hot) else 0)
    n_crit = int((hot["tier"] == "Critical").sum()) if len(hot) else 0
    n_high = int((hot["tier"] == "High").sum()) if len(hot) else 0
    n_med = int((hot["tier"] == "Medium").sum()) if len(hot) else 0
    n_low = int((hot["tier"] == "Low").sum()) if len(hot) else 0
    conc = (hot.head(max(1, int(0.05 * len(hot))))["n_tickets"].sum() /
            hot["n_tickets"].sum() * 100) if len(hot) else 0

    hours = [0] * 24
    if len(df) and "hour" in df:
        vc = df["hour"].value_counts(); hours = [int(vc.get(h, 0)) for h in range(24)]
    peak_hour = max(range(24), key=lambda h: hours[h]) if any(hours) else 0

    tier_cls = lambda c, v: ({"Critical": "tc", "High": "th", "Severe": "tc",
                              "Medium": "tm"}.get(str(v), "") if c in ("tier", "risk_level") else "")
    gen = []
    if len(ctx) and "context" in ctx.columns:
        gen = [(k, int(v)) for k, v in ctx.groupby("context")["n_tickets"].sum()
               .sort_values(ascending=False).head(7).items()]
    # data prep for charts (proper analysis + per-bar labels for hover)
    top10 = hot.head(10) if len(hot) else hot
    top_viol = [int(r["n_tickets"]) for _, r in top10.iterrows()]
    top_viol_labels = [f"#{int(r['rank'])} {r['junction_name']}" for _, r in top10.iterrows()]
    # Coverage chart: violations by CIS-tier (relates directly to the Coverage card stats)
    tier_viol = [int(hot[hot["tier"] == t]["n_tickets"].sum()) for t in ["Critical", "High", "Medium", "Low"]] if len(hot) else [0, 0, 0, 0]
    tier_viol_labels = [f"{t}-tier zones" for t in ["Critical", "High", "Medium", "Low"]]
    hour_labels = [f"{h:02d}:00" for h in range(24)]
    top_rows = [{"n": int(r["rank"]), "name": str(r["junction_name"]),
                 "sub": str(r["police_station"]), "v": f"CIS {r['CIS']:.0f}", "bar": float(r["CIS"]),
                 "color": C_CRIT if r["tier"] == "Critical" else (C_HIGH if r["tier"] == "High" else MINT)}
                for _, r in hot.head(6).iterrows()]
    sevsegs = [("Critical", n_crit, C_CRIT), ("High", n_high, C_HIGH),
               ("Medium", n_med, C_MED), ("Low", n_low, C_LOW)]
    aijobs = []
    for _, r in ai.head(7).iterrows():
        rk = str(r["risk_level"])
        aijobs.append({"name": str(r["junction_name"]), "sub": str(r["event_name"]),
                       "status": rk, "t": str(r["date"]),
                       "cls": "bad" if rk == "Severe" else ("warn" if rk == "High" else "ok")})

    panes = {}
    # ---- OVERVIEW (proper data analysis · all bars have hover tooltips) ----
    panes["overview"] = f"""
      <div class='dgrid'>
        <div class='dmain'><div class='cgrid'>
          <div class='card'><div class='m-h'><span class='m-ic'>🔥</span><b>Hotspots</b></div>
            <div class='m-sub'>Top 10 hotspots by violation count — hover any bar to see its junction</div>
            {statpair([('Critical', n_crit, C_CRIT), ('High', n_high, C_HIGH)])}
            {barchart(top_viol, MINT, 104, labels=top_viol_labels)}</div>
          <div class='card'><div class='m-h'><span class='m-ic'>▦</span><b>Coverage</b></div>
            <div class='m-sub'>Violations by CIS tier — concentration: top-5% zones = {conc:.0f}% of all violations</div>
            {statpair([('Zones', f'{len(hot):,}', '#fff'), ('Violations', f'{n_viol:,}', MINT)])}
            {barchart(tier_viol, PURPLE, 104, labels=tier_viol_labels)}</div>
          <div class='card span2'><div class='m-h'><span class='m-ic'>⏱️</span><b>Demand by hour</b>
            <span class='pill'>peak {peak_hour:02d}:00</span></div>
            <div class='m-sub'>Violations across the 24 hours of the day — hover any bar for the exact count</div>
            {barchart(hours, MINT, 140, 720, labels=hour_labels)}
            <div class='axis'><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div></div>
          <div class='card span2'><div class='m-h'><span class='m-ic'>📍</span><b>By demand generator</b></div>
            <div class='m-sub'>What kind of land use is pulling the parking — hover any row for the share</div>
            {barlist(gen, PURPLE)}</div>
        </div></div>
        <div class='drail'>
          <div class='card'><div class='m-h'><b>Severity mix</b></div>{gauge(sevsegs, f'{len(hot):,}', 'enforcement zones')}</div>
          <div class='card'><div class='m-h'><span class='m-ic'>🤖</span><b>AI event flags this week</b></div>{joblist(aijobs)}</div>
          <div class='card'><div class='m-h'><b>Top hotspots</b><span class='pill'>by CIS</span></div>{rank_list(top_rows)}</div>
        </div>
      </div>"""

    stations = ([(k, int(v)) for k, v in hot.groupby("police_station")["n_tickets"].sum()
                 .sort_values(ascending=False).head(10).items()] if len(hot) else [])
    # filterable priority hotspots table
    station_options = sorted(hot["police_station"].dropna().unique()) if len(hot) else []
    stn_opt_html = "".join(f"<option>{_esc(s)}</option>" for s in station_options)
    hot_rows = ""
    for _, r in hot.head(80).iterrows():
        cls_t = "tc" if r["tier"] == "Critical" else ("th" if r["tier"] == "High" else ("tm" if r["tier"] == "Medium" else ""))
        hot_rows += (f"<tr data-tier='{r['tier']}' data-cis='{r['CIS']:.1f}' "
                     f"data-station='{_esc(r['police_station'])}'>"
                     f"<td>{int(r['rank'])}</td><td><b>{r['CIS']:.1f}</b></td>"
                     f"<td class='{cls_t}'>{r['tier']}</td>"
                     f"<td>{int(r['n_tickets']):,}</td>"
                     f"<td>{_esc(r['junction_name'])}</td>"
                     f"<td>{_esc(r['police_station'])}</td>"
                     f"<td>{_esc(r['top_violation'])}</td>"
                     f"<td>{int(r['peak_hour']):02d}:00</td></tr>")
    filter_bar = f"""
      <div class='filter-bar'>
        <select id='f-tier' onchange='filterHotspots()'>
          <option>All tiers</option><option>Critical</option><option>High</option>
          <option>Medium</option><option>Low</option></select>
        <select id='f-stn' onchange='filterHotspots()'>
          <option>All stations</option>{stn_opt_html}</select>
        <input id='f-q' placeholder='Search junction or violation…' oninput='filterHotspots()'>
        <label class='f-cis'>Min CIS: <input type='range' id='f-cis' min='0' max='100' value='0'
          oninput='document.getElementById("f-cis-v").textContent=this.value;filterHotspots()'>
          <span id='f-cis-v'>0</span></label>
        <span id='f-count' class='f-count'>{min(80, len(hot))} of {len(hot):,}</span>
      </div>"""
    hot_table_html = (filter_bar +
        "<div class='tblwrap'><table id='hot-tbl'><thead><tr>"
        "<th>#</th><th>CIS</th><th>Tier</th><th>Violations</th>"
        "<th>Junction / Area</th><th>Police station</th><th>Top violation</th><th>Peak</th>"
        "</tr></thead><tbody>" + hot_rows + "</tbody></table></div>")

    # tier-violation mini chart (with labels for hover)
    tier_chart = barchart(tier_viol, color=C_CRIT, h=140, w=320, labels=tier_viol_labels)
    # top violation types across all zones
    top_violations = []
    if len(hot) and "top_violation" in hot.columns:
        top_violations = [(k, int(v)) for k, v in hot.groupby("top_violation")["n_tickets"].sum()
                          .sort_values(ascending=False).head(6).items()]
    panes["hotspots"] = f"""
      <div class='card'><div class='m-h'><b>Priority hotspots — by Congestion Impact Score</b>
        <span class='pill'>filterable</span></div>
        <div class='m-sub'>Filter by tier, police station, search, or set a minimum CIS</div>
        {hot_table_html}</div>
      <div class='cols c-1-1'>
        <div class='card'><div class='m-h'><b>Busiest police stations</b></div>
          <div class='m-sub'>Top 10 stations by violation volume — hover for share</div>
          {barlist(stations, MINT)}</div>
        <div class='card'><div class='m-h'><b>Violations by CIS tier</b></div>
          <div class='m-sub'>How violations distribute across severity tiers — hover any bar</div>
          {statpair([('Critical', f'{tier_viol[0]:,}', C_CRIT), ('High', f'{tier_viol[1]:,}', C_HIGH),
                     ('Medium', f'{tier_viol[2]:,}', C_MED), ('Low', f'{tier_viol[3]:,}', C_LOW)])}
          {tier_chart}</div>
      </div>
      <div class='cols c-1-1'>
        <div class='card'><div class='m-h'><b>Top primary violations</b></div>
          <div class='m-sub'>Which violations drive the hotspots — hover any row</div>
          {barlist(top_violations, C_HIGH)}</div>
        <div class='card'><div class='m-h'><b>Violation &amp; vehicle mix</b></div>{b64img('violation_mix.png')}</div>
      </div>"""

    # ---- PARKING MAP (the Folium heatmap built by build_map.py) ----
    # iframe needs onload→resize so Leaflet recomputes its viewport and the
    # zone markers + legend + layer-control land in the right place
    panes["parking_map"] = """
      <div class='note'>Severity-weighted heat layer of illegal-parking violations, plus
        ranked enforcement-zone markers (sized by volume, coloured by CIS tier) and the
        worst junctions. Click any marker for its breakdown.
        <a href='parking_congestion_map.html' target='_blank' style='float:right;color:var(--mint)'>Open standalone ↗</a></div>
      <div class='mapwrap'>
        <iframe id='pmap-frame' src='parking_congestion_map.html' class='mapframe'
          onload="setTimeout(()=>{try{this.contentWindow.dispatchEvent(new Event('resize'));}catch(e){}},120)"></iframe>
      </div>"""

    panes["command"] = """
      <div class='note'>Districts pulse by live congestion; click one to drill into its police
        areas of attention, live Google traffic, and AI event flags.</div>
      <iframe src='congestion_command.html' class='frame'></iframe>"""

    # ---- ANALYTICS (the consolidated graph browser — was Demand Context) ----
    panes["analytics"] = f"""
      <div class='note'>One place for every standalone chart Gridlock produces. Cards on
        the left are demand-side analytics, on the right are enforcement-side analytics.</div>
      <div class='cols c-1-1'>
        <div class='card'><div class='m-h'><b>Why the hotspots exist — demand-generator attribution</b></div>
          {b64img('context_summary.png')}
          <div class='m-sub' style='margin-top:8px'>Each hotspot tagged to the land use pulling its parking.</div>
        </div>
        <div class='card'><div class='m-h'><b>Demand by hour × weekday</b></div>
          {b64img('temporal_hour_dow.png')}
          <div class='m-sub' style='margin-top:8px'>Severity-weighted illegal-parking pressure over a typical week.</div>
        </div>
      </div>
      <div class='cols c-1-1'>
        <div class='card'><div class='m-h'><b>Violation &amp; vehicle mix</b></div>
          {b64img('violation_mix.png')}
          <div class='m-sub' style='margin-top:8px'>What's being parked illegally, and what kind of offence each is.</div>
        </div>
        <div class='card'><div class='m-h'><b>Why hotspots exist (table)</b></div>{barlist(gen, PURPLE)}</div>
      </div>
      <div class='cols c-1-1'>
        <div class='card'><div class='m-h'><b>Forecast accuracy (holdout)</b></div>
          {b64img('forecast_accuracy.png')}
          <div class='m-sub' style='margin-top:8px'>Model vs actual on a held-out 21-day window — spatial signal is what matters.</div>
        </div>
        <div class='card'><div class='m-h'><b>Enforcement ROI coverage curve</b></div>
          {b64img('optimize_coverage.png')}
          <div class='m-sub' style='margin-top:8px'>How much of the citywide violations are covered as you add patrol points.</div>
        </div>
      </div>
      <div class='cols c-1-1'>
        <div class='card'><div class='m-h'><b>Clearest measured reduction (DiD)</b></div>
          {b64img('impact_demo.png')}
          <div class='m-sub' style='margin-top:8px'>A real enforcement intervention vs the citywide trend.</div>
        </div>
        <div class='card'><div class='m-h'><b>Displacement (whack-a-mole)</b></div>
          {b64img('displacement_demo.png')}
          <div class='m-sub' style='margin-top:8px'>Did the drop here just appear next door? Treat as corridor if so.</div>
        </div>
      </div>
      <div class='card'><div class='m-h'><b>Daily load with spikes flagged</b></div>
        {b64img('events_timeline.png')}
        <div class='m-sub' style='margin-top:8px'>Robust z-score flags event surge-days (festivals, sales, matches).</div>
      </div>"""

    panes["forecast"] = f"""
      <div class='cols c-1-1'>
        <div class='card'><div class='m-h'><b>Predicted hotspots — next 7 days (ML)</b></div>
        {table(fc, ['rank','pred_week','junction_name','police_station'],
               ['#','Pred. tickets','Junction / Area','Police station'], 10)}</div>
        <div class='card'><div class='m-h'><b>Forecast accuracy (holdout)</b></div>{b64img('forecast_accuracy.png')}</div>
      </div>
      <div class='card'><div class='m-h'><span class='m-ic'>🤖</span><b>AI event-aware forecast — what's happening this week</b></div>
        <div class='note'>An internet-connected Claude agent finds real events and reasons about which hotspots they'll overload, a day ahead.</div>
        {table(ai, ['date','risk_level','junction_name','event_name','reasoning'],
               ['Date','Risk','Hotspot','Event','Why (AI reasoning)'], 12, tier_cls)}</div>"""

    panes["deployment"] = f"""
      <div class='card'><div class='m-h'><b>Optimised patrol deployment (ROI)</b></div>
        <div class='note'>Distinct deployable points ranked by capturable impact — a handful dominate the violations.</div>
        {table(plan, ['priority','junction_name','police_station','window','busiest_dow','violations','cum_located_%'],
               ['#','Enforcement point','Police station','Window','Busiest day','Violations','Cum. %'], 12)}</div>
      <div class='card'><div class='m-h'><b>Enforcement ROI coverage curve</b></div>{b64img('optimize_coverage.png')}</div>"""

    panes["impact"] = f"""
      <div class='card'><div class='m-h'><b>Before / after enforcement impact (Difference-in-Differences)</b></div>
        {table(impact, ['junction_name','police_station','intervention_date','before_mean','after_mean','did_change_%','verdict'],
               ['Junction / Area','Police station','Intervention','Before/day','After/day','DiD change','Verdict'], 8, tier_cls)}</div>
      <div class='cols c-1-1'>
        <div class='card'><div class='m-h'><b>Clearest measured reduction</b></div>{b64img('impact_demo.png')}</div>
        <div class='card'><div class='m-h'><b>Displacement (whack-a-mole)</b></div>{b64img('displacement_demo.png')}</div>
      </div>
      <div class='card'><div class='m-h'><b>Displacement verdicts</b></div>
        {table(disp, ['junction_name','police_station','treated_drop','neigh_gain','displacement_%','verdict'],
               ['Junction / Area','Police station','Treated drop','Neighbour gain','Displacement %','Verdict'], 8)}</div>"""

    panes["events"] = f"""
      <div class='card'><div class='m-h'><b>Event / surge detection</b></div>
        {table(events, ['date','dow','junction_name','police_station','count','normal_day','z_score'],
               ['Date','Day','Junction / Area','Police station','Tickets','Normal','Spike σ'], 12)}</div>
      <div class='card'><div class='m-h'><b>Daily load with spikes flagged</b></div>{b64img('events_timeline.png')}</div>"""

    panes["ingest"] = """
      <div class='note'>Admin only — drag-drop a file, pin a violation on the map, or paste records,
        then retrain the whole system on base + new data. Enforced by the API: only an admin token can write.</div>
      <iframe src='ingest_console.html' class='frame tall'></iframe>"""

    return panes


GROUPS = [
    ("MAIN", [("overview", "▦", "Overview", False), ("hotspots", "🔥", "Hotspots", False),
              ("parking_map", "🗺️", "Parking Map", False),
              ("command", "🛰️", "Command Centre", False), ("forecast", "📈", "Forecast & AI", False)]),
    ("ENFORCEMENT", [("deployment", "🎯", "Deployment", False), ("impact", "📉", "Impact", False),
                     ("events", "📅", "Events", False)]),
    ("INSIGHT", [("analytics", "📊", "Analytics", False)]),
    ("DATA", [("ingest", "📥", "Data Ingestion", True)]),
]
SUBTITLE = {
    "overview": "Citywide snapshot of illegal-parking hotspots and enforcement.",
    "hotspots": "The highest-priority zones by Congestion Impact Score — filterable, with deeper analytics.",
    "parking_map": "Severity-weighted heatmap of every detected violation with ranked enforcement zones.",
    "command": "Districts pulse by live congestion — click one to drill into its areas of attention.",
    "forecast": "Next-week predicted hotspots, plus the AI agent's event-aware risk for the days ahead.",
    "deployment": "Optimised patrol roster — where and when to send a fixed number of patrol-shifts.",
    "impact": "Did crackdowns work? Before/after (DiD) and the whack-a-mole displacement check.",
    "events": "Festival / sale / rally surges and detected anomaly spike-days.",
    "analytics": "Every standalone chart in one place — demand-side and enforcement-side.",
    "ingest": "Admin only — dump fresh data and retrain the whole system on base + new records.",
}

# shared design system
CSS = r"""
 :root{--bg:#080b11;--bg2:#0b0f17;--card:#10151f;--line:#1c2531;--tx:#eef2f7;--mut:#7d8a9c;
   --mint:#4ee3b8;--purple:#a78bfa;--red:#ff5d6c;--amber:#ff9f45}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--tx);
   font:14px/1.5 'Inter',-apple-system,Segoe UI,Roboto,sans-serif}
 a{text-decoration:none;color:inherit} .muted{color:var(--mut)}
 .badge{font-size:10.5px;font-weight:700;border-radius:20px;padding:3px 9px;white-space:nowrap}
 .badge.ok{background:rgba(78,227,184,.15);color:#7fe6c2}
 .badge.bad{background:rgba(255,93,108,.15);color:#ff9aa3}
 .badge.warn{background:rgba(255,159,69,.15);color:#ffc08a}
"""


def login_html():
    return r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gridlock · Sign in</title><style>""" + CSS + r"""
 .wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;
   background:radial-gradient(1100px 560px at 50% -8%,#10283f,#05080d)}
 .lbox{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:34px;width:380px;
   box-shadow:0 24px 60px #0009}
 .brand{display:flex;align-items:center;gap:11px;font-size:24px;font-weight:800;margin-bottom:3px}
 .brand .mk{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;font-size:18px;
   background:linear-gradient(135deg,var(--mint),#2bd4cf);color:#06231b}
 .brand b{color:var(--mint)}
 .sub{color:var(--mut);font-size:13px;margin-bottom:20px}
 label{font-size:12px;color:var(--mut);display:block;margin:11px 0 5px}
 input{width:100%;background:#0a0f17;border:1px solid var(--line);color:var(--tx);border-radius:10px;padding:12px}
 .go{width:100%;background:var(--mint);color:#06231b;border:none;border-radius:11px;padding:13px;font-weight:800;
   margin-top:18px;cursor:pointer;font-size:15px}
 .ghost{width:100%;background:#0e1521;border:1px solid var(--line);color:var(--tx);border-radius:11px;padding:11px;
   margin-top:10px;cursor:pointer;font-weight:600;font-size:13px}
 .hint{display:flex;gap:8px;margin-top:16px}
 .hint b{flex:1;background:#0a0f17;border:1px solid var(--line);border-radius:10px;padding:9px;font-size:11px;
   color:var(--mut);cursor:pointer;text-align:center} .hint b:hover{border-color:var(--mint)}
 #err{color:#ff8a93;font-size:12.5px;margin-top:10px;min-height:16px}
 code{background:#0a0f17;border:1px solid var(--line);border-radius:5px;padding:1px 5px;font-size:11px}
</style></head><body><div class="wrap"><div class="lbox">
  <div class="brand"><span class="mk">🚦</span>Grid<b>lock</b></div>
  <div class="sub">Parking Congestion Intelligence — sign in to your dashboard</div>
  <label>Role / username</label><input id="u" value="viewer" autocomplete="username">
  <label>Password</label><input id="p" type="password" autocomplete="current-password">
  <button class="go" onclick="doLogin()">Sign in</button>
  <button class="ghost" onclick="guest()">👁️ Continue as viewer — no login</button>
  <div id="err"></div>
  <div class="hint">
    <b onclick="fill('admin','admin@gridlock')">admin demo<br>full + ingestion</b>
    <b onclick="fill('viewer','viewer@gridlock')">viewer demo<br>analytics only</b>
  </div>
</div></div>
<script>
const API="http://localhost:8000";
function fill(u,p){u_.value=u;p_.value=p;} const u_=document.getElementById('u'),p_=document.getElementById('p');
function go(){ location.href='dashboard.html'; }
function guest(){ localStorage.setItem('gridlock_role','viewer'); localStorage.setItem('gridlock_ingest','0');
  localStorage.removeItem('gridlock_token'); go(); }
async function doLogin(){ const err=document.getElementById('err'); err.innerHTML='';
  try{ const r=await fetch(API+"/auth/login",{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({username:u_.value.trim(),password:p_.value})});
    if(r.status===401) throw new Error('Invalid username or password.');
    if(!r.ok) throw new Error('Login failed ('+r.status+').');
    const d=await r.json(); localStorage.setItem('gridlock_token',d.token);
    localStorage.setItem('gridlock_role',d.role); localStorage.setItem('gridlock_ingest',d.can_ingest?'1':'0'); go();
  }catch(e){ const net=(e instanceof TypeError)||/fetch/i.test(e.message||'');
    err.innerHTML = net ? "Can't reach the API. Start it: <code>uvicorn api:app</code> and open via "
      +"<code>http://localhost:8540/portal.html</code>. Or just Continue as viewer." : (e.message||'Login failed.'); }
}
u_.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();});
p_.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();});
</script></body></html>"""


def dashboard_html(panes, pages, sidebar, chat_ctx):
    return (r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gridlock · Dashboard</title><style>""" + CSS + r"""
 .side{position:fixed;left:0;top:0;bottom:0;width:238px;background:var(--bg2);border-right:1px solid var(--line);
   padding:18px 14px;overflow-y:auto;z-index:40;display:flex;flex-direction:column}
 .logo{display:flex;align-items:center;gap:10px;font-size:19px;font-weight:800;padding:4px 6px 14px}
 .logo .mk{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;font-size:16px;
   background:linear-gradient(135deg,var(--mint),#2bd4cf);color:#06231b} .logo b{color:var(--mint)}
 .ws{display:flex;align-items:center;gap:10px;background:#0e1521;border:1px solid var(--line);border-radius:12px;
   padding:10px;margin-bottom:6px} .ws .wi{width:30px;height:30px;border-radius:8px;background:#16202d;display:grid;place-items:center}
 .ws b{font-size:12.5px;display:block} .ws span{font-size:10.5px;color:var(--mut)}
 .s-grp{font-size:10px;letter-spacing:.13em;color:#56657a;margin:15px 6px 6px;font-weight:700}
 .nav{display:flex;align-items:center;gap:11px;padding:9px 11px;border-radius:10px;color:#aab6c6;font-size:13.5px;
   cursor:pointer;font-weight:500;margin-bottom:2px} .nav .s-ic{width:18px;text-align:center;opacity:.9}
 .nav:hover{background:#121a26;color:var(--tx)}
 .nav.on{background:linear-gradient(90deg,rgba(78,227,184,.16),rgba(78,227,184,.03));color:#fff;box-shadow:inset 2px 0 0 var(--mint)}
 .nav.admin.on{background:linear-gradient(90deg,rgba(167,139,250,.18),transparent);box-shadow:inset 2px 0 0 var(--purple)}
 .s-badge{margin-left:auto;font-size:9.5px;background:#2a2150;color:#c9b6ff;border-radius:10px;padding:2px 7px;font-weight:700}
 .s-foot{margin-top:auto;padding-top:14px;border-top:1px solid var(--line)}
 .s-role{font-size:11.5px;font-weight:700;padding:6px 11px;border-radius:20px;border:1px solid var(--line);display:inline-block}
 .s-role.admin{background:#2a1417;border-color:var(--red);color:#ff9aa3}
 .s-role.viewer{background:#0f2620;border-color:#1c6b50;color:#7fe6c2}
 .s-foot button{width:100%;margin-top:10px;background:#0e1521;border:1px solid var(--line);color:var(--tx);
   border-radius:9px;padding:9px;cursor:pointer;font-size:12.5px;font-weight:600}
 .content{margin-left:238px}
 .topbar{position:sticky;top:0;z-index:30;display:flex;align-items:center;gap:14px;padding:16px 26px;
   background:rgba(8,11,17,.82);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
 .topbar h1{margin:0;font-size:21px;font-weight:800;letter-spacing:-.3px}
 .topbar p{margin:2px 0 0;color:var(--mut);font-size:12.5px}
 .topbar .sp{flex:1}
 .searchpill{display:flex;align-items:center;gap:8px;background:#0c1219;border:1px solid var(--line);color:var(--mut);
   border-radius:22px;padding:9px 16px;cursor:pointer;font-size:13px;min-width:220px} .searchpill:hover{border-color:var(--mint)}
 .apistat{font-size:11.5px;color:var(--mut);white-space:nowrap}
 .ic-btn{width:36px;height:36px;border-radius:10px;background:#0c1219;border:1px solid var(--line);display:grid;place-items:center;cursor:pointer;color:var(--mut)}
 .avatar{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;font-weight:800;color:#06231b;
   background:linear-gradient(135deg,var(--mint),#2bd4cf)} .hamb{display:none}
 main{padding:22px 26px 60px;max-width:1340px}
 .pane{display:none;animation:fade .25s ease} .pane.on{display:block}
 @keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
 .dgrid{display:grid;grid-template-columns:1.85fr 1fr;gap:16px}
 .cgrid{display:grid;grid-template-columns:1fr 1fr;gap:16px} .drail{display:flex;flex-direction:column;gap:16px}
 .cols{display:grid;gap:16px;margin-top:16px} .c-2-1{grid-template-columns:1.7fr 1fr} .c-1-1{grid-template-columns:1fr 1fr}
 .span2{grid-column:1/-1}
 .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px 18px}
 .m-h{display:flex;align-items:center;gap:9px;font-size:14.5px;font-weight:700} .m-h .m-ic{font-size:15px}
 .m-h .pill{margin-left:auto;font-size:11px;color:#9fe9d2;background:rgba(78,227,184,.12);border:1px solid rgba(78,227,184,.25);border-radius:20px;padding:3px 10px;font-weight:600}
 .m-sub{color:var(--mut);font-size:12px;margin:3px 0 2px}
 .statpair{display:flex;gap:30px;margin:12px 0 10px}
 .sp-l{font-size:11px;color:var(--mut)} .sp-v{font-size:25px;font-weight:800;letter-spacing:-.5px;margin-top:2px}
 .barc{width:100%;height:auto;display:block;margin-top:4px} .spark{width:100%;height:34px;display:block}
 .barc .hit{cursor:crosshair} .barc .bar{transition:filter .15s,opacity .15s}
 .barc .hit:hover ~ .bar{} /* sibling reach not used; we do JS-driven highlight */
 .barc.bar-act .bar{opacity:.45} .barc.bar-act .bar.on{opacity:1;filter:brightness(1.18) drop-shadow(0 0 6px currentColor)}
 .brow{cursor:default;border-radius:7px;padding:2px 4px;margin:0 -4px;transition:background .15s} .brow:hover{background:#13202d}
 .rl-row{transition:background .15s;border-radius:7px;padding-left:4px;padding-right:4px}
 .rl-row:hover{background:#13202d}
 /* custom tooltip */
 #ttip{position:fixed;z-index:200;background:#0e1a26;color:#eef2f7;border:1px solid var(--line);
   border-radius:8px;padding:8px 12px;font-size:12px;font-weight:600;pointer-events:none;
   box-shadow:0 8px 24px #000a;opacity:0;transform:translate(-50%,-110%);transition:opacity .12s}
 #ttip.on{opacity:1} #ttip::after{content:"";position:absolute;left:50%;top:100%;
   border:6px solid transparent;border-top-color:#0e1a26;margin-left:-6px}
 /* filter bar */
 .filter-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 0 12px;border-bottom:1px solid var(--line);margin-bottom:10px}
 .filter-bar select,.filter-bar input{background:#0c1219;border:1px solid var(--line);color:var(--tx);border-radius:8px;padding:7px 11px;font:inherit;font-size:12.5px}
 .filter-bar select:focus,.filter-bar input:focus{outline:none;border-color:var(--mint)}
 .filter-bar #f-q{flex:1;min-width:180px} .f-cis{display:flex;align-items:center;gap:8px;color:var(--mut);font-size:12px}
 .f-cis input[type=range]{accent-color:var(--mint);width:120px}
 .f-cis #f-cis-v{color:var(--mint);font-weight:700;font-variant-numeric:tabular-nums;min-width:24px;text-align:right}
 .f-count{margin-left:auto;color:var(--mut);font-size:11.5px}
 .tblwrap{max-height:540px;overflow:auto;border:1px solid var(--line);border-radius:10px}
 .tblwrap table thead{position:sticky;top:0;background:#0e1521;z-index:1}
 .tblwrap table th{background:#0e1521}
 .axis{display:flex;justify-content:space-between;color:#566276;font-size:10px;margin-top:2px}
 .gauge-wrap{text-align:center;padding-top:2px} .gauge-wrap svg{width:100%;max-width:230px}
 .g-v{fill:#fff;font-size:25px;font-weight:800} .g-s{fill:#7d8a9c;font-size:11px}
 .g-lg{display:flex;gap:13px;justify-content:center;flex-wrap:wrap;margin-top:6px}
 .lg{font-size:11.5px;color:#aab6c6;display:flex;align-items:center;gap:5px} .lg i{width:9px;height:9px;border-radius:3px;display:inline-block}
 .barlist{display:flex;flex-direction:column;gap:9px}
 .brow{display:grid;grid-template-columns:130px 1fr auto;align-items:center;gap:10px;font-size:12.5px}
 .b-l{color:#c2cdda;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .b-trk{height:8px;background:#0c121b;border-radius:6px;overflow:hidden} .b-fill{display:block;height:100%;border-radius:6px}
 .b-v{color:var(--mut);white-space:nowrap;font-variant-numeric:tabular-nums} .b-v i{color:#5f6c80;font-style:normal;font-size:11px}
 .brow.hl .b-l{color:#fff;font-weight:600}
 .rank-list{display:flex;flex-direction:column}
 .rl-row{display:grid;grid-template-columns:22px 1fr 86px 60px;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--line)}
 .rl-row:last-child{border-bottom:none} .rl-n{color:#5f6c80;font-weight:700;font-size:12px}
 .rl-name{font-size:12.5px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .rl-name i{display:block;color:var(--mut);font-style:normal;font-size:11px;font-weight:400}
 .rl-bar{height:7px;background:#0c121b;border-radius:5px;overflow:hidden} .rl-bar span{display:block;height:100%;border-radius:5px}
 .rl-v{text-align:right;font-size:12px;font-weight:700;color:#cfe9e0}
 .joblist{display:flex;flex-direction:column} .jl-row{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--line)}
 .jl-row:last-child{border-bottom:none} .jl-name{flex:1;font-size:12.5px;font-weight:600;overflow:hidden}
 .jl-name i{display:block;color:var(--mut);font-style:normal;font-weight:400;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .jl-t{font-size:10.5px;color:#5f6c80;white-space:nowrap}
 table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:2px}
 th,td{padding:9px 11px;text-align:left;border-bottom:1px solid var(--line)}
 th{color:#7d8a9c;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em}
 tr:last-child td{border-bottom:none} table tr:hover td{background:#121a26}
 .tc{color:var(--red);font-weight:700}.th{color:var(--amber);font-weight:700}.tm{color:#ffe08a}
 img{width:100%;border-radius:10px;border:1px solid var(--line);margin-top:6px}
 .note{color:#9aa7b8;background:#0c1219;border:1px solid var(--line);border-left:3px solid var(--mint);border-radius:10px;padding:12px 14px;margin-bottom:12px;font-size:13px}
 .frame{width:100%;height:660px;border:1px solid var(--line);border-radius:14px;margin-top:4px;background:#0a0f17} .frame.tall{height:880px}
 /* parking map: give the iframe a guaranteed, generous height so Leaflet renders zones+legend correctly */
 .mapwrap{width:100%;height:calc(100vh - 200px);min-height:720px;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#0a0f17}
 .mapframe{width:100%;height:100%;border:0;display:block}
 @media(max-width:1180px){.dgrid{grid-template-columns:1fr}.cgrid{grid-template-columns:1fr}.c-2-1,.c-1-1{grid-template-columns:1fr}}
 @media(max-width:860px){.side{transform:translateX(-100%);transition:.2s;box-shadow:0 0 40px #000a}.side.open{transform:none}
   .content{margin-left:0}.hamb{display:grid}.searchpill{min-width:0;flex:1}.topbar p{display:none}}
 #cbtn{position:fixed;right:20px;bottom:20px;z-index:70;background:var(--mint);color:#06231b;border:none;width:54px;height:54px;border-radius:50%;font-size:23px;cursor:pointer;box-shadow:0 6px 20px rgba(78,227,184,.4)}
 #chat{position:fixed;right:20px;bottom:84px;width:360px;max-width:92vw;height:520px;max-height:76vh;z-index:70;background:var(--card);border:1px solid var(--line);border-radius:16px;display:none;flex-direction:column;overflow:hidden;box-shadow:0 10px 34px #000b}
 #chat.on{display:flex}
 #chat .ch{display:flex;align-items:center;gap:8px;padding:12px 14px;background:#0f1722;border-bottom:1px solid var(--line)} #chat .ch b{font-size:14px} #chat .ch .src{font-size:10px;color:var(--mut);margin-left:auto} #chat .ch .x{cursor:pointer;color:var(--mut)}
 #cmsgs{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:9px}
 .bub{max-width:84%;padding:9px 12px;border-radius:12px;font-size:13px;line-height:1.45;white-space:pre-wrap}
 .bub.u{align-self:flex-end;background:var(--mint);color:#06231b;border-bottom-right-radius:3px;font-weight:500}
 .bub.b{align-self:flex-start;background:#0c1219;border:1px solid var(--line);border-bottom-left-radius:3px}
 #cchips{display:flex;gap:6px;flex-wrap:wrap;padding:0 12px 8px} #cchips b{font-size:11px;background:#0c1219;border:1px solid var(--line);border-radius:14px;padding:5px 9px;cursor:pointer;color:#aab6c6} #cchips b:hover{border-color:var(--mint)}
 #cin{display:flex;gap:8px;padding:10px 12px;border-top:1px solid var(--line)} #cin input{flex:1;background:#0c1219;border:1px solid var(--line);color:var(--tx);border-radius:20px;padding:9px 13px;font:inherit} #cin button{background:var(--mint);color:#06231b;border:none;border-radius:50%;width:38px;height:38px;cursor:pointer;font-size:16px}
</style></head><body>
 <aside class="side" id="side">
   <div class="logo"><span class="mk">🚦</span>Grid<b>lock</b></div>
   <div class="ws"><span class="wi">🏙️</span><div><b>Bengaluru Traffic Police</b><span>Live · 298k records</span></div></div>
   __SIDEBAR__
   <div class="s-foot"><span class="s-role" id="rolebadge">—</span>
     <button onclick="logout()">Sign out</button></div>
 </aside>
 <div class="content">
   <header class="topbar">
     <div class="ic-btn hamb" onclick="document.getElementById('side').classList.toggle('open')">☰</div>
     <div><h1 id="ptitle">Overview</h1><p id="psub"></p></div>
     <div class="sp"></div>
     <div class="searchpill" onclick="chatToggle()">🔍 <span>Ask the assistant…</span></div>
     <span class="apistat" id="apidot"></span><div class="ic-btn">🔔</div>
     <div class="avatar" id="avatar">V</div>
   </header>
   <main>__BODY__</main>
 </div>
<button id="cbtn" onclick="chatToggle()" title="Ask the assistant">💬</button>
<div id="chat"><div class="ch"><b>🚦 Gridlock assistant</b><span class="src" id="csrc">instant</span><span class="x" onclick="chatToggle()">✕</span></div>
  <div id="cmsgs"></div>
  <div id="cchips"><b onclick="chatSend('Worst hotspots?')">Worst hotspots</b><b onclick="chatSend('Busiest police station?')">Busiest station</b><b onclick="chatSend('When is the peak?')">Peak hour</b><b onclick="chatSend('Where should we patrol today?')">Where to patrol</b><b onclick="chatSend('Any events this week?')">Events</b></div>
  <div id="cin"><input id="cintxt" placeholder="Ask about hotspots, patrols, events…"><button onclick="chatSend()">➤</button></div></div>
<script>
const API="http://localhost:8000", PAGES=__PAGES__;
const role=localStorage.getItem('gridlock_role');
if(!role){ location.replace('portal.html'); }
const canIngest=localStorage.getItem('gridlock_ingest')==='1', online=!!localStorage.getItem('gridlock_token');
function logout(){ localStorage.clear(); location.replace('portal.html'); }
function show(pid){
  document.querySelectorAll('.nav').forEach(t=>t.classList.toggle('on',t.dataset.p===pid));
  document.querySelectorAll('.pane').forEach(s=>s.classList.toggle('on',s.id==='p-'+pid));
  const p=PAGES[pid]; if(p){ document.getElementById('ptitle').innerHTML=p[0]; document.getElementById('psub').textContent=p[1]; }
  document.getElementById('side').classList.remove('open'); window.scrollTo({top:0,behavior:'smooth'});
}
(function(){
  const rb=document.getElementById('rolebadge'); rb.textContent=(role||'viewer').toUpperCase()+(canIngest?' · admin':' · read-only');
  rb.className='s-role '+(canIngest?'admin':'viewer'); document.getElementById('avatar').textContent=(role||'V')[0].toUpperCase();
  document.querySelectorAll('[data-admin]').forEach(t=>{ if(!canIngest) t.style.display='none'; });
  const dot=document.getElementById('apidot'); dot.textContent=online?'● API online':'○ offline (embedded)'; dot.style.color=online?'#4ee3b8':'#7d8a9c';
  document.querySelectorAll('.nav').forEach(t=>t.onclick=()=>show(t.dataset.p));
  const first=[...document.querySelectorAll('.nav')].find(t=>t.style.display!=='none'); if(first) show(first.dataset.p);
})();

/* ===== global hover tooltip (works on any element with data-t) ===== */
(function(){
  const ttip = document.createElement('div'); ttip.id='ttip'; document.body.appendChild(ttip);
  function show(text, x, y){ ttip.textContent=text; ttip.style.left=x+'px'; ttip.style.top=y+'px'; ttip.classList.add('on'); }
  function hide(){ ttip.classList.remove('on'); }
  document.addEventListener('mousemove', e => {
    const el = e.target.closest('[data-t]');
    if (!el) { hide(); document.querySelectorAll('.barc.bar-act').forEach(s=>s.classList.remove('bar-act')); document.querySelectorAll('.bar.on').forEach(b=>b.classList.remove('on')); return; }
    const rect = el.getBoundingClientRect();
    show(el.dataset.t, rect.left + rect.width/2, rect.top - 6);
    // SVG bar highlight: when the .hit rect is hovered, light up the matching .bar
    if (el.classList.contains('hit')) {
      const svg = el.closest('.barc');
      const bars = svg.querySelectorAll('rect.bar');
      const hits = [...svg.querySelectorAll('rect.hit')];
      const idx = hits.indexOf(el);
      svg.classList.add('bar-act');
      bars.forEach((b,i)=>b.classList.toggle('on', i===idx));
    }
  });
  document.addEventListener('mouseleave', hide, true);
})();

/* ===== hotspot table filters ===== */
function filterHotspots(){
  const tier = (document.getElementById('f-tier')||{}).value || 'All tiers';
  const stn  = (document.getElementById('f-stn')||{}).value || 'All stations';
  const q    = ((document.getElementById('f-q')||{}).value || '').toLowerCase();
  const min  = parseFloat((document.getElementById('f-cis')||{}).value || 0);
  const rows = document.querySelectorAll('#hot-tbl tbody tr');
  let shown = 0;
  rows.forEach(tr => {
    const t = tr.dataset.tier, s = tr.dataset.station, c = parseFloat(tr.dataset.cis);
    const text = tr.textContent.toLowerCase();
    const ok = (tier==='All tiers' || t===tier)
            && (stn==='All stations' || s===stn)
            && (!q || text.includes(q))
            && (c >= min);
    tr.style.display = ok ? '' : 'none';
    if (ok) shown++;
  });
  const cnt = document.getElementById('f-count');
  if (cnt) cnt.textContent = shown + ' of ' + rows.length.toLocaleString();
}

/* chatbot */
const CTX=__CHATCTX__;
function chatToggle(){ const c=document.getElementById('chat'); c.classList.toggle('on'); if(c.classList.contains('on')) document.getElementById('cintxt').focus(); }
function addBub(t,c){ const m=document.getElementById('cmsgs'); const d=document.createElement('div'); d.className='bub '+c; d.textContent=t; m.appendChild(d); m.scrollTop=m.scrollHeight; return d; }
async function chatSend(q){ q=(q||document.getElementById('cintxt').value).trim(); if(!q)return; document.getElementById('cintxt').value=''; addBub(q,'u'); const ty=addBub('…','b'); let ans,src='instant';
  try{ const ctl=new AbortController(); const to=setTimeout(()=>ctl.abort(),2200);
    const r=await fetch(API+'/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q}),signal:ctl.signal}); clearTimeout(to);
    if(r.ok){ const d=await r.json(); ans=d.answer; src=d.source==='ai'?'AI':'data'; } }catch(e){}
  if(!ans){ ans=localAnswer(q); src='instant'; } ty.textContent=ans; document.getElementById('csrc').textContent=src; }
function fmtH(h){ return (h==null)?'—':(String(h).padStart(2,'0')+':00'); }
function localAnswer(q){ q=q.toLowerCase().trim(); const o=CTX.overview||{}; const hot=CTX.top_hotspots||[],bs=CTX.busiest_stations||[],dp=CTX.deployment||[];
  const hl=n=>hot.slice(0,n).map(h=>`${h.junction} (${h.station}, ${h.violations.toLocaleString()} violations, CIS ${h.cis})`).join('; ');
  if(!q||/^(hi|hello|hey|help)/.test(q)) return 'Ask me e.g. "worst hotspots", "busiest station", "when is the peak", "where to patrol today", "events this week", or a junction/station name.';
  if(/(how many|total|number).*(violation|ticket|case)/.test(q)) return `There are ${(o.violations||0).toLocaleString()} violations across ${(o.zones||0).toLocaleString()} zones — ${o.critical||0} critical, ${o.high||0} high.`;
  if(/station|jurisdiction|thana/.test(q)&&bs.length) return 'Busiest stations: '+bs.slice(0,3).map(b=>`${b.station} (${b.violations.toLocaleString()})`).join(', ')+'.';
  if(/when|what time|peak|hour|busiest time/.test(q)) return `Citywide peak is around ${fmtH(o.peak_hour)} — focus patrols on the morning window.`;
  if(/deploy|patrol|where should|send|prioriti|today|roster/.test(q)&&dp.length){ const c=CTX.deploy_cover||{}; return 'Send patrols to: '+dp.slice(0,4).map(d=>`${d.point} (${d.station}) at ${d.window} on ${d.busiest_dow}`).join('; ')+(c.points?`. Top ${c.points} points = ~${c.located_pct}% of all violations.`:''); }
  if(/forecast|next week|predict|expect|upcoming|tomorrow/.test(q)&&(CTX.forecast||[]).length) return 'Predicted hot next week: '+CTX.forecast.slice(0,4).map(f=>`${f.junction} (~${f.pred_week})`).join(', ')+'.';
  if(/event|festival|rally|sale|match|surge|spike|procession/.test(q)){ const ai=CTX.ai_events||[]; if(ai.length) return 'Flagged this week: '+ai.slice(0,3).map(a=>`${a.risk} on ${a.date} — ${a.event} near ${a.junction}`).join('; ')+'.'; }
  if(/displace|whack|move|next door|corridor/.test(q)){ const dm=CTX.displacement||[]; return dm.length? 'Displacement risk at: '+dm.slice(0,4).map(d=>`${d.junction} (~${d.displacement_pct}%)`).join(', ')+' — treat as corridors.' : 'No strong displacement detected.'; }
  for(const b of bs){ if(q.includes(b.station.toLowerCase())) return `${b.station} has ${b.violations.toLocaleString()} violations.`; }
  for(const h of hot){ const nm=h.junction.toLowerCase(); if(q.includes(nm)||q.includes(nm.split(' - ').pop())) return `${h.junction} (${h.station}): ${h.violations.toLocaleString()} violations, CIS ${h.cis}, peaks ~${fmtH(h.peak_hour)}.`; }
  if(/worst|top|highest|biggest|hotspot|zone|area|junction|spot|problem/.test(q)) return 'Top hotspots: '+hl(3)+'.';
  return 'Try "worst hotspots", "busiest station", "peak hour", "where to patrol", "events this week", or a specific junction/station.';
}
document.getElementById('cintxt').addEventListener('keydown',e=>{ if(e.key==='Enter') chatSend(); });
addBub('Hi 👋 I\'m the Gridlock assistant. Ask me about hotspots, stations, timing, patrols, or events.','b');
</script></body></html>""").replace("__PAGES__", json.dumps(pages)).replace("__SIDEBAR__", sidebar)\
        .replace("__BODY__", "".join(f"<section class='pane' id='p-{pid}'>{panes.get(pid,'')}</section>" for pid in panes))\
        .replace("__CHATCTX__", chat_ctx)


def main():
    panes = build_panes()
    sidebar, pages = "", {}
    for group, items in GROUPS:
        grp_admin = " data-admin=1" if all(it[3] for it in items) else ""
        sidebar += f"<div class='s-grp'{grp_admin}>{group}</div>"
        for pid, icon, label, admin in items:
            badge = "<span class='s-badge'>admin</span>" if admin else ""
            sidebar += (f"<a class='nav{' admin' if admin else ''}' data-p='{pid}' "
                        f"{'data-admin=1' if admin else ''}><span class='s-ic'>{icon}</span>{label}{badge}</a>")
            pages[pid] = [label.replace(" & ", " &amp; "), SUBTITLE.get(pid, "")]
    try:
        chat_ctx = json.dumps(chatmod.build_context())
    except Exception:
        chat_ctx = "{}"

    (OUT_DIR / "portal.html").write_text(login_html(), encoding="utf-8")
    (OUT_DIR / "dashboard.html").write_text(
        dashboard_html(panes, pages, sidebar, chat_ctx), encoding="utf-8")
    (OUT_DIR / "index.html").write_text(
        '<!doctype html><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=portal.html">'
        '<title>Gridlock</title><body style="background:#080b11;color:#7d8a9c;'
        'font-family:Inter,sans-serif">Redirecting to '
        '<a href="portal.html" style="color:#4ee3b8">sign in</a>…</body>',
        encoding="utf-8")
    print("Wrote portal.html (login) | dashboard.html (app) | index.html (redirect to login)")


if __name__ == "__main__":
    main()
