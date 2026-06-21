# Gridlock — Parking Congestion Intelligence

**Problem:** *Poor visibility on parking-induced congestion.* On-street illegal
parking near commercial areas, metro stations and markets chokes carriageways
and intersections. Enforcement today is patrol-based and reactive, there is no
heatmap of violations vs. congestion impact, and zones are hard to prioritise.

**Gridlock** turns ~298k geotagged Bengaluru Traffic Police parking-violation
records into a complete **AI-driven parking-intelligence product** that closes the
enforcement loop end-to-end:

> **detect → score → explain → forecast → deploy → measure impact → check displacement → re-target**

1. **Detects illegal-parking hotspots** — ~150 m, patrol-able enforcement zones.
2. **Scores their congestion impact** — a tunable **Congestion Impact Score (CIS)**
   per zone (volume · severity · junction · vehicle · persistence).
3. **Explains why** — each hotspot tagged to its demand generator (metro/market/…).
4. **Forecasts** next week's hotspots (validated, beats baseline).
5. **Optimises enforcement** — a deployment roster with an ROI coverage curve.
6. **Proves it works** — before/after **Difference-in-Differences** + a
   **whack-a-mole** displacement check.
7. **Ships as a product** — dashboard, live app, **REST API**, **printable field
   briefings**, an **auto daily digest**, Docker, and a **test suite**.

Why it's hard to beat: not one clever feature, but the *whole loop* built from one
messy real dataset — with every estimate transparent, tunable, and honestly
caveated.

📣 **Presenting it?** See [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) — a timed ~3-min
click-path with exact narration, judge Q&A, and a failure fallback.

---

## How it works (pipeline)

| Step | Script | What it does | Why |
|------|--------|--------------|-----|
| 0 | `src/profile_data.py` | Measures the raw CSV (geometry, time, violation/vehicle mix, validation) — run once | Never trust the spec; measure the file before modelling |
| 1 | `src/pipeline.py` | Cleans GPS, parses timestamps→IST, reduces each ticket to its worst flow-blocking offence, drops non-parking offences, engineers severity/vehicle/junction/validation features → `data/violations_clean.parquet` | One clean, fast table every later step reuses |
| 2 | `src/hotspots.py` | Snaps points to a 150 m grid, scores each zone's CIS, ranks & tiers → `outputs/hotspots.csv` | Bounded, comparable, deployable zones + the core metric |
| 3 | `src/context.py` | **Demand-generator attribution** (metro/market/mall/…) → `outputs/zone_context.csv` | Explain *why* each hotspot exists |
| 5 | `src/build_map.py` | Folium map: severity-weighted heat layer + ranked zone markers + worst junctions → `outputs/parking_congestion_map.html` | Fills the "no heatmap" gap |
| 6 | `src/temporal.py` | Hour×weekday demand heatmap, violation/vehicle mix, per-zone patrol windows → `outputs/patrol_schedule.csv` + PNGs | Answers *when* to enforce → proactive |
| 7 | `src/forecast.py` | Gradient-boosted **7-day-ahead forecast** of each zone's load → `outputs/forecast_hotspots.csv` | Plan enforcement *before* congestion happens |
| 8 | `src/impact.py` | **Before/after enforcement impact** (Difference-in-Differences) → `outputs/impact_report.csv` | Prove whether a crackdown worked |
| 9 | `src/displacement.py` | **Whack-a-mole check** — did violations move to neighbours? → `outputs/displacement_report.csv` | Treat a block, or the whole corridor |
| 10 | `src/optimize.py` | **Patrol-allocation optimiser + ROI curve** → `outputs/deployment_plan.csv` | Turn the ranking into a deployment roster |
| 11 | `src/anomaly.py` | **Event/surge detection** (robust z-score) → `outputs/events.csv` | Pre-position for festivals/sales/matches |
| 12 | `src/ai_agent.py` | **AI event agent** — Claude + web search finds real upcoming events and reasons about hotspot risk → `outputs/ai_briefings.md` | Day-ahead, event-aware, *explained* forecast |
| 13 | `src/congestion.py` | **Live congestion feed** — fuses parking pressure with Google traffic → `outputs/congestion_live.json` | Real-time district congestion |
| 14 | `src/command_center.py` | **Live Congestion Command Centre** (pulsing, clickable districts) → `outputs/congestion_command.html` | The real-time ops drill-down |
| 15 | `src/dashboard.py` | Self-contained executive dashboard → `outputs/index.html` | One file an ops chief can open |
| — | `app.py` | **Live Streamlit app**, 8 tabs, adjustable CIS weights | Interactive, policy-tunable front-end |

