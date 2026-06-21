"""
ai_agent.py  —  the AI layer on top of the ML.

Everything before this file is statistics: it tells you WHERE illegal parking
usually is and, from history, roughly how much to expect next week. It cannot
know that next Tuesday is a festival, that a cricket match fills a stadium on
Saturday, or that a mall starts its end-of-season sale on Friday — the things
that actually spike congestion on a given day.

This module is an internet-connected Claude agent (model claude-opus-4-8) that:
  1. uses the web_search tool to find real upcoming demand drivers in the city
     for the next 7 days — festivals/holidays, scheduled events at venues,
     rallies/protests, mall & market sales;
  2. maps each event to the parking hotspots it will overload (by area);
  3. fuses that with the statistical forecast and REASONS about it — producing,
     per zone per day, an event-aware risk level, a plain-English explanation
     ("severe — Ganesh Chaturthi immersion near KR Market on a Sunday"), and a
     concrete "prepare the day before" recommendation for the police.

Live mode needs ANTHROPIC_API_KEY in the environment. Without it (or if the
network/API fails), the module degrades to a clearly-labelled offline sample so
the dashboard and demo still work — it never breaks the pipeline.

Outputs:
  outputs/ai_events.json          - the raw events the agent found (provenance)
  outputs/ai_event_forecast.csv   - per zone-day event-aware risk + reasoning
  outputs/ai_briefings.md         - human-readable "tomorrow needs groundwork" brief
"""
import os, sys, json, re
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

try:                                  # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR, AI

EVENTS_JSON = OUT_DIR / "ai_events.json"
FORECAST_CSV = OUT_DIR / "ai_event_forecast.csv"
BRIEFINGS_MD = OUT_DIR / "ai_briefings.md"

RISK_ORDER = {"Severe": 3, "High": 2, "Elevated": 1, "Normal": 0}
STOP = {"the", "and", "near", "road", "cross", "main", "junction", "circle",
        "bengaluru", "bangalore", "karnataka", "india", "layout", "nagar", "pin"}


# ====================================================================== LIVE
def have_api():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _extract_json(text):
    """Pull a JSON array out of the model's text (fenced or bare)."""
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    blob = m.group(1) if m else None
    if blob is None:
        i, j = text.find("["), text.rfind("]")
        blob = text[i:j + 1] if (i != -1 and j != -1 and j > i) else None
    if not blob:
        return []
    try:
        return json.loads(blob)
    except Exception:
        return []


def fetch_events_live(start, end):
    """Agentic web_search call → list of upcoming-event dicts (or None on failure)."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        city = AI["city"]
        prompt = (
            f"You are a traffic-operations intelligence agent for {city} city police. "
            f"Using web search, find real events likely to drive vehicle congestion in "
            f"{city} between {start.isoformat()} and {end.isoformat()} (inclusive). "
            "Include: festivals & public holidays, scheduled events at major venues "
            "(concerts, cricket/football matches, exhibitions, conventions), political "
            "rallies or processions, and big retail/mall sale launches. "
            "Return ONLY a JSON array, no prose, where each item is:\n"
            '{"name": str, "date": "YYYY-MM-DD", "type": '
            '"festival|holiday|sports|concert|exhibition|rally|sale|other", '
            '"area": "specific locality/venue/road in the city", '
            '"expected_crowd": "low|medium|high", '
            '"why_congestion": "one line on why it chokes traffic"}.\n'
            f"Limit to the {AI['max_events']} most traffic-relevant. If you find few real "
            "events, return what you can verify — do not invent."
        )
        tools = [{"type": "web_search_20260209", "name": "web_search"}]
        user_msg = {"role": "user", "content": prompt}
        messages = [user_msg]
        for _ in range(6):                       # cap server-tool continuations
            resp = client.messages.create(
                model=AI["model"], max_tokens=16000, tools=tools, messages=messages)
            if resp.stop_reason == "pause_turn":
                messages = [user_msg, {"role": "assistant", "content": resp.content}]
                continue
            text = "".join(b.text for b in resp.content if b.type == "text")
            events = _extract_json(text)
            return events if events else None
        return None
    except Exception as e:
        print(f"  [live events] failed ({type(e).__name__}: {e}); using offline sample.")
        return None


def assess_live(matched_rows):
    """Structured Claude reasoning over matched (event, zone) rows → enriched rows."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        payload = [{
            "id": i, "date": r["date"], "weekday": r["weekday"], "event": r["event_name"],
            "type": r["event_type"], "area": r["area"], "expected_crowd": r["expected_crowd"],
            "hotspot": r["junction_name"], "police_station": r["police_station"],
            "baseline_violations_week": r["baseline_pred"],
        } for i, r in enumerate(matched_rows)]
        prompt = (
            "You are a traffic-police planning agent. For each item, a real upcoming "
            "event has been matched to a known illegal-parking hotspot. Reason about the "
            "congestion risk and what the police should do the day before. Return ONLY a "
            "JSON array; one object per input id:\n"
            '{"id": int, "risk_level": "Elevated|High|Severe", '
            '"reasoning": "2 sentences: why this event raises congestion at this hotspot", '
            '"recommended_action": "concrete pre-positioning / coordination step", '
            '"lead_time_hours": int}.\n\nINPUT:\n' + json.dumps(payload, ensure_ascii=False)
        )
        resp = client.messages.create(
            model=AI["model"], max_tokens=16000,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in resp.content if b.type == "text")
        out = {o["id"]: o for o in _extract_json(text) if "id" in o}
        for i, r in enumerate(matched_rows):
            o = out.get(i, {})
            r["risk_level"] = o.get("risk_level", r["risk_level"])
            r["reasoning"] = o.get("reasoning", r["reasoning"])
            r["recommended_action"] = o.get("recommended_action", r["recommended_action"])
        return matched_rows
    except Exception as e:
        print(f"  [live reasoning] failed ({type(e).__name__}); keeping heuristic reasoning.")
        return matched_rows


