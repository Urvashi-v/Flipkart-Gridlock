"""
app.py  —  Gridlock live dashboard (Streamlit).

    streamlit run app.py

Lets a traffic-ops user:
  * move the 5 Congestion-Impact-Score weights and watch zones re-rank and the
    map recolour live (the score is policy, not a black box);
  * filter by police station / minimum volume;
  * see next-week forecast hotspots and before/after enforcement impact.

Everything is computed from the artifacts produced by run_all.py + forecast.py +
impact.py, so the app is just a fast, interactive front-end.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT))
from config import (OUT_DIR, CIS_WEIGHTS, GRID_SIZE_M, M_PER_DEG_LAT)

LABELLED = OUT_DIR / "violations_labelled.parquet"

st.set_page_config(page_title="Gridlock · Parking Congestion Intelligence",
                   layout="wide", page_icon="🚦")


# ---------------------------------------------------------------- data
@st.cache_data(show_spinner="Aggregating zones…")
def load_zone_table():
    df = pd.read_parquet(LABELLED)
    df = df[df["zone"] != "__noise__"].copy()
    total_days = max((df["ts_ist"].max() - df["ts_ist"].min()).days, 1)
    g = df.groupby("zone")
    agg = pd.DataFrame({
        "n_tickets": g.size(),
        "w_tickets": g["conf_weight"].sum(),
        "lat": g["latitude"].mean(), "lon": g["longitude"].mean(),
        "sev_mean": g["severity"].mean(),
        "junction_share": g["at_junction"].mean(),
        "veh_mean": g["vehicle_block"].mean(),
        "n_days": g["date"].nunique(), "n_hours": g["hour"].nunique(),
        "rejected_share": g["is_rejected"].mean(),
        "top_violation": g["primary_violation"].agg(lambda s: s.mode().iloc[0]),
        "top_vehicle": g["vehicle_type"].agg(lambda s: s.mode().iloc[0]),
        "police_station": g["police_station"].agg(lambda s: s.mode().iloc[0]),
        "junction_name": g["junction_name"].agg(lambda s: s.mode().iloc[0]),
        "peak_hour": g["hour"].agg(lambda s: int(s.mode().iloc[0])),
    }).reset_index()
    agg["persistence"] = 0.6 * (agg["n_days"] / total_days) + 0.4 * (agg["n_hours"] / 24.0)
    return agg


@st.cache_data
def load_csv(name):
    p = OUT_DIR / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def minmax(s):
    lo, hi = s.min(), s.max()
    return (s - lo) / (hi - lo) if hi - lo > 1e-12 else pd.Series(0.0, index=s.index)


def compute_cis(agg, w):
    a = agg.copy()
    a["c_volume"] = minmax(np.log1p(a["w_tickets"]))
    a["c_severity"] = minmax(a["sev_mean"])
    a["c_junction"] = a["junction_share"]
    a["c_vehicle"] = minmax(a["veh_mean"])
    a["c_persistence"] = minmax(a["persistence"])
    tot = sum(w.values()) or 1.0
    a["CIS"] = 100 * (
        w["volume"] * a["c_volume"] + w["severity"] * a["c_severity"] +
        w["junction"] * a["c_junction"] + w["vehicle"] * a["c_vehicle"] +
        w["persistence"] * a["c_persistence"]) / tot
    a["tier"] = pd.cut(a["CIS"], [-1, 25, 45, 65, 101],
                       labels=["Low", "Medium", "High", "Critical"])
    return a.sort_values("CIS", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------- sidebar
st.sidebar.title("🚦 Gridlock controls")
st.sidebar.caption("Tune the Congestion Impact Score weights — the map and "
                   "ranking update live.")

w = {}
defaults = CIS_WEIGHTS
w["volume"]      = st.sidebar.slider("Volume (how many)", 0.0, 1.0, defaults["volume"], 0.05)
w["severity"]    = st.sidebar.slider("Severity (flow-blocking)", 0.0, 1.0, defaults["severity"], 0.05)
w["junction"]    = st.sidebar.slider("Junction proximity", 0.0, 1.0, defaults["junction"], 0.05)
w["vehicle"]     = st.sidebar.slider("Vehicle size", 0.0, 1.0, defaults["vehicle"], 0.05)
w["persistence"] = st.sidebar.slider("Persistence (chronic)", 0.0, 1.0, defaults["persistence"], 0.05)
wsum = sum(w.values())
st.sidebar.caption(f"Weights auto-normalise (sum now {wsum:.2f}).")
if st.sidebar.button("↺ Reset to defaults"):
    st.rerun()

agg = load_zone_table()
stations = ["(all)"] + sorted(agg["police_station"].unique())
sel_station = st.sidebar.selectbox("Police station", stations)
min_tickets = st.sidebar.slider("Min tickets per zone", 30, 1000, 30, 10)

view = agg.copy()
if sel_station != "(all)":
    view = view[view["police_station"] == sel_station]
view = view[view["n_tickets"] >= min_tickets]
scored = compute_cis(view, w)

# ---------------------------------------------------------------- header + KPIs
st.title("Parking Congestion Intelligence")
st.caption("AI-driven detection of illegal-parking hotspots and their impact on "
           "traffic flow · Bengaluru Traffic Police")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Zones shown", f"{len(scored):,}")
c2.metric("Critical", int((scored['tier'] == 'Critical').sum()))
c3.metric("High", int((scored['tier'] == 'High').sum()))
c4.metric("Tickets in view", f"{int(scored['n_tickets'].sum()):,}")
c5.metric("Top CIS", f"{scored['CIS'].max():.1f}" if len(scored) else "—")

(tab_map, tab_rank, tab_deploy, tab_ctx,
 tab_fc, tab_ai, tab_impact, tab_events) = st.tabs(
    ["🗺️ Hotspot map", "📋 Ranked zones", "🎯 Deployment",
     "📍 Context", "🔮 Forecast", "🤖 AI event forecast", "📉 Impact", "📅 Events"])

# ---- map -------------------------------------------------------------
with tab_map:
    if len(scored):
        fig = px.scatter_map(
            scored, lat="lat", lon="lon", color="CIS", size="n_tickets",
            color_continuous_scale="YlOrRd", size_max=22, zoom=11, height=620,
            hover_name="junction_name",
            hover_data={"CIS": ":.1f", "tier": True, "n_tickets": True,
                        "police_station": True, "top_violation": True,
                        "peak_hour": True, "lat": False, "lon": False},
        )
        fig.update_layout(map_style="carto-positron",
                          margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No zones match the current filters.")

# ---- ranked table ----------------------------------------------------
with tab_rank:
    show = scored.head(100).copy()
    show.insert(0, "rank", np.arange(1, len(show) + 1))
    show["CIS"] = show["CIS"].round(1)
    show["junction_share"] = (show["junction_share"] * 100).round(0)
    cols = ["rank", "CIS", "tier", "n_tickets", "junction_name", "police_station",
            "top_violation", "top_vehicle", "peak_hour", "junction_share",
            "c_volume", "c_severity", "c_junction", "c_vehicle", "c_persistence"]
    st.dataframe(show[cols], use_container_width=True, height=560,
                 column_config={"junction_share": st.column_config.NumberColumn("jn %"),
                                "CIS": st.column_config.NumberColumn(format="%.1f")})
    st.download_button("⬇️ Download ranked zones (CSV)",
                       show[cols].to_csv(index=False), "hotspots_ranked.csv")

# ---- deployment / ROI ------------------------------------------------
with tab_deploy:
    plan = load_csv("deployment_plan.csv")
    if len(plan):
        K = st.slider("Patrol-shifts per day to deploy", 5, 100, 25, 5)
        locK = plan["cum_located_%"].iloc[min(K, len(plan)) - 1]
        capK = plan["cum_captured_%"].iloc[min(K, len(plan)) - 1]
        total_v = int(plan["violations"].sum())
        st.subheader("Optimised enforcement deployment")
        m1, m2, m3 = st.columns(3)
        m1.metric(f"Violations in top {K} points", f"{locK:.0f}%", "of citywide")
        m2.metric("Realistically captured", f"~{capK:.0f}%")
        m3.metric("Violations addressed", f"{int(total_v*capK/100):,}")
        roster = plan.head(K).copy()
        st.map(roster.rename(columns={"lat": "latitude", "lon": "longitude"})[["latitude", "longitude"]])
        st.dataframe(roster[["priority", "junction_name", "police_station", "window",
                     "busiest_dow", "violations", "cum_located_%", "corridor"]],
                     use_container_width=True, height=380)
        st.download_button("⬇️ Download deployment roster (CSV)",
                           roster.to_csv(index=False), "deployment_plan.csv")
        img = OUT_DIR / "optimize_coverage.png"
        if img.exists():
            st.image(str(img), caption="Enforcement ROI coverage curve")
    else:
        st.warning("Run  python src/optimize.py  to generate the deployment plan.")

# ---- context ---------------------------------------------------------
with tab_ctx:
    ctx = load_csv("zone_context.csv")
    if len(ctx) and "context" in ctx.columns:
        st.subheader("Why the hotspots exist — demand-generator attribution")
        by = (ctx.groupby("context")
                 .agg(zones=("zone", "size"), tickets=("n_tickets", "sum"))
                 .sort_values("tickets", ascending=False).reset_index())
        fig = px.bar(by, x="tickets", y="context", orientation="h",
                     color="tickets", color_continuous_scale="Reds", height=400)
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)
        sel = st.selectbox("Inspect a category", by["context"])
        st.dataframe(ctx[ctx["context"] == sel][["junction_name", "police_station",
                     "n_tickets", "generator_kw"]].sort_values("n_tickets", ascending=False)
                     .head(30), use_container_width=True, height=320)
    else:
        st.warning("Run  python src/context.py  to generate context tags.")

# ---- AI event forecast ----------------------------------------------
with tab_ai:
    aif = load_csv("ai_event_forecast.csv")
    st.subheader("🤖 AI event-aware forecast")
    st.caption("An internet-connected Claude agent finds real upcoming events "
               "(festivals, matches, sales, rallies) and reasons about which "
               "hotspots they'll overload — so police can prepare the day before.")
    if len(aif):
        mode = aif["source"].iloc[0] if "source" in aif.columns else "offline"
        if mode == "live":
            st.success("LIVE — events fetched via web search + reasoned by Claude.")
        else:
            st.info("OFFLINE sample mode. Set ANTHROPIC_API_KEY and rerun "
                    "`python src/ai_agent.py` to fetch real events live.")
        sev = (aif["risk_level"] == "Severe").sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Event-hotspot risks", len(aif))
        c2.metric("Severe", int(sev))
        c3.metric("Days covered", aif["date"].nunique())
        if {"lat", "lon"}.issubset(aif.columns) and aif["lat"].notna().any():
            m = aif.dropna(subset=["lat", "lon"]).rename(
                columns={"lat": "latitude", "lon": "longitude"})
            st.map(m[["latitude", "longitude"]])
        for d, g in aif.groupby("date"):
            st.markdown(f"**📅 {d}**")
            for _, r in g.iterrows():
                dot = {"Severe": "🔴", "High": "🟠", "Elevated": "🟡"}.get(r["risk_level"], "⚪")
                with st.expander(f"{dot} {r['risk_level']} · {r['junction_name']} — {r['event_name']}"):
                    st.write(f"**Why:** {r['reasoning']}")
                    st.write(f"**Do now:** {r['recommended_action']}")
                    if pd.notna(r.get("baseline_pred")) and r["baseline_pred"]:
                        st.caption(f"Baseline forecast ~{int(r['baseline_pred'])} violations/week.")
        bp = OUT_DIR / "ai_briefings.md"
        if bp.exists():
            st.download_button("⬇️ Download AI briefing (markdown)",
                               bp.read_text(encoding="utf-8"), "ai_briefings.md")
    else:
        st.warning("Run  python src/ai_agent.py  to generate the event forecast.")

# ---- forecast --------------------------------------------------------
with tab_fc:
    fc = load_csv("forecast_hotspots.csv")
    if len(fc):
        st.subheader("Predicted hotspots — next 7 days")
        st.caption("Gradient-boosted 7-day-ahead forecast of ticket load per zone.")
        fig = px.scatter_map(fc.head(150), lat="lat", lon="lon",
                             size="pred_week", color="pred_week",
                             color_continuous_scale="YlOrRd", size_max=24,
                             zoom=11, height=560, hover_name="junction_name",
                             hover_data={"pred_week": ":.0f", "police_station": True})
        fig.update_layout(map_style="carto-positron", margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(fc.head(40)[["rank", "pred_week", "junction_name", "police_station"]],
                     use_container_width=True, height=320)
        img = OUT_DIR / "forecast_accuracy.png"
        if img.exists():
            st.image(str(img), caption="Holdout accuracy (model vs actual)")
    else:
        st.warning("Run  python src/forecast.py  to generate forecasts.")

# ---- impact ----------------------------------------------------------
with tab_impact:
    rep = load_csv("impact_report.csv")
    if len(rep):
        st.subheader("Before / after enforcement impact (Difference-in-Differences)")
        st.caption("DiD change controls for citywide trend. Negative = illegal "
                   "parking fell more than the city did.")
        vc = rep["verdict"].value_counts()
        k1, k2, k3 = st.columns(3)
        k1.metric("Strong reductions", int(vc.get("Strong reduction", 0)))
        k2.metric("Reductions", int(vc.get("Reduction", 0)))
        k3.metric("Rebounds", int(vc.get("Worsened / rebound", 0)))
        st.dataframe(rep, use_container_width=True, height=340)
        img = OUT_DIR / "impact_demo.png"
        if img.exists():
            st.image(str(img), caption="Clearest measured reduction")

        # ---- displacement / whack-a-mole ----
        disp = load_csv("displacement_report.csv")
        if len(disp):
            st.markdown("---")
            st.subheader("🔀 Displacement check — solved, or just moved next door?")
            st.caption("For each crackdown, compares the treated zone's drop with the "
                       "DiD-adjusted change in zones within 400 m. >40% = whack-a-mole.")
            dvc = disp["verdict"].value_counts()
            d1, d2, d3 = st.columns(3)
            d1.metric("Genuine reductions", int(dvc.get("Genuine reduction", 0)))
            d2.metric("Displacement cases",
                      int(dvc.get("Partial displacement", 0)) +
                      int(dvc.get("Displacement (whack-a-mole)", 0)))
            d3.metric("Inconclusive", int(dvc.get("Inconclusive (no drop)", 0)))
            st.dataframe(disp, use_container_width=True, height=300)
            dimg = OUT_DIR / "displacement_demo.png"
            if dimg.exists():
                st.image(str(dimg), caption="Treated zone vs neighbours, before/after")
    else:
        st.warning("Run  python src/impact.py  to generate the impact report.")

# ---- events ----------------------------------------------------------
with tab_events:
    ev = load_csv("events.csv")
    if len(ev):
        st.subheader("Event / surge detection")
        st.caption("Robust z-score (median/MAD) flags days a zone's load suddenly "
                   "surges — festivals, sales, matches, rallies.")
        st.metric("Event spike-days detected", f"{len(ev):,}")
        st.dataframe(ev[["date", "dow", "junction_name", "police_station",
                     "count", "normal_day", "z_score"]].head(40),
                     use_container_width=True, height=360)
        img = OUT_DIR / "events_timeline.png"
        if img.exists():
            st.image(str(img), caption="Citywide daily load with spike days flagged")
        st.caption("Caveat: surges partly reflect enforcement drives, not only true demand.")
    else:
        st.warning("Run  python src/anomaly.py  to generate the event report.")

st.caption("Built for the parking-congestion problem statement · scores & weights "
           "fully configurable in config.py")