### Product surfaces (it's a platform, not a script)

```bash
pip install -r requirements.txt
python run_all.py                              # 1. rebuild all artifacts (~70s)
uvicorn api:app                                # 2. REST API + auth        → :8000/docs
python -m http.server 8540 --directory outputs # 3. serve the web portal
streamlit run app.py                           # 4. interactive ops console → :8501
pytest                                         # 5. trust checks (14 tests)
```

Then open **`http://localhost:8540/portal.html`** — the role-gated tabbed portal.
(Windows: `demo_up.ps1` starts all servers and opens everything.)

### 🔐 Roles — admin vs viewer

The portal is a **tabbed** app (no endless scroll) behind a login, with two roles:

| Role | Login | Can do |
|------|-------|--------|
| **Admin** (the one head person) | `admin` / `admin@gridlock` | View **all analytics** + the **Data Ingestion** tab (dump fresh data, retrain the system) |
| **Viewer** | `viewer` / `viewer@gridlock` | View **all analytics** — read-only, no ingestion |

The boundary is **enforced by the API**, not just the UI: `POST /ingest/*`, `/rebuild`,
and `/dataset/reset` require an **admin** token (`/auth/login` → HMAC-signed token);
viewers and anonymous callers get `401`. Change credentials via env vars
`GRIDLOCK_ADMIN_PW`, `GRIDLOCK_VIEWER_PW`, and the signing key `GRIDLOCK_SECRET`.

| Surface | What it is | Who uses it |
|---------|------------|-------------|
| `outputs/index.html` | Executive dashboard (one file) | Leadership |
| `app.py` (Streamlit) | Live console — tune CIS weights, 8 tabs | Control room |
| `api.py` (FastAPI) | `/summary /hotspots /score /forecast /deployment /impact /events /context` | City systems / mobile app |
| `outputs/briefing_pack.pdf` | One printable page per top hotspot | Patrol commanders |
| `outputs/daily_digest.md` | Auto-generated morning brief | Ops desk |
| `outputs/parking_congestion_map.html` | Interactive heatmap | Everyone |

Or run the app in Docker (no Python setup needed):

```bash
docker compose up --build    # dashboard → http://localhost:8501
# REST API instead:
docker run -p 8000:8000 gridlock uvicorn api:app --host 0.0.0.0 --port 8000
```

Then open `outputs/index.html` (dashboard) and `outputs/parking_congestion_map.html` (map).

---

## Demand-generator context (`src/context.py`)

Every hotspot is tagged to the land use pulling the parking — metro/transit hub,
wholesale market, mall, hospital, education, religious, entertainment, commercial
street — from its address + junction text. Turns "where" into "**why**", and ties
hotspots to the "commercial areas, metro stations, events" in the problem
statement. (Commercial streets 38%, malls 13%, markets/metro/entertainment each a
distinct, addressable generator.)

## Enforcement optimiser + ROI (`src/optimize.py`)

A ranked list isn't a plan. We merge the 150 m cells into distinct deployable
**enforcement points**, score the impact a patrol captures in each point's peak
3-hour window, and greedily allocate a fixed number of patrol-shifts. The output
is a **deployment roster** plus a **coverage curve**: a small set of points hold a
large share of all **violations**, and patrolling them captures a meaningful chunk
after the window/capture discount. Whack-a-mole points are flagged to deploy as corridors.

## Event / surge detection (`src/anomaly.py`)

A robust z-score (median/MAD, spike-resistant) flags days a zone's load suddenly
surges — festivals, sales, matches, rallies (it catches 31 Dec and exhibition
spikes). Lets enforcement pre-position. *Caveat: surges partly reflect enforcement
drives, not only true demand.*

---

## 🚦 Live Congestion Command Centre (`src/congestion.py` + `src/command_center.py`)

A full-screen, real-time map (`outputs/congestion_command.html`) where each
police **district pulses by its current congestion** (green→amber→orange→red,
blinking when heavy/severe) and is **clickable**. Click a district → the map flies
to it and a panel lists the **"areas of attention for police"** — its worst
hotspots, each with a recommended action, AI event flags, and a one-click link to
**Google Maps live traffic** for that exact spot.

**Where the real congestion comes from (two levels, both honest):**
- **Google deep-links — work now, no key, no billing.** Every district & hotspot
  links to Google Maps centred there with the live Traffic layer on
  (`…/@lat,lng,16z/data=!5m1!1e1`) — real Google congestion, one click.