# =================================================================== OFFLINE
def sample_events(start, end, zones):
    """Illustrative events anchored to CONTEXT-MATCHED real hotspots so the offline
    demo is coherent (wholesale event -> a market zone, sale -> a mall zone, etc.).
    Clearly flagged as offline."""
    # (name, type, crowd, why, preferred zone context)
    templates = [
        ("Weekend wholesale market surge", "festival", "high",
         "wholesale buyers and loading vehicles overrun the market approaches",
         "Wholesale market"),
        ("Mall end-of-season sale launch", "sale", "high",
         "shopper inflow overflows mall parking onto feeder roads", "Mall / Shopping"),
        ("Temple festival procession", "festival", "high",
         "procession and devotee parking block the carriageway", "Religious"),
        ("Weekend cinema / entertainment rush", "concert", "high",
         "show-time arrivals spike parking around the venue", "Entertainment"),
        ("Metro-station feeder overflow", "other", "medium",
         "last-mile vehicles park on station approaches", "Metro / Transit hub"),
        ("Commercial-street political rally", "rally", "high",
         "assembly and march occupy road space for hours", "Commercial street"),
    ]
    span = max((end - start).days, 1)
    used, rows = set(), []
    has_ctx = "context" in zones.columns
    for k, (name, typ, crowd, why, want_ctx) in enumerate(templates):
        pool = zones[zones["context"] == want_ctx] if has_ctx else zones
        pool = pool[~pool["junction_name"].isin(used)]
        if pool.empty:
            pool = zones[~zones["junction_name"].isin(used)]
        if pool.empty:
            pool = zones
        z = pool.iloc[0]
        used.add(z["junction_name"])
        d = start + timedelta(days=min(span, 1 + (k * span) // len(templates)))
        area = str(z["junction_name"]).split(" - ")[-1].strip()
        rows.append({"name": name, "date": d.isoformat(), "type": typ,
                     "area": area, "expected_crowd": crowd, "why_congestion": why})
    return rows


# =================================================================== MATCHING
def _keywords(*texts):
    toks = re.findall(r"[a-z]{4,}", " ".join(str(t) for t in texts).lower())
    return {t for t in toks if t not in STOP}


def match_events_to_zones(events, zones):
    """Map each event to the hotspot zones whose area text it overlaps."""
    z = zones.copy()
    z["hay"] = (z["junction_name"].astype(str) + " " + z["police_station"].astype(str)
                + " " + z.get("address", "").astype(str) + " "
                + z.get("context", "").astype(str)).str.lower()
    rows = []
    for ev in events:
        ekw = _keywords(ev.get("area", ""), ev.get("name", ""))
        if not ekw:
            continue
        scored = []
        for _, zr in z.iterrows():
            hit = sum(1 for k in ekw if k in zr["hay"])
            if hit:
                scored.append((hit, zr))
        scored.sort(key=lambda x: -x[0])
        seen_jn = set()
        for hit, zr in scored:                   # up to 2 DISTINCT junctions per event
            if zr["junction_name"] in seen_jn:
                continue
            seen_jn.add(zr["junction_name"])
            if len(seen_jn) > 2:
                break
            d = pd.to_datetime(ev["date"]).date()
            crowd = str(ev.get("expected_crowd", "medium")).lower()
            base = float(zr.get("baseline_pred", 0) or 0)
            # heuristic baseline risk (Claude may override in live mode)
            risk = "Severe" if crowd == "high" else ("High" if crowd == "medium" else "Elevated")
            rows.append({
                "date": ev["date"], "weekday": d.strftime("%A"),
                "event_name": ev.get("name", "Event"), "event_type": ev.get("type", "other"),
                "area": ev.get("area", ""), "expected_crowd": crowd,
                "junction_name": zr["junction_name"], "police_station": zr["police_station"],
                "lat": zr.get("lat"), "lon": zr.get("lon"),
                "baseline_pred": round(base, 0),
                "risk_level": risk,
                "reasoning": (f"{ev.get('name','Event')} ({ev.get('type','event')}) near "
                              f"{ev.get('area','')} coincides with a known hotspot at "
                              f"{zr['junction_name']}; {ev.get('why_congestion','')}."),
                "recommended_action": ("Pre-position a patrol unit and tow vehicle the "
                                       "evening before; mark no-parking on approaches and "
                                       "brief the morning shift."),
                "match_strength": hit,
            })
    return rows


# ===================================================================== MAIN
def load_zones():
    hot = pd.read_csv(OUT_DIR / "hotspots.csv")
    cols = ["zone", "junction_name", "police_station", "address", "lat", "lon",
            "n_tickets", "CIS", "rank"]
    hot = hot[[c for c in cols if c in hot.columns]]
    fc = OUT_DIR / "forecast_hotspots.csv"
    if fc.exists():
        f = pd.read_csv(fc)[["zone", "pred_week"]].rename(columns={"pred_week": "baseline_pred"})
        hot = hot.merge(f, on="zone", how="left")
    ctx = OUT_DIR / "zone_context.csv"
    if ctx.exists():
        c = pd.read_csv(ctx)[["zone", "context"]]
        hot = hot.merge(c, on="zone", how="left")
    return hot.sort_values("rank").head(AI["top_zones_for_ai"]).reset_index(drop=True)


def write_briefings(rows, mode, start, end):
    df = pd.DataFrame(rows)
    if len(df):
        df["risk_rank"] = df["risk_level"].map(RISK_ORDER).fillna(0)
        df = df.sort_values(["date", "risk_rank"], ascending=[True, False])
    L = ["# 🤖 AI Event-Aware Congestion Forecast",
         f"**{start.isoformat()} → {end.isoformat()}**  ·  "
         f"mode: {'LIVE (web search + Claude reasoning)' if mode=='live' else 'OFFLINE sample (set ANTHROPIC_API_KEY for live)'}\n",
         "The statistical model says where parking is usually bad. This agent adds "
         "*what's happening this week* — so enforcement can prepare the day before.\n"]
    emoji = {"Severe": "🔴", "High": "🟠", "Elevated": "🟡"}
    for d, g in df.groupby("date") if len(df) else []:
        dt = pd.to_datetime(d).date()
        when = "Tomorrow" if dt == date.today() + timedelta(days=1) else dt.strftime("%a %d %b")
        L.append(f"\n## 📅 {when} ({d})")
        for _, r in g.iterrows():
            L.append(f"- {emoji.get(r['risk_level'],'⚪')} **{r['risk_level']}** · "
                     f"{r['junction_name']} ({r['police_station']})")
            L.append(f"  - **Why:** {r['reasoning']}")
            L.append(f"  - **Do now:** {r['recommended_action']}")
            if pd.notna(r.get("baseline_pred")) and r["baseline_pred"]:
                L.append(f"  - *Baseline forecast ~{int(r['baseline_pred'])} violations/week; "
                         f"event raises this materially.*")
    if not len(df):
        L.append("\n_No event-to-hotspot matches found for this window._")
    BRIEFINGS_MD.write_text("\n".join(L), encoding="utf-8")


def main():
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=AI["horizon_days"] - 1)
    zones = load_zones()

    if have_api():
        print("ANTHROPIC_API_KEY found — running LIVE agent (web search + reasoning).")
        events = fetch_events_live(start, end)
        mode = "live" if events else "offline"
        if not events:
            events = sample_events(start, end, zones)
    else:
        print("No ANTHROPIC_API_KEY — running OFFLINE sample mode "
              "(set the key to fetch real events with Claude).")
        events, mode = sample_events(start, end, zones), "offline"

    for ev in events:
        ev["source"] = mode
    EVENTS_JSON.write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")

    rows = match_events_to_zones(events, zones)
    if mode == "live" and rows:
        rows = assess_live(rows)
    for r in rows:
        r["source"] = mode

    out = pd.DataFrame(rows)
    keep = ["date", "weekday", "event_name", "event_type", "area", "expected_crowd",
            "junction_name", "police_station", "risk_level", "baseline_pred",
            "reasoning", "recommended_action", "lat", "lon", "source"]
    (out[keep] if len(out) else pd.DataFrame(columns=keep)).to_csv(FORECAST_CSV, index=False)
    write_briefings(rows, mode, start, end)

    print(f"\nMode: {mode.upper()}   window: {start} -> {end}")
    print(f"Events: {len(events)}   event-hotspot matches: {len(rows)}")
    if len(out):
        sev = (out["risk_level"] == "Severe").sum()
        print(f"Severe-risk zone-days: {sev}")
        print("\nSample (top 5):")
        print(out.head(5)[["date", "risk_level", "junction_name", "event_name"]].to_string(index=False))
    print(f"\nWrote ai_events.json, ai_event_forecast.csv, ai_briefings.md")


if __name__ == "__main__":
    main()
