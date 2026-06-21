"""
chat.py  —  the data brain behind the officer chatbot. Builds a compact context
from the built artifacts and answers plain-language questions quantitatively.

Two answer paths:
  * answer_ai()    — Claude (claude-opus-4-8) grounded strictly in the context,
                     used when ANTHROPIC_API_KEY is set (richer phrasing).
  * answer_rules() — deterministic keyword rules over the same context, so it
                     works with no key and is fully testable.

The portal embeds build_context() output so the sidebar can also answer offline
in the browser when the API isn't running.
"""
import os, sys, json, re
from functools import lru_cache
from pathlib import Path
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR, AI


def _csv(name):
    p = OUT_DIR / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


@lru_cache(maxsize=1)
def build_context():
    """A small, JSON-able snapshot of the key numbers for grounding answers."""
    hot = _csv("hotspots.csv")
    plan = _csv("deployment_plan.csv")
    fc = _csv("forecast_hotspots.csv")
    ev = _csv("events.csv")
    disp = _csv("displacement_report.csv")
    ctx = _csv("zone_context.csv")
    ai = _csv("ai_event_forecast.csv")
    out = {}
    if not len(hot):
        return out

    # citywide peak hour from the labelled data if available, else zone modes
    peak_hour = None
    lp = OUT_DIR / "violations_labelled.parquet"
    try:
        if lp.exists():
            h = pd.read_parquet(lp, columns=["hour"])["hour"]
            peak_hour = int(h.value_counts().idxmax())
    except Exception:
        pass
    if peak_hour is None and "peak_hour" in hot:
        peak_hour = int(hot["peak_hour"].mode().iloc[0])

    total = int(hot["n_tickets"].sum())
    top5 = hot.head(max(1, int(0.05 * len(hot))))["n_tickets"].sum()
    out["overview"] = {
        "violations": total,
        "zones": int(len(hot)),
        "critical": int((hot["tier"] == "Critical").sum()),
        "high": int((hot["tier"] == "High").sum()),
        "peak_hour": peak_hour,
        "top5pct_share": round(float(top5 / total * 100), 0),
        "top_zone": str(hot.iloc[0]["junction_name"]),
        "top_zone_station": str(hot.iloc[0]["police_station"]),
        "top_zone_cis": round(float(hot.iloc[0]["CIS"]), 1),
        "top_zone_tickets": int(hot.iloc[0]["n_tickets"]),
    }
    out["top_hotspots"] = [{
        "rank": int(r["rank"]), "junction": str(r["junction_name"]),
        "station": str(r["police_station"]), "cis": round(float(r["CIS"]), 1),
        "violations": int(r["n_tickets"]), "top_violation": str(r.get("top_violation", "")),
        "peak_hour": int(r["peak_hour"]) if "peak_hour" in r else None,
    } for _, r in hot.head(10).iterrows()]
    bs = hot.groupby("police_station")["n_tickets"].sum().sort_values(ascending=False).head(8)
    out["busiest_stations"] = [{"station": k, "violations": int(v)} for k, v in bs.items()]

    if len(plan):
        out["deployment"] = [{
            "priority": int(r["priority"]), "point": str(r["junction_name"]),
            "station": str(r["police_station"]), "window": str(r["window"]),
            "busiest_dow": str(r["busiest_dow"]), "violations": int(r["violations"]),
            "corridor": bool(r.get("corridor", False)),
        } for _, r in plan.head(8).iterrows()]
        out["deploy_cover"] = {
            "points": min(25, len(plan)),
            "located_pct": round(float(plan["cum_located_%"].iloc[min(25, len(plan)) - 1]), 0),
        }
    if len(fc):
        out["forecast"] = [{
            "rank": int(r["rank"]), "junction": str(r["junction_name"]),
            "station": str(r["police_station"]), "pred_week": round(float(r["pred_week"]), 0),
        } for _, r in fc.head(8).iterrows()]
    if len(ev):
        out["events"] = [{
            "date": str(r["date"]), "junction": str(r["junction_name"]),
            "station": str(r["police_station"]), "count": int(r["count"]),
            "normal": float(r["normal_day"]),
        } for _, r in ev.head(8).iterrows()]
        out["n_event_days"] = int(len(ev))
    if len(disp):
        wm = disp[disp["verdict"].astype(str).str.startswith("Displacement")]
        out["displacement"] = [{
            "junction": str(r["junction_name"]), "station": str(r["police_station"]),
            "displacement_pct": round(float(r["displacement_%"]), 0),
        } for _, r in wm.head(5).iterrows()]
    if len(ctx) and "context" in ctx.columns:
        by = (ctx.groupby("context")["n_tickets"].sum().sort_values(ascending=False))
        tot = by.sum() or 1
        out["context_mix"] = [{"generator": k, "violations": int(v),
                               "pct": round(float(v / tot * 100), 0)} for k, v in by.head(8).items()]
    if len(ai):
        out["ai_events"] = [{
            "date": str(r["date"]), "junction": str(r["junction_name"]),
            "risk": str(r["risk_level"]), "event": str(r["event_name"]),
        } for _, r in ai.head(6).iterrows()]
    return out


