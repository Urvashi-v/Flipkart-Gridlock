"""
context.py  —  WHY does each hotspot exist? Attribute every zone to the demand
generator that pulls the illegal parking: a metro/transit hub, a wholesale
market, a mall, a hospital, etc. This directly addresses the problem statement's
"near commercial areas, metro stations, and events" and turns a dot on a map
into an explanation an officer can act on.

HOW
  Each zone's address + junction text is matched against ordered keyword rules
  (config.CONTEXT_RULES), most-specific first. The first hit wins; unmatched
  zones fall back to "Mixed / Other".

OUTPUT
  outputs/zone_context.csv     - zone -> context category + matched keyword
  outputs/context_summary.png  - tickets & cost by context category
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR, CONTEXT_RULES, DEFAULT_CONTEXT

LABELLED = OUT_DIR / "violations_labelled.parquet"


def classify(text):
    t = str(text).lower()
    for category, keywords in CONTEXT_RULES:
        for kw in keywords:
            if kw in t:
                return category, kw
    return DEFAULT_CONTEXT, ""


def main():
    df = pd.read_parquet(LABELLED)
    z = df[df["zone"] != "__noise__"].copy()

    g = z.groupby("zone")
    zt = pd.DataFrame({
        "n_tickets": g.size(),
        "lat": g["latitude"].mean(), "lon": g["longitude"].mean(),
        "junction_name": g["junction_name"].agg(lambda s: s.mode().iloc[0]),
        "police_station": g["police_station"].agg(lambda s: s.mode().iloc[0]),
        "address": g["location"].agg(lambda s: s.mode().iloc[0]),
    }).reset_index()

    cat = zt.apply(lambda r: classify(f"{r['address']} {r['junction_name']}"), axis=1)
    zt["context"] = [c[0] for c in cat]
    zt["generator_kw"] = [c[1] for c in cat]

    zt.to_csv(OUT_DIR / "zone_context.csv", index=False)

    by = (zt.groupby("context")
            .agg(zones=("zone", "size"), tickets=("n_tickets", "sum"))
            .sort_values("tickets", ascending=False))
    by["tickets_%"] = (by["tickets"] / by["tickets"].sum() * 100).round(1)

    print("Demand-generator attribution of hotspots:")
    print(by.to_string())

    # ---- plot: violations by demand generator ----
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    b = by[::-1]
    ax.barh(b.index, b["tickets"], color="#f03b20")
    ax.set_title("Illegal-parking violations by demand generator", weight="bold", fontsize=12)
    ax.tick_params(labelsize=9)
    for i, v in enumerate(b["tickets"]):
        ax.text(v, i, f" {v:,}", va="center", fontsize=8.5)
    fig.tight_layout(); fig.savefig(OUT_DIR / "context_summary.png", dpi=130)
    plt.close(fig)
    print("\nWrote zone_context.csv, context_summary.png")


if __name__ == "__main__":
    main()
