# 🎤 Gridlock — Live Demo Script

A tight **~3-minute** run (2-min core + buffer) for judges. Every number below is
real output from this build. Practise once out loud; it should feel conversational,
not read.

---

## ⏱️ At-a-glance timing

| # | Beat | Surface | Time | The one line that lands |
|---|------|---------|------|--------------------------|
| 0 | Pre-flight | — | before | (have everything open) |
| 1 | The hook | dashboard top | 0:00–0:25 | "298k tickets, and nobody knows which spots actually matter" |
| 2 | Where + why | dashboard / map | 0:25–0:50 | "a fraction of spots cause most of the problem" |
| 3 | It's tunable, not a black box | Streamlit app | 0:50–1:20 | "the score is policy you can dial" |
| 4 | The differentiators | app tabs | 1:20–2:10 | "we don't just move the problem — we prove it" |
| 5 | It's a product | API + PDF + digest | 2:10–2:40 | "a commander prints this; a dev calls this" |
| 6 | Close | — | 2:40–3:00 | "the whole loop, from one real dataset" |

---

## 0. Pre-flight (do this BEFORE you present)

Open these in browser tabs / terminals so there's zero loading on stage:

```bash
python run_all.py                       # ensure artifacts are fresh
streamlit run app.py                    # Tab A → http://localhost:8501
uvicorn api:app --port 8000             # Tab B → http://localhost:8000/docs
```
- **Tab A:** `outputs/index.html` (the dashboard) — scrolled to top
- **Tab B:** the Streamlit app (`localhost:8501`)
- **Tab C:** the API docs (`localhost:8000/docs`)
- **Open:** `outputs/briefing_pack.pdf` (page 1) and `outputs/daily_digest.md`
- Terminal ready with `pytest` typed but not run (optional flourish)

---

## 0.5 The showstopper open  (optional, 0:00–0:20)  · *congestion_command.html*

**[DO]** Open `outputs/congestion_command.html`. Let the districts pulse. Click the
biggest one (Upparpet).

**[SAY]**
> "This is our live command centre. Every district pulses with its real-time
> congestion. The control room sees Upparpet going red — clicks it — and instantly
> gets the *areas of attention*: which junctions, what to do, and a one-click jump
> to **Google's live traffic** for that exact spot. And see these? AI event flags —
> there's a festival there this week. That's the whole product in one screen."

*(Then go to the dashboard for the numbers.)*

## 1. The hook  (0:00–0:25)  · *dashboard top*

**[DO]** Show the dashboard header KPIs.

**[SAY]**
> "Bengaluru's traffic police write thousands of illegal-parking tickets a month —
> but they have no idea which spots actually choke traffic. We turned **298,000**
> of their real tickets into this. Every hotspot gets a **Congestion Impact Score**
> — a transparent blend of volume, how flow-blocking the violations are, junction
> proximity, vehicle size, and how chronic it is. Today enforcement is reactive
> patrols. We make it targeted."

## 2. Where + why  (0:25–0:50)  · *dashboard scroll / heatmap*

**[DO]** Show the **top hotspots table** + the deployment ROI curve; then click
**"Open interactive congestion heatmap."**

**[SAY]**
> "The violations are wildly concentrated: a **small fraction of 150 m zones holds
> most of the citywide total.** That's the targeting opportunity. Each hotspot is
> also tagged to *why* it exists — market, metro, mall — so you know what to fix,
> not just where."

## 3. Not a black box  (0:50–1:20)  · *Streamlit app, Tab B*

**[DO]** On the **Hotspot map** tab, drag the **Severity** weight up and **Volume**
down. Watch zones recolour / re-rank.

**[SAY]**
> "The priority score is *policy*, not a black box. Watch — if leadership says
> 'I care about main-road blockages, not bike volume,' I just dial it, and the whole
> city re-ranks live. Same engine, exposed as a knob the city actually controls."

## 4. The differentiators  (1:20–2:10)  · *app tabs*

**[DO]** Click **Deployment** tab → show the ROI curve + roster.

**[SAY]**
> "A ranked list isn't a plan. Our optimiser says: with **25 patrol-shifts a day**,
> hit *these* points — that's a large share of **all citywide violations** in 25 of
> 845 distinct spots, with the best window and day for each."

**[DO]** Click **Impact** tab → scroll to the displacement section.