- **Quantitative travel-time index — optional, needs `GOOGLE_MAPS_API_KEY`.**
  `congestion.py` calls Google's Distance Matrix (`duration_in_traffic / duration`)
  per district to drive the blink with *measured* data; falls back to a realistic
  time-of-day simulation otherwise (so the demo always pulses).

```
congestion = 0.45 · (our parking pressure) + 0.55 · (live traffic index)
```

It runs **standalone** (just open the HTML — congestion is simulated client-side).
If `api.py` is running, the page polls `GET /congestion` for genuinely live values
(real Google indices when a key is set). To enable real indices:

```powershell
$env:GOOGLE_MAPS_API_KEY = "AIza..."   # Distance Matrix API enabled in Google Cloud
python src/congestion.py
```

## 🤖 AI event agent — the layer that makes it *truly* predictive (`src/ai_agent.py`)

Everything else is statistics — it knows where parking is *usually* bad. It can't
know that next Tuesday is a festival, that a match fills a stadium on Saturday, or
that a mall starts a sale on Friday. This module is an **internet-connected Claude
agent** (`claude-opus-4-8`) that closes that gap:

1. uses the **web_search tool** to find real upcoming demand drivers in the city
   for the next 7 days (festivals/holidays, venue events, rallies, mall/market sales);
2. maps each event to the hotspots it will overload (by area);
3. **reasons** about it — producing, per hotspot per day, an event-aware risk level,
   a plain-English *why*, and a concrete "prepare the day before" action for police.

```bash
# live mode (fetches real events + Claude reasoning):
setx ANTHROPIC_API_KEY "sk-ant-..."     # Windows (new shell after); or $env: for this shell
python src/ai_agent.py
```

**Graceful degradation:** with no `ANTHROPIC_API_KEY` (or no network), it falls back
to a clearly-labelled offline sample anchored to your real hotspots, so the
dashboard and demo never break. Outputs: `ai_briefings.md` (the readable
"tomorrow needs groundwork" brief), `ai_event_forecast.csv`, `ai_events.json`.
Surfaced in the dashboard, the app's **🤖 AI event forecast** tab, and the API's
`/ai-forecast` endpoint.

## Predictive model — forecast next week's hotspots (`src/forecast.py`)

We build a **zone × day panel** (zero-filled) and train a `HistGradientBoosting`
regressor to predict a zone's ticket count **7 days ahead**. Every feature
(lags, rolling means, weekday seasonality, static zone attributes) is computed
from history **≥7 days old**, so all 7 future days are forecast at once with no
leakage and no iterative error build-up.

- Validated on a **time-based 21-day holdout** vs. a strong *same-weekday-last-week*
  baseline → **beats baseline**, and predicts **which** zones will be hot with
  **per-zone weekly correlation r ≈ 0.85**.
- Honest read: citywide *daily* volume is dominated by unpredictable patrol
  scheduling; the **spatial** structure (which zones) is what's predictable — and
  that's exactly what enforcement planning needs.

## Enforcement-impact module — did the crackdown work? (`src/impact.py`)

Answers *"we enforced zone X from date D — did illegal parking actually fall, or
was the whole city quieter that month?"* using **Difference-in-Differences**:

```
expected_after = zone_before × (city_after / city_before)   # counterfactual
DiD change     = (zone_after − expected_after) / zone_before # <0 = real improvement
```

The rest of the city is the control, so a zone only counts as improved if it fell
**more than the city did**. A Welch t-test flags significance. `measure_impact()`
is the reusable production API — pass real crackdown dates for audit-grade numbers;
the auto change-point scan is a screen for the demo. *Caveat: observational data;
fewer tickets can mean better compliance or displacement, so pair with the forecast
residual.*

## Displacement / whack-a-mole check (`src/displacement.py`)

A drop at an enforced zone is only a real win if the cars don't reappear next
door. For each intervention we compare the treated zone's drop with the
DiD-adjusted change in zones within **400 m**:

```
displacement_% = neighbour DiD gain / treated drop
```

- **> 40%** → *Displacement* (whack-a-mole): treat the **corridor**, not the block.
- **≤ 10%** → *Genuine reduction* (often benefit even spills to neighbours).

On this data, most crackdowns produced genuine reductions, but a few high-profile
junctions (e.g. **Elite Junction, ~200% displacement**) simply pushed parking onto
adjacent streets — exactly the zones to saturate as a corridor.

## Live app (`app.py`)

`streamlit run app.py` opens an interactive console: drag the five CIS-weight
sliders and the map recolours and zones re-rank instantly; filter by police
station / volume; tabs for the **next-week forecast** and **enforcement impact**
(with the displacement check). The score is policy, not a black box.