# ------------------------------------------------------------------ rules
def _fmt_hour(h):
    return f"{int(h):02d}:00" if h is not None else "—"


def answer_rules(question, ctx=None):
    ctx = ctx if ctx is not None else build_context()
    if not ctx:
        return "The analytics aren't built yet — run the pipeline first."
    q = (question or "").lower().strip()
    ov = ctx.get("overview", {})

    def hot_list(n=3):
        return "; ".join(f"{h['junction']} ({h['station']}, {h['violations']:,} violations, "
                         f"CIS {h['cis']})" for h in ctx.get("top_hotspots", [])[:n])

    if not q or re.search(r"^(hi|hello|hey|help|what can you)", q):
        return ("Ask me about the parking data — e.g. \"worst hotspots\", "
                "\"busiest police station\", \"when is the peak\", \"where should we "
                "patrol today\", \"any events this week\", or \"displacement risks\".")

    if re.search(r"how many|total|number of", q) and re.search(r"violation|ticket|case", q):
        return (f"There are {ov.get('violations',0):,} illegal-parking violations across "
                f"{ov.get('zones',0):,} enforcement zones — {ov.get('critical',0)} are critical "
                f"hotspots and {ov.get('high',0)} are high.")

    if re.search(r"critical|how many hotspot", q):
        return (f"{ov.get('critical',0)} critical and {ov.get('high',0)} high-priority hotspots. "
                f"The worst is {ov.get('top_zone','?')} ({ov.get('top_zone_station','?')}) with "
                f"CIS {ov.get('top_zone_cis','?')} and {ov.get('top_zone_tickets',0):,} violations.")

    if re.search(r"station|jurisdiction|thana", q):
        bs = ctx.get("busiest_stations", [])[:3]
        if bs:
            return ("Busiest police stations by violations: "
                    + ", ".join(f"{b['station']} ({b['violations']:,})" for b in bs) + ".")

    if re.search(r"when|what time|peak|hour|busiest time", q):
        return (f"The citywide peak is around {_fmt_hour(ov.get('peak_hour'))}. Most enforcement "
                "pressure is in the morning window; plan patrols accordingly.")

    if re.search(r"deploy|patrol|where should|send|prioriti|today|roster", q):
        dp = ctx.get("deployment", [])[:5]
        cov = ctx.get("deploy_cover", {})
        if dp:
            lines = "; ".join(f"{d['point']} ({d['station']}) at {d['window']} on {d['busiest_dow']}"
                              for d in dp)
            cv = (f" Covering the top {cov.get('points',25)} points hits about "
                  f"{cov.get('located_pct',0):.0f}% of all violations." if cov else "")
            return f"Send patrols to: {lines}.{cv}"

    if re.search(r"forecast|next week|predict|expect|upcoming|tomorrow", q):
        fc = ctx.get("forecast", [])[:4]
        ai = ctx.get("ai_events", [])[:2]
        msg = ""
        if fc:
            msg = ("Predicted hot next week: "
                   + ", ".join(f"{f['junction']} (~{f['pred_week']:.0f})" for f in fc) + ".")
        if ai:
            msg += " Event watch: " + "; ".join(f"{a['risk']} on {a['date']} — {a['event']} near "
                                                 f"{a['junction']}" for a in ai)
        return msg or "No forecast available yet."

    if re.search(r"event|festival|rally|sale|match|surge|spike|procession", q):
        ai = ctx.get("ai_events", [])
        if ai:
            return ("This week's flagged events: "
                    + "; ".join(f"{a['risk']} on {a['date']} — {a['event']} near {a['junction']}"
                               for a in ai[:4]) + ".")
        ev = ctx.get("events", [])[:3]
        if ev:
            return ("Recent surge days: "
                    + "; ".join(f"{e['date']} at {e['junction']} ({e['count']} vs ~{e['normal']:.0f} normal)"
                               for e in ev) + ".")

    if re.search(r"displace|whack|move|next door|corridor|spread", q):
        dm = ctx.get("displacement", [])
        if dm:
            return ("Watch for displacement (cars moving next door) at: "
                    + ", ".join(f"{d['junction']} (~{d['displacement_pct']:.0f}%)" for d in dm[:4])
                    + ". Treat these as corridors, not single blocks.")
        return "No strong displacement cases were detected — enforcement effects mostly held."

    for kw, label in [("market", "Wholesale market"), ("metro", "Metro / Transit hub"),
                      ("mall", "Mall / Shopping"), ("shop", "Mall / Shopping"),
                      ("hospital", "Hospital"), ("school", "Education"),
                      ("college", "Education"), ("temple", "Religious"),
                      ("entertain", "Entertainment"), ("cinema", "Entertainment")]:
        if kw in q:
            for c in ctx.get("context_mix", []):
                if c["generator"] == label:
                    return (f"{label} areas account for {c['violations']:,} violations "
                            f"({c['pct']:.0f}% of the total).")

    # station / junction name lookup
    for b in ctx.get("busiest_stations", []):
        if b["station"].lower() in q:
            return f"{b['station']} has {b['violations']:,} illegal-parking violations."
    for h in ctx.get("top_hotspots", []):
        nm = h["junction"].lower()
        if nm in q or (len(nm) > 6 and nm.split(" - ")[-1] in q):
            return (f"{h['junction']} ({h['station']}): {h['violations']:,} violations, "
                    f"CIS {h['cis']}, peaks around {_fmt_hour(h.get('peak_hour'))}. "
                    f"Top offence: {h['top_violation']}.")

    if re.search(r"worst|top|highest|biggest|hotspot|zone|area|junction|spot|problem", q):
        return f"Top hotspots right now: {hot_list(3)}."

    return ("I can answer with the parking data — try \"worst hotspots\", \"busiest "
            "station\", \"peak hour\", \"where to patrol\", \"events this week\", or a "
            "specific junction/station name.")


# ------------------------------------------------------------------ AI
def answer_ai(question, ctx=None):
    ctx = ctx if ctx is not None else build_context()
    import anthropic
    client = anthropic.Anthropic()
    system = (
        "You are Gridlock Assistant, a helper for Bengaluru traffic police officers. "
        "Answer ONLY using the JSON data context provided. Be QUANTITATIVE — cite exact "
        "numbers (violations, CIS, %, times, dates). Use short, plain, everyday language "
        "(2-4 sentences, no jargon). If the answer is not in the data, say so plainly and "
        "suggest what you can answer. Never invent numbers.")
    msg = client.messages.create(
        model=AI["model"], max_tokens=500,
        system=system,
        messages=[{"role": "user",
                   "content": f"DATA CONTEXT (JSON):\n{json.dumps(ctx)}\n\nOFFICER QUESTION: {question}"}])
    return "".join(b.text for b in msg.content if b.type == "text").strip()


if __name__ == "__main__":
    c = build_context()
    print("context keys:", list(c.keys()))
    for q in ["worst hotspots", "busiest police station", "when is the peak",
              "where should we patrol today", "any events this week", "how many violations"]:
        print(f"\nQ: {q}\nA: {answer_rules(q, c)}")