**[SAY]**
> "And here's what no one else does. We measured real crackdowns with
> difference-in-differences — this one cut violations **91%, p=0.0002.** But we also
> check **displacement**: enforce Elite Junction in isolation and **200% of it pops
> up next door.** So we flag it: treat the *corridor*, not the block. We don't just
> move the problem — we prove whether we solved it."

**[DO]** *(optional, if time)* Flick to **Forecast** and **Events** tabs.

**[SAY]**
> "We forecast next week's hotspots — beats the seasonal baseline — and we flag
> event surges. It even caught **New Year's Eve.**"

## 4b. The AI agent — not just ML  (optional, +0:20)  · *app → 🤖 AI event forecast tab*

**[DO]** Open the **AI event forecast** tab (or show `outputs/ai_briefings.md`).

**[SAY]**
> "All of that was machine learning — it knows where parking is *usually* bad. This
> is the AI layer: an internet-connected Claude agent that searches for what's
> actually happening this week — a festival, a match, a mall sale — and reasons
> about which hotspots it'll choke. So the night before, the control room already
> knows: *tomorrow there's a procession near KR Market — pre-deploy.* That's the
> difference between a dashboard and an intelligence system."

> *(If presenting offline, note: "running in offline-sample mode here; with an API
> key it pulls live events via web search.")*

## 5. It's a product, not a notebook  (2:10–2:40)  · *PDF + API*

**[DO]** Show **briefing_pack.pdf** page 1. Then flick to **Tab C** (`/docs`) and
run `GET /summary` (or `POST /score`).

**[SAY]**
> "This is built to deploy. A patrol commander prints **this one-pager** per
> hotspot — where, when, why, and the action. The ops desk gets an **auto daily
> digest**. And every bit is a **REST API** the city's dispatch can call. Plus a
> **test suite** — twelve tests, all green."

## 6. Close  (2:40–3:00)

**[SAY]**
> "So: detect, **score the impact**, explain, forecast, deploy, **measure impact,
> check displacement**, re-target — a closed loop, built from one messy real
> dataset, every number transparent and tunable. That's Gridlock."

---

## 🛡️ Judge Q&A — crisp answers

- **"How is the Congestion Impact Score computed?"**
  "A transparent weighted blend per zone — volume, violation severity (how
  flow-blocking), junction proximity, vehicle size, and persistence — each
  normalised 0–1, weights in `config.CIS_WEIGHTS`. No black box; the weights are a
  live knob in the app."

- **"Isn't this just enforcement data, not true demand?"**
  "Exactly — and we say so. Spatial hotspots are robust; the *timing* reflects
  patrol effort. That's why the product's value is closing the loop: deploy to
  high-impact under-watched zones, then the data corrects itself."

- **"Why a grid and not clustering?"**
  "We tried DBSCAN first — density chaining merged whole corridors into a 1.8 km
  blob no patrol could action. A 150 m grid gives bounded, comparable, deployable
  zones."

- **"How accurate is the forecast?"**
  "It beats a same-weekday-last-week baseline and predicts *which* zones are hot at
  per-zone weekly correlation r ≈ 0.85 — the spatial signal enforcement needs."

- **"Does it work for another city?"**
  "Yes — point `GRIDLOCK_RAW_CSV` at new data, tune `config.py`. Nothing is
  hard-coded to Bengaluru except the bounding box."

- **"What's next / what's missing?"**
  "Fuse a live traffic-speed feed to replace our proxy with measured delay, and an
  intervention log so the impact module runs on real crackdown dates."

---

## 🧯 If something breaks on stage
- **App won't load?** Fall back to `outputs/index.html` (static dashboard) — same story, no server.
- **API hiccups?** Show `outputs/daily_digest.md` and `briefing_pack.pdf` instead — they're files.
- **Map slow?** Talk over it using the Pareto chart; it doesn't need the map.
- **Worst case:** the dashboard PDF/HTML alone tells the entire story offline.

---

## ✅ One-breath version (if you only get 30 seconds)
> "298k real parking tickets → the hotspots that actually choke Bengaluru, scored
> and ranked. A handful of spots drive most of it. We rank them, forecast them,
> optimise patrols to them, prove enforcement worked with difference-in-differences,
> and flag when it just moved next door — shipped as a role-gated portal, an API,
> and printable field briefings. That's Gridlock."