## Deploy (`Dockerfile` / `docker-compose.yml`)

The image bundles the pre-built artifacts, so the app starts with no Python setup
and **without** the 105 MB raw CSV:

```bash
docker compose up --build            # → http://localhost:8501
```

To rebuild artifacts inside the container, mount the raw CSV and set
`GRIDLOCK_RAW_CSV` (see the commented block in `docker-compose.yml`), then
`docker compose run --rm gridlock python run_all.py`. The raw-CSV path is also
overridable natively via the same env var (defaults to the original Downloads
path).

---

## The Congestion Impact Score (CIS)

We have no live traffic-speed feed, so we **engineer a defensible proxy** for how
much each zone hurts traffic flow, from signals present in the data:

```
CIS = 100 × ( 0.35·volume + 0.25·severity + 0.20·junction
             + 0.10·vehicle + 0.10·persistence )
```

| Component | Meaning | Source signal |
|-----------|---------|---------------|
| **volume** | chronic pressure | log-scaled, false-positive-discounted ticket count |
| **severity** | how flow-blocking the offences are | `PARKING IN A MAIN ROAD`=1.0 … `NO PARKING`=0.45 |
| **junction** | intersection choke | share of tickets at a tagged junction |
| **vehicle** | road footprint of what's parked | bus/truck=1.0 … two-wheeler=0.3 |
| **persistence** | chronic vs one-off | spread across distinct days & hours |

Each component is min-max normalised across zones, so the score discriminates
between hotspots. **All weights and severities live in `config.py`** — tune them
to local policy without touching the code. Rejected tickets are down-weighted
(×0.25) so likely false positives don't inflate a zone.

---

## Key findings on this data

- **298,277** parking violations over ~5 months (Nov 2023 – Apr 2024).
- Violations are **highly concentrated** — a small fraction of 150 m zones
  account for most tickets, exactly the targeting opportunity the brief seeks.
- **7 Critical + 186 High** zones; worst are the Shivajinagar/Upparpet/City-Market
  commercial core (Safina Plaza, Elite, KR Market, Sagar Theatre junctions).
- **Bimodal timing:** morning 06–11 dominates commercial districts, but
  wholesale markets (KR Market) peak **23:00–02:00** — different shifts for
  different zones.
- `WRONG PARKING` + `NO PARKING` are 90% of offences; two-wheelers and cars
  dominate volume, but buses/trucks raise a zone's blocking severity.

## Honest caveat

Tickets are generated *by patrols*, so timing reflects enforcement effort as well
as true demand (note the sharp drop after 2pm = patrols off, not roads clear).
**Spatial** hotspots are robust; the temporal layer should be read as "when we
currently catch violations." Deployed live, the system closes this loop by
steering patrols toward under-watched, high-CIS zones.

## Outputs

```
outputs/
  index.html                      ← executive dashboard (start here)
  parking_congestion_map.html     ← interactive heatmap
  hotspots.csv                    ← all 1,239 zones ranked by CIS
  patrol_schedule.csv             ← per-zone recommended enforcement window
  forecast_hotspots.csv           ← zones ranked by predicted next-week load
  forecast_next_week.csv          ← zone × day forecast
  forecast_accuracy.png           ← holdout model-vs-actual
  zone_context.csv                ← demand-generator tag per zone
  context_summary.png             ← violations by land use
  deployment_plan.csv             ← optimised patrol roster (distinct points)
  optimize_coverage.png           ← enforcement ROI coverage curve
  events.csv                      ← detected event/surge days
  events_timeline.png             ← citywide daily load with spikes
  briefing_pack.pdf               ← printable one-page briefing per top zone
  daily_digest.md                 ← auto-generated daily ops brief
  ai_briefings.md                 ← AI event-aware day-ahead brief (with reasoning)
  ai_event_forecast.csv           ← per zone-day event risk + AI reasoning
  ai_events.json                  ← raw events the agent found (provenance)
  congestion_command.html         ← LIVE command centre (pulsing clickable districts)
  congestion_live.json            ← district congestion feed (parking + Google traffic)
  impact_report.csv               ← before/after DiD effect per zone + verdict
  impact_demo.png                 ← clearest measured reduction
  displacement_report.csv         ← whack-a-mole verdict per intervention
  displacement_demo.png           ← treated zone vs neighbours, before/after
  temporal_hour_dow.png           ← hour × weekday demand
  violation_mix.png               ← violation & vehicle breakdown
```
