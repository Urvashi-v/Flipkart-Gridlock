"""
congestion.py  —  builds the LIVE CONGESTION feed for the command centre.

A "district" is a police jurisdiction. For each, we combine:
  * structural pressure  — its illegal-parking violation volume (from hotspots), and
  * live road congestion — a real-time travel-time index from Google's Distance
    Matrix API (`duration_in_traffic / duration`) when GOOGLE_MAPS_API_KEY is set;
    otherwise a realistic time-of-day simulation so the demo still pulses.

Every district drills down to its hotspots ("areas of attention for police"),
each carrying a recommended action and a Google Maps **live-traffic deep-link**
(works with no API key at all — `.../@lat,lng,16z/data=!5m1!1e1`).

`compute_districts()` is imported by api.py (the /congestion endpoint) so the
command centre can poll for genuinely live values when the API is running.

Output: outputs/congestion_live.json
"""
import os, sys, json, math
from datetime import datetime
from pathlib import Path
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR, CONGESTION

LIVE_JSON = OUT_DIR / "congestion_live.json"


def google_link(lat, lon, zoom=16):
    """Deep-link to Google Maps centred here with the live TRAFFIC layer on."""
    return f"https://www.google.com/maps/@{lat:.5f},{lon:.5f},{zoom}z/data=!5m1!1e1"


def _action(context, violation):
    c = str(context)
    if "Market" in c:   return "Coordinate market loading bays; tow on approaches in peak window."
    if "Metro" in c or "Transit" in c: return "Clear station approaches; push last-mile parking to lots."
    if "Mall" in c or "Shopping" in c: return "Engage mall valet; keep feeder roads clear."
    if "Hospital" in c: return "Protect emergency lanes; mark visitor drop-off."
    if "Religious" in c: return "Manage event/procession parking; pre-mark no-parking."
    if "Entertainment" in c: return "Stagger show-time arrivals; deploy at peak hours."
    return "Station a unit in the peak window; tow repeat offenders."


def get_google_tti(origin, dest, key):
    """Travel-time index = in-traffic / free-flow for one segment (or None)."""
    try:
        import requests
        r = requests.get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            params={"origins": f"{origin[0]},{origin[1]}",
                    "destinations": f"{dest[0]},{dest[1]}",
                    "departure_time": "now", "key": key},
            timeout=8)
        el = r.json()["rows"][0]["elements"][0]
        base = el["duration"]["value"]
        live = el.get("duration_in_traffic", el["duration"])["value"]
        return round(live / base, 3) if base else None
    except Exception:
        return None


def _farthest_pair(pts):
    if len(pts) < 2:
        a = pts[0]; return a, (a[0] + 0.01, a[1] + 0.01)
    best, bi, bj = -1, 0, 1
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = (pts[i][0]-pts[j][0])**2 + (pts[i][1]-pts[j][1])**2
            if d > best:
                best, bi, bj = d, i, j
    return pts[bi], pts[bj]


def build_districts():
    hot = pd.read_csv(OUT_DIR / "hotspots.csv")
    ctxp = OUT_DIR / "zone_context.csv"
    if ctxp.exists():
        hot = hot.merge(pd.read_csv(ctxp)[["zone", "context"]], on="zone", how="left")
    hot["context"] = hot.get("context", "Mixed / Other").fillna("Mixed / Other")
    hot["n_tickets"] = hot.get("n_tickets", 1).fillna(0)

    ai = OUT_DIR / "ai_event_forecast.csv"
    ai_df = pd.read_csv(ai) if ai.exists() else pd.DataFrame()

    rows = []
    for ps, g in hot.groupby("police_station"):
        g = g.sort_values("n_tickets", ascending=False)
        hs = []
        for _, r in g.head(CONGESTION["hotspots_per_district"]).iterrows():
            hs.append({
                "junction": str(r["junction_name"]),
                "lat": round(float(r["lat"]), 6), "lon": round(float(r["lon"]), 6),
                "tickets": int(r["n_tickets"]),
                "cis": round(float(r.get("CIS", 0)), 1),
                "violation": str(r.get("top_violation", "")),
                "context": str(r["context"]),
                "action": _action(r["context"], r.get("top_violation", "")),
                "gmaps": google_link(float(r["lat"]), float(r["lon"])),
            })
        evs = []
        if len(ai_df):
            sub = ai_df[ai_df["police_station"] == ps]
            for _, e in sub.head(4).iterrows():
                evs.append({"date": e["date"], "event": e["event_name"],
                            "risk": e["risk_level"], "why": e["reasoning"],
                            "action": e["recommended_action"]})
        rows.append({
            "district": str(ps),
            "lat": round(float(g["lat"].mean()), 6),
            "lon": round(float(g["lon"].mean()), 6),
            "n_hotspots": int(len(g)),
            "violations": int(g["n_tickets"].sum()),
            "top_violation": str(g["primary_violation"].mode().iloc[0]) if "primary_violation" in g else
                             (str(g["top_violation"].mode().iloc[0]) if "top_violation" in g else ""),
            "gmaps": google_link(float(g["lat"].mean()), float(g["lon"].mean()), 14),
            "hotspots": hs, "events": evs,
            "_corridor": _farthest_pair([(h["lat"], h["lon"]) for h in hs]),
        })

    dd = pd.DataFrame(rows).sort_values("violations", ascending=False) \
        .head(CONGESTION["n_districts"]).reset_index(drop=True)
    mx = dd["violations"].max() or 1.0
    dd["pressure"] = (dd["violations"] / mx).round(3)
    return dd.to_dict(orient="records")


def compute_districts(use_google=None):
    """District feed; adds a live Google travel-time index when a key is available."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    use_google = (key is not None) if use_google is None else (use_google and key)
    districts = build_districts()
    sw = CONGESTION["structural_weight"]
    for d in districts:
        tti = None
        if use_google:
            (o, dst) = d["_corridor"]
            tti = get_google_tti(o, dst, key)
        d.pop("_corridor", None)
        d["tti"] = tti                                  # None => client simulates
        if tti is not None:
            live = max(0.0, min(1.0, (tti - 1.0) / 1.0))
            d["congestion"] = round(100 * (sw * d["pressure"] + (1 - sw) * live))
        else:
            d["congestion"] = None
    return {"generated": datetime.now().isoformat(timespec="seconds"),
            "source": "google" if use_google else "simulated",
            "districts": districts}


def main():
    feed = compute_districts()
    LIVE_JSON.write_text(json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8")
    n = len(feed["districts"])
    blink = sum(1 for d in feed["districts"] if (d["congestion"] or 0) >= 55)
    print(f"Congestion feed: {n} districts  ·  source: {feed['source'].upper()}")
    if feed["source"] == "simulated":
        print("  (set GOOGLE_MAPS_API_KEY for real travel-time indices; the command "
              "centre simulates live congestion client-side regardless)")
    print(f"  districts currently heavy/severe: {blink}")
    print("  top 5 districts by parking pressure:")
    for d in feed["districts"][:5]:
        print(f"    {d['district']:22s} pressure {d['pressure']:.2f}  "
              f"hotspots {d['n_hotspots']:2d}  violations {d['violations']:,}")
    print(f"\nWrote {LIVE_JSON}")


if __name__ == "__main__":
    main()
