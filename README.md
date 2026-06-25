# GRIDLOCK — AI-Powered Parking Congestion Intelligence System

**Real-Time Hotspot Detection, Predictive Enforcement & Causal Impact Measurement Across Bengaluru's Urban Road Network**

> *298,277 real Bengaluru Traffic Police parking-violation records → a live AI command centre that detects hotspots, predicts them before they form, optimises patrol deployment, and causally proves whether enforcement actually reduced congestion.*

**Live Demo:** [https://gridlock-qfse.onrender.com](https://gridlock-qfse.onrender.com)

---

## Quick Overview

GRIDLOCK is a full-stack AI platform that closes the entire enforcement loop:

```
DETECT → SCORE → EXPLAIN → FORECAST → DEPLOY → MEASURE → CHECK DISPLACEMENT → RE-TARGET
```

It ships as a **web dashboard** (10 interactive sections + chatbot), a **REST API** (13 endpoints), a **Streamlit app** (interactive weight sliders), **printable PDF briefings**, and an **automated daily digest** — all built from one real police dataset.

---

## How to Run This Project

There are two ways to get the project: **clone from GitHub** or **use a downloaded copy** (ZIP/folder). Both work identically. Follow the path that matches your situation.

---

### PATH A: Running from GitHub (Clone)

This is the recommended way. You get the full git history and can pull updates.

#### Step 1: Open a terminal

- **Windows:** Open **PowerShell** or **Command Prompt**. You can do this by pressing `Win + R`, typing `powershell`, and hitting Enter. Or open VS Code and use its built-in terminal (`Ctrl + `` ` ``).
- **macOS:** Open **Terminal** (search "Terminal" in Spotlight).
- **Linux:** Open your terminal emulator.

#### Step 2: Navigate to where you want the project

Choose a folder where you want the project to live. For example:

```bash
# Windows — go to your Desktop:
cd C:\Users\YourName\Desktop

# macOS / Linux — go to your home directory:
cd ~
```

#### Step 3: Clone the repository

```bash
git clone https://github.com/Urvashi-v/Flipkart-Gridlock.git
```

You'll see output like:
```
Cloning into 'Flipkart-Gridlock'...
remote: Enumerating objects: ...
Receiving objects: 100% ...
```

This creates a folder called `Flipkart-Gridlock` with all the project files.

#### Step 4: Enter the project folder

```bash
cd Flipkart-Gridlock
```

Now skip ahead to **[Setting Up the Environment](#setting-up-the-environment)** below.

---

### PATH B: Running from Downloaded Source Code (ZIP / Shared Folder)

If someone gave you the project as a ZIP file or a folder (not through GitHub):

#### Step 1: Extract the ZIP (if applicable)

- **Windows:** Right-click the ZIP → **"Extract All..."** → choose a location (e.g., Desktop) → click **Extract**.
- **macOS:** Double-click the ZIP. It extracts automatically.
- **Linux:** `unzip Flipkart-Gridlock.zip`

You should now have a folder with files like `api.py`, `config.py`, `run_all.py`, `requirements.txt`, and subfolders `src/`, `outputs/`, `tests/`.

#### Step 2: Open a terminal inside the project folder

**Option A — VS Code (easiest):**
1. Open VS Code.
2. Go to **File → Open Folder** → select the project folder (the one containing `api.py`).
3. Open the terminal: **Terminal → New Terminal** (or press `Ctrl + `` ` ``).
4. You're now inside the project folder. Confirm by running `ls` (macOS/Linux) or `dir` (Windows) — you should see `api.py`, `src/`, `outputs/`, etc.

**Option B — Manual navigation:**
```bash
# Windows (replace the path with where you extracted it):
cd C:\Users\YourName\Desktop\Flipkart-Gridlock

# macOS / Linux:
cd ~/Desktop/Flipkart-Gridlock
```

Now continue to the next section.

---

### Setting Up the Environment

These steps are the same whether you cloned from GitHub or downloaded the folder.

#### Step 1: Verify Python is installed

```bash
python --version
```

You should see something like `Python 3.12.3`. **You need Python 3.10 or higher.**

If you see an error ("python is not recognized"):
- **Windows:** Download Python from [python.org/downloads](https://www.python.org/downloads/). During installation, **check the box that says "Add Python to PATH"**. Then restart your terminal and try again.
- **macOS:** Run `python3 --version` instead. If that works, use `python3` instead of `python` in all commands below.
- **Linux:** `sudo apt install python3 python3-venv python3-pip` (Ubuntu/Debian) or equivalent for your distro.

#### Step 2: Create a virtual environment

A virtual environment keeps this project's packages separate from your system Python. This prevents conflicts.

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks the activation script with a red error about "execution policy":
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt / cmd):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**How to know it worked:** You'll see `(.venv)` at the start of your terminal prompt, like this:
```
(.venv) C:\Users\YourName\Desktop\Flipkart-Gridlock>
```

> **Important:** Every time you open a new terminal to work on this project, you need to activate the virtual environment again using the same activate command above.

#### Step 3: Install all dependencies

```bash
pip install -r requirements.txt
```

This downloads and installs all the libraries the project needs: pandas, numpy, scikit-learn, fastapi, folium, streamlit, etc.

**Expected time:** 1–3 minutes depending on your internet speed.

**Expected output:** A lot of "Downloading..." and "Installing..." lines, ending with:
```
Successfully installed ... (long list of packages)
```

If you see errors:
- Make sure your virtual environment is activated (you see `(.venv)` in the prompt).
- Try: `pip install --upgrade pip` first, then re-run the install command.
- On Windows, if a package fails to compile, make sure you have Python 3.10–3.12 (not 3.13 or 3.14).

---

### Starting the Application

#### The simple way: one command, one server

```bash
uvicorn api:app --port 8000
```

You'll see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Now open your browser and go to:

### **http://localhost:8000**

That's it. The entire dashboard loads — all 10 sections, the parking congestion map with the red enforcement-zone markers, the live command centre, analytics, the chatbot, data ingestion — everything works.

> **No login required.** The system has open access. Just open the URL and explore.

#### To stop the server

Press `Ctrl + C` in the terminal where the server is running.

---

### Running the Full Experience (Dashboard + Streamlit + API Docs)

If you want to see everything the project offers, open **two terminals** (both inside the project folder, both with the virtual environment activated):

**Terminal 1 — the main server (API + Dashboard):**
```bash
uvicorn api:app --port 8000
```

**Terminal 2 — the Streamlit interactive app:**
```bash
streamlit run app.py
```

Now open these in your browser:

| URL | What it is |
|---|---|
| **http://localhost:8000** | Main dashboard — 10 tabs, chatbot, maps, analytics, data ingestion |
| **http://localhost:8501** | Streamlit app — drag the CIS weight sliders and watch zones re-rank live |
| **http://localhost:8000/docs** | REST API documentation (Swagger UI) — try every endpoint interactively |

#### Windows shortcut: one-click launch

If you're on Windows, there's a script that starts everything and opens all surfaces automatically:

```powershell
powershell -ExecutionPolicy Bypass -File demo_up.ps1
```

This opens: the dashboard, the command centre map, the briefing PDF, the daily digest, the Streamlit app, and the API docs — all at once.

---

### What You'll See When You Open the Dashboard

The dashboard has a **dark sidebar on the left** with 10 sections. Here's what each one shows:

| Sidebar Section | What's Inside |
|---|---|
| **Overview** | City-wide snapshot: 4 metric cards, demand-by-hour chart (24 bars), top hotspots ranking, demand generators. **Hover any bar** for exact numbers. |
| **Hotspots** | The core intelligence: a **filterable table of 1,254 zones** (filter by severity tier, police station, search text, or minimum CIS score). Plus: busiest police stations, violations by tier, top violation types. |
| **Parking Map** | A full Folium map embedded in the dashboard: purple/blue heat layer showing violation density + **200 red circle markers** (the enforcement zones, sized by violation volume). Toggle layers with the control panel in the top-right. Click any red dot for its full breakdown. |
| **Command Centre** | A real-time ops map: 24 police districts **pulse and blink** by congestion level (green → amber → red). **Click any district** → it zooms in and shows its worst junctions with recommended actions and Google Maps traffic links. |
| **Forecast & AI** | The 7-day-ahead ML prediction + the AI event agent's flags for upcoming festivals, matches, and sales with plain-English reasoning about which hotspots they'll overload. |
| **Deployment** | An optimised patrol roster: exactly where, when, and which day to deploy. A coverage curve shows that 25 patrol-shifts can intercept ~48% of all citywide violations. |
| **Impact** | Causal proof: Difference-in-Differences analysis showing whether enforcement crackdowns actually reduced violations vs. the city-wide trend. One measured intervention: **91% reduction, p = 0.0002**. |
| **Events** | Detected surge days — festivals, flash sales, cricket matches — with a citywide timeline chart. |
| **Analytics** | Every chart in one scrollable view: 8 full-width cards covering demand context, temporal heatmap, forecast accuracy, ROI curve, impact demo, displacement analysis, events timeline. |
| **Data Ingestion** | Drag-drop a CSV/Excel/JSON of new violation records, pin a violation on a map, or paste data. Click **"Retrain system"** and the entire pipeline rebuilds in ~60 seconds. A before/after delta card shows what changed. |

**The chatbot:** Click the **"Ask the assistant..."** pill in the top bar. Try asking:
- *"Worst hotspots?"*
- *"Busiest police station?"*
- *"Where should we patrol today?"*
- *"Any events this week?"*
- *"When is the peak hour?"*

It answers instantly with real numbers from the data.

---

### Rebuilding from Raw Data (Optional — not needed to run the app)

The `outputs/` folder comes **pre-built** with all analytics, charts, maps, and data files. You do NOT need the raw dataset just to view and use the dashboard.

But if you want to rebuild everything from scratch (e.g., to verify reproducibility or after ingesting new data):

1. **Get the raw dataset** — `violation_raw.csv` (~105 MB). This is not included in the repo due to size. Ask the project team or download from the shared link.

2. **Place it in the data folder:**
   ```
   data/violation_raw.csv
   ```

3. **Run the full pipeline:**
   ```bash
   python run_all.py
   ```
   
   This takes ~70 seconds and runs 17 steps:
   - Cleans and feature-engineers the raw data
   - Detects 1,254 enforcement zones and scores each with CIS
   - Tags every hotspot to its demand generator (market, metro, mall, etc.)
   - Builds the Folium heatmap with 200 ranked zone markers
   - Runs temporal analysis and generates patrol schedules
   - Trains a 7-day-ahead forecast model
   - Measures enforcement impact with Difference-in-Differences
   - Checks for whack-a-mole displacement
   - Optimises patrol allocation with ROI curve
   - Detects event/surge anomalies
   - Runs the AI event agent (Claude + web search, falls back to offline sample)
   - Generates the live congestion feed
   - Builds the command centre, ingestion console, briefings, digest, and dashboard

4. **Start the server:**
   ```bash
   uvicorn api:app --port 8000
   ```

---

### Enabling AI Features (Optional)

Everything works fully offline. These API keys unlock enhanced capabilities:

#### Claude AI Chatbot + Event Agent

```powershell
# Windows PowerShell (current session):
$env:ANTHROPIC_API_KEY = "sk-ant-your-key-here"

# macOS / Linux:
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

**What it does:** Upgrades the chatbot from instant rule-based answers to Claude AI reasoning. Also enables the event agent to search the web for real upcoming Bengaluru events and reason about which hotspots they'll affect.

**Without the key:** The chatbot still works (instant rules with real data). The event agent uses a realistic offline sample. Nothing breaks.

#### Google Maps Live Traffic

```powershell
# Windows PowerShell:
$env:GOOGLE_MAPS_API_KEY = "AIza-your-key-here"

# macOS / Linux:
export GOOGLE_MAPS_API_KEY="AIza-your-key-here"
```

**What it does:** The Command Centre uses real Google Distance Matrix travel-time indices instead of simulated congestion.

**Without the key:** The Command Centre still pulses and works — it simulates realistic time-of-day congestion patterns. The Google Maps deep-links (click any junction → opens Google Maps with live traffic) always work regardless.


Expected:
```
15 passed, 1 warning in ~1.5s
```

---

### Troubleshooting

| Problem | Solution |
|---|---|
| `python` not found | Install Python 3.10+ from [python.org](https://www.python.org/downloads/). Check "Add to PATH" during install. Restart your terminal. On macOS/Linux, try `python3` instead. |
| `pip install` fails | Make sure virtual environment is active (`.venv`). Try `pip install --upgrade pip` first. Use Python 3.10–3.12, not 3.13/3.14. |
| PowerShell blocks `.ps1` scripts | Run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| "Address already in use" (port 8000) | Another program is using port 8000. Use a different port: `uvicorn api:app --port 8001` and open `http://localhost:8001` |
| Parking Map shows no red dots | Hard-refresh with `Ctrl + Shift + R`. The map lazy-loads when you click the tab — give it 2–3 seconds. |
| Chatbot says "offline" | Normal without `ANTHROPIC_API_KEY`. It uses instant rule-based answers that are fully functional. |
| Command Centre not pulsing | Use Chrome or Edge. Give it a few seconds to load the district data. |
| "Artifacts not built" API error | The `outputs/` folder is missing data. Run `python run_all.py` (needs the raw CSV in `data/`). |
| Streamlit won't start | Try: `streamlit run app.py --server.port 8502` |

---

### Project Structure

```
Flipkart-Gridlock/
│
├── api.py                  # FastAPI server (REST API + serves the dashboard)
├── app.py                  # Streamlit interactive app (CIS weight sliders)
├── config.py               # All tuneable parameters (CIS weights, grid size)
├── run_all.py              # Rebuild everything from raw data (17 steps, ~70s)
├── requirements.txt        # Python dependencies
├── demo_up.ps1             # Windows: one-click demo launcher
├── render.yaml             # Render.com cloud deployment config
│
├── src/                    # Source modules (one per pipeline step)
│   ├── pipeline.py         # Clean + feature-engineer raw data
│   ├── hotspots.py         # Detect zones, score CIS, rank & tier
│   ├── context.py          # Tag hotspots to demand generators
│   ├── build_map.py        # Folium heatmap + zone markers
│   ├── temporal.py         # Hour × weekday analysis, patrol windows
│   ├── forecast.py         # 7-day-ahead ML forecast
│   ├── impact.py           # Difference-in-Differences enforcement impact
│   ├── displacement.py     # Whack-a-mole displacement check
│   ├── optimize.py         # Patrol-allocation optimiser + ROI curve
│   ├── anomaly.py          # Event/surge spike detection
│   ├── ai_agent.py         # Claude AI + web search event agent
│   ├── congestion.py       # Live congestion feed (Google + parking)
│   ├── command_center.py   # Live command centre HTML generator
│   ├── ingest_console.py   # Data ingestion console HTML generator
│   ├── briefing.py         # Printable PDF briefing pack
│   ├── digest.py           # Daily ops digest
│   ├── portal.py           # Main dashboard generator (10 sections)
│   ├── chat.py             # Officer chatbot brain (rules + AI)
│   └── ingest.py           # Data ingestion logic
│
├── outputs/                # Pre-built artifacts (ready to use, no rebuild needed)
│   ├── dashboard.html      # The main app (10 tabs, chatbot, filters, tooltips)
│   ├── parking_congestion_map.html  # Folium map (heat + 200 red zone markers)
│   ├── congestion_command.html      # Live command centre (pulsing districts)
│   ├── ingest_console.html          # Data ingestion interface
│   ├── briefing_pack.pdf            # Printable field briefings
│   ├── daily_digest.md              # Auto-generated ops brief
│   ├── hotspots.csv                 # 1,254 zones ranked by CIS
│   └── (+ 20 more CSVs, PNGs, JSONs)
│
├── tests/
│   └── test_core.py        # 15 automated tests
│
└── data/                   # Data directory
    └── violation_raw.csv   # Raw dataset (NOT included — 105 MB)
```

---

### Tech Stack

Python 3.12 · FastAPI · Uvicorn · scikit-learn · pandas · NumPy · SciPy · Folium · Leaflet.js · Plotly · Matplotlib · Claude AI (Opus) with live web search · Google Maps Distance Matrix · Streamlit · pytest

---

*Built for GRIDLOCK 2.0 — Flipkart × Bengaluru Traffic Police × HackerEarth*
