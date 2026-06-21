"""
api.py  —  Gridlock REST API. Turns the intelligence into a SERVICE that the
city's existing systems (dispatch, control-room dashboards, a patrol mobile app)
can integrate with — not just a report.

    uvicorn api:app --reload          # docs at http://localhost:8000/docs

Endpoints
  GET  /summary                 headline KPIs (violations, zones, …)
  GET  /hotspots                ranked zones (filter by tier / station / limit)
  GET  /zone/{zone_id}          everything known about one zone
  POST /score                   re-rank zones with custom CIS weights (live policy)
  GET  /forecast                next-week predicted hotspots
  GET  /deployment              optimised patrol roster + ROI for K patrols
  POST /impact                  before/after DiD effect of an intervention
  GET  /events                  detected event/surge days
  GET  /context                 demand-generator breakdown

Everything is served from the pre-built artifacts, so responses are instant.
"""
import sys, os, threading, subprocess, time, hmac, hashlib, base64
from pathlib import Path
from functools import lru_cache
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Body, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT))
from config import OUT_DIR, CIS_WEIGHTS, AUTH, AUTH_SECRET

app = FastAPI(title="Gridlock — Parking Congestion Intelligence API",
              version="1.0",
              description="Detect illegal-parking hotspots, score their congestion "
                          "impact, and drive targeted enforcement.")

# the command-centre HTML polls /congestion cross-origin; allow it
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


