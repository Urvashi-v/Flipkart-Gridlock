"""
run_all.py  —  one command to rebuild every artifact end-to-end.

    python run_all.py

Order matters: pipeline -> hotspots -> (map | temporal) -> dashboard.
"""
import subprocess, sys, time
from pathlib import Path

# Windows consoles default to cp1252; force UTF-8 so child output never crashes.
import os
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
STEPS = [
    ("Clean + feature engineer", "src/pipeline.py"),
    ("Detect hotspots + score CIS", "src/hotspots.py"),
    ("Demand-generator context", "src/context.py"),
    ("Build interactive heatmap", "src/build_map.py"),
    ("Temporal analysis + patrol schedule", "src/temporal.py"),
    ("Forecast next week's hotspots", "src/forecast.py"),
    ("Before/after enforcement impact (DiD)", "src/impact.py"),
    ("Displacement (whack-a-mole) check", "src/displacement.py"),
    ("Patrol-allocation optimiser + ROI", "src/optimize.py"),
    ("Event / anomaly detection", "src/anomaly.py"),
    ("AI event-aware forecast (Claude + web search)", "src/ai_agent.py"),
    ("Live congestion district feed (Google/sim)", "src/congestion.py"),
    ("Live congestion command centre (HTML)", "src/command_center.py"),
    ("Data ingestion console (HTML)", "src/ingest_console.py"),
    ("Printable enforcement briefing pack (PDF)", "src/briefing.py"),
    ("Daily ops digest", "src/digest.py"),
    ("Web app (login + role dashboard)", "src/portal.py"),
]


def run(label, script):
    print(f"\n{'='*64}\n>> {label}  ({script})\n{'='*64}")
    t = time.time()
    r = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT)
    if r.returncode != 0:
        sys.exit(f"FAILED at {script} (exit {r.returncode})")
    print(f"  done in {time.time()-t:.1f}s")


if __name__ == "__main__":
    t0 = time.time()
    for label, script in STEPS:
        run(label, script)
    print(f"\nALL DONE in {time.time()-t0:.1f}s")
    print("Open  outputs/index.html  (dashboard)  and  "
          "outputs/parking_congestion_map.html  (map).")