# ---------------------------------------------------------------- auth (roles)
def make_token(role: str) -> str:
    msg = f"{role}.{int(time.time())}"
    sig = hmac.new(AUTH_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()[:20]
    return base64.urlsafe_b64encode(f"{msg}.{sig}".encode()).decode()


def parse_token(token: str):
    try:
        role, ts, sig = base64.urlsafe_b64decode(token.encode()).decode().split(".")
        good = hmac.new(AUTH_SECRET.encode(), f"{role}.{ts}".encode(),
                        hashlib.sha256).hexdigest()[:20]
        return role if hmac.compare_digest(sig, good) else None
    except Exception:
        return None


def current_role(authorization: str = Header(None)):
    if not authorization:
        return None
    return parse_token(authorization.split()[-1])


def require_admin(role: str = Depends(current_role)):
    """Gate for write endpoints — only the admin (head person) may ingest/retrain."""
    if role != "admin":
        raise HTTPException(401, "admin login required to dump data or retrain")
    return role


class Login(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
def login(c: Login):
    cfg = AUTH.get(c.username.strip().lower())
    if not cfg or c.password != cfg["password"]:
        raise HTTPException(401, "invalid credentials")
    role = c.username.strip().lower()
    return {"role": role, "can_ingest": cfg["can_ingest"], "token": make_token(role)}


@app.get("/auth/me")
def whoami(role: str = Depends(current_role)):
    return {"role": role, "can_ingest": bool(role and AUTH.get(role, {}).get("can_ingest"))}


def _csv(name):
    p = OUT_DIR / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


@lru_cache(maxsize=1)
def data():
    return {
        "hot": _csv("hotspots.csv"),
        "ctx": _csv("zone_context.csv"),
        "fc": _csv("forecast_hotspots.csv"),
        "plan": _csv("deployment_plan.csv"),
        "events": _csv("events.csv"),
        "disp": _csv("displacement_report.csv"),
    }


def clean(df):
    """JSON-safe records (NaN -> None)."""
    return df.replace({np.nan: None}).to_dict(orient="records")


# ---------------------------------------------------------------- models
class Weights(BaseModel):
    volume: float = Field(CIS_WEIGHTS["volume"], ge=0, le=1)
    severity: float = Field(CIS_WEIGHTS["severity"], ge=0, le=1)
    junction: float = Field(CIS_WEIGHTS["junction"], ge=0, le=1)
    vehicle: float = Field(CIS_WEIGHTS["vehicle"], ge=0, le=1)
    persistence: float = Field(CIS_WEIGHTS["persistence"], ge=0, le=1)
    limit: int = Field(20, ge=1, le=500)


class Intervention(BaseModel):
    zone: str
    date: str          # ISO date the enforcement started
    window_days: int = Field(28, ge=7, le=90)


# ---------------------------------------------------------------- endpoints
@app.get("/")
def root():
    return {"service": "Gridlock Parking Congestion Intelligence API",
            "docs": "/docs",
            "endpoints": ["/summary", "/hotspots", "/zone/{id}", "/score",
                          "/forecast", "/ai-forecast", "/congestion", "/deployment",
                          "/impact", "/events", "/context"]}


@app.get("/summary")
def summary():
    d = data()
    hot = d["hot"]
    if hot.empty:
        raise HTTPException(503, "Artifacts not built. Run run_all.py first.")
    return {
        "zones": int(len(hot)),
        "violations": int(hot["n_tickets"].sum()),
        "critical": int((hot["tier"] == "Critical").sum()),
        "high": int((hot["tier"] == "High").sum()),
        "top_zone": hot.iloc[0]["junction_name"],
    }


@app.get("/hotspots")
def hotspots(limit: int = Query(20, ge=1, le=500),
             tier: str | None = None, station: str | None = None):
    hot = data()["hot"]
    if hot.empty:
        raise HTTPException(503, "Artifacts not built.")
    df = hot
    if tier:
        df = df[df["tier"].str.lower() == tier.lower()]
    if station:
        df = df[df["police_station"].str.contains(station, case=False, na=False)]
    cols = ["rank", "CIS", "tier", "n_tickets", "junction_name", "police_station",
            "top_violation", "peak_hour", "lat", "lon"]
    return clean(df[cols].head(limit))


@app.get("/zone/{zone_id}")
def zone(zone_id: str):
    d = data()
    hot = d["hot"]
    row = hot[hot["zone"] == zone_id]
    if row.empty:
        raise HTTPException(404, f"zone {zone_id} not found")
    r = row.iloc[0].to_dict()
    out = {"zone": zone_id, "cis": r.get("CIS"), "tier": r.get("tier"),
           "junction_name": r.get("junction_name"), "police_station": r.get("police_station"),
           "n_tickets": r.get("n_tickets"), "peak_hour": r.get("peak_hour"),
           "top_violation": r.get("top_violation"), "lat": r.get("lat"), "lon": r.get("lon")}
    for name, key, fields in [
        ("forecast", "fc", ["pred_week"]),
        ("context", "ctx", ["context", "generator_kw"]),
    ]:
        df = d[key]
        if not df.empty and zone_id in set(df["zone"]):
            sub = df[df["zone"] == zone_id].iloc[0]
            out[name] = {f: (None if pd.isna(sub.get(f)) else sub.get(f)) for f in fields if f in df.columns}
    disp = d["disp"]
    if not disp.empty and zone_id in set(disp["zone"]):
        out["displacement"] = clean(disp[disp["zone"] == zone_id])[0]
    return out


@app.post("/score")
def score(w: Weights):
    """Re-rank zones with custom CIS weights — exposes policy as a live knob."""
    hot = data()["hot"]
    if hot.empty:
        raise HTTPException(503, "Artifacts not built.")
    comp = ["c_volume", "c_severity", "c_junction", "c_vehicle", "c_persistence"]
    if not all(c in hot.columns for c in comp):
        raise HTTPException(500, "component columns missing in hotspots.csv")
    tot = w.volume + w.severity + w.junction + w.vehicle + w.persistence or 1.0
    s = (w.volume * hot["c_volume"] + w.severity * hot["c_severity"] +
         w.junction * hot["c_junction"] + w.vehicle * hot["c_vehicle"] +
         w.persistence * hot["c_persistence"]) / tot * 100
    out = hot.assign(CIS_custom=s.round(2)).sort_values("CIS_custom", ascending=False)
    out = out.head(w.limit)
    cols = ["zone", "CIS_custom", "junction_name", "police_station", "n_tickets",
            "top_violation", "lat", "lon"]
    return {"weights": w.model_dump(exclude={"limit"}), "zones": clean(out[cols])}


@app.get("/forecast")
def forecast(limit: int = Query(20, ge=1, le=500)):
    fc = data()["fc"]
    if fc.empty:
        raise HTTPException(503, "forecast not built (run src/forecast.py)")
    cols = [c for c in ["rank", "pred_week", "junction_name", "police_station", "lat", "lon"]
            if c in fc.columns]
    return clean(fc[cols].head(limit))


@app.get("/deployment")
def deployment(patrols: int = Query(25, ge=1, le=200)):
    plan = data()["plan"]
    if plan.empty:
        raise HTTPException(503, "deployment plan not built (run src/optimize.py)")
    roster = plan.head(patrols)
    located = float(roster["cum_located_%"].iloc[-1])
    captured = float(roster["cum_captured_%"].iloc[-1])
    total_v = int(plan["violations"].sum())
    cols = ["priority", "junction_name", "police_station", "window", "busiest_dow",
            "violations", "corridor", "lat", "lon"]
    return {"patrols": patrols,
            "violations_located_pct": round(located, 1),
            "violations_captured_pct": round(captured, 1),
            "violations_addressed": int(total_v * captured / 100),
            "roster": clean(roster[cols])}


@app.post("/impact")
def impact(iv: Intervention):
    """Before/after DiD effect of an enforcement intervention at a zone."""
    try:
        from src.impact import daily_panel, measure_impact
    except Exception as e:
        raise HTTPException(500, f"impact module unavailable: {e}")
    lab = OUT_DIR / "violations_labelled.parquet"
    if not lab.exists():
        raise HTTPException(503, "labelled data not built.")
    df = pd.read_parquet(lab)
    panel, city = daily_panel(df)
    if iv.zone not in set(panel["zone"]):
        raise HTTPException(404, f"zone {iv.zone} not found")
    res = measure_impact(panel, city, iv.zone, iv.date, window=iv.window_days)
    if res is None:
        raise HTTPException(422, "not enough data around that date for this zone")
    return res


@app.get("/events")
def events(limit: int = Query(30, ge=1, le=500)):
    ev = data()["events"]
    if ev.empty:
        raise HTTPException(503, "events not built (run src/anomaly.py)")
    return clean(ev.head(limit))


# ====================================================================== INGEST
from src import ingest

REBUILD = {"running": False, "step": 0, "total": 1, "log": [], "done": False,
           "error": None, "before": {}, "after": {}, "started": None}


def _snapshot():
    try:
        hot = pd.read_csv(OUT_DIR / "hotspots.csv")
        return {"zones": int(len(hot)), "violations": int(hot["n_tickets"].sum())}
    except Exception:
        return {}


def _rebuild_worker():
    try:
        from run_all import STEPS
        REBUILD.update(running=True, done=False, error=None, step=0,
                       total=len(STEPS), log=["Combining base + ingested data…"],
                       before=_snapshot(), after={}, started=time.time())
        combined = ingest.build_combined()
        env = os.environ.copy()
        env["GRIDLOCK_RAW_CSV"] = str(combined)
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen([sys.executable, str(ROOT / "run_all.py")], cwd=str(ROOT),
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1)
        for line in proc.stdout:
            line = line.rstrip()
            if line.startswith(">>"):
                REBUILD["step"] += 1
                REBUILD["log"].append(line[3:].strip())
            elif "ALL DONE" in line:
                REBUILD["log"].append(line.strip())
        proc.wait()
        data.cache_clear()                       # serve fresh artifacts
        try:
            from src import chat as _chat
            _chat.build_context.cache_clear()
        except Exception:
            pass
        REBUILD["after"] = _snapshot()
        if proc.returncode != 0:
            REBUILD["error"] = f"rebuild exited {proc.returncode}"
    except Exception as e:
        REBUILD["error"] = f"{type(e).__name__}: {e}"
    finally:
        REBUILD["running"] = False
        REBUILD["done"] = True


@app.get("/dataset/stats")
def dataset_stats():
    s = ingest.dataset_stats()
    s["base_note"] = "original 298k-row dataset (immutable)"
    return s


@app.post("/ingest/file")
async def ingest_file(file: UploadFile = File(...), _: str = Depends(require_admin)):
    """Upload a CSV / XLSX / JSON of fresh violations; validate + append."""
    raw = await file.read()
    try:
        df = ingest.read_any(file.filename or "upload.csv", raw)
    except Exception as e:
        raise HTTPException(400, f"could not parse file: {e}")
    return ingest.ingest_frame(df)


@app.post("/ingest/records")
def ingest_records(records: list[dict] = Body(...), _: str = Depends(require_admin)):
    """Append a JSON array of violation records."""
    if not records:
        raise HTTPException(400, "empty records array")
    return ingest.ingest_frame(pd.DataFrame(records))


@app.post("/ingest/record")
def ingest_record(record: dict = Body(...), _: str = Depends(require_admin)):
    """Append a single violation (e.g. a map-pinned field report)."""
    return ingest.ingest_frame(pd.DataFrame([record]))


@app.post("/dataset/reset")
def dataset_reset(_: str = Depends(require_admin)):
    ingest.reset_ingested()
    return {"status": "ingested data cleared; base dataset untouched"}


@app.post("/rebuild")
def rebuild(_: str = Depends(require_admin)):
    """Retrain the whole system on base + ingested data (runs in background)."""
    if REBUILD["running"]:
        raise HTTPException(409, "a rebuild is already running")
    threading.Thread(target=_rebuild_worker, daemon=True).start()
    time.sleep(0.3)
    return {"status": "rebuild started"}


@app.get("/rebuild/status")
def rebuild_status():
    r = dict(REBUILD)
    r["elapsed"] = round(time.time() - r["started"], 1) if r.get("started") else 0
    return r


@app.get("/context")
def context():
    ctx = data()["ctx"]
    if ctx.empty:
        raise HTTPException(503, "context not built (run src/context.py)")
    by = (ctx.groupby("context")
            .agg(zones=("zone", "size"), tickets=("n_tickets", "sum"))
            .sort_values("tickets", ascending=False).reset_index())
    return clean(by)


@app.get("/congestion")
def congestion():
    """Live district congestion feed for the command centre — fuses parking
    pressure with real Google travel-time indices (when GOOGLE_MAPS_API_KEY is
    set) or a time-of-day simulation otherwise."""
    try:
        from src.congestion import compute_districts
        return compute_districts()
    except Exception as e:
        raise HTTPException(503, f"congestion feed unavailable: {e}")


class ChatQ(BaseModel):
    question: str


@app.post("/chat")
def chat_endpoint(c: ChatQ):
    """Officer Q&A — quantitative, plain-language answers grounded in the data.
    Uses Claude when ANTHROPIC_API_KEY is set, else deterministic rules."""
    from src import chat as chatmod
    ctx = chatmod.build_context()
    if not ctx:
        raise HTTPException(503, "analytics not built (run run_all.py)")
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return {"answer": chatmod.answer_ai(c.question, ctx), "source": "ai"}
        except Exception:
            pass
    return {"answer": chatmod.answer_rules(c.question, ctx), "source": "rules"}


@app.get("/ai-forecast")
def ai_forecast(risk: str | None = None):
    """Event-aware, AI-reasoned congestion risk for the coming week
    (festivals/matches/sales/rallies mapped to hotspots)."""
    df = _csv("ai_event_forecast.csv")
    if df.empty:
        raise HTTPException(503, "AI forecast not built (run src/ai_agent.py)")
    if risk:
        df = df[df["risk_level"].str.lower() == risk.lower()]
    mode = df["source"].iloc[0] if "source" in df.columns and len(df) else "offline"
    return {"mode": mode, "count": int(len(df)), "risks": clean(df)}
