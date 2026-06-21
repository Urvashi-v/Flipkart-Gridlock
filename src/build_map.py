"""
build_map.py  —  Step 4: the interactive heatmap the brief says is missing.

Produces outputs/parking_congestion_map.html with three toggle-able layers:
  1. Congestion heat layer  - raw violations, weighted by flow-blocking severity
                              so a car in a main road glows hotter than a bike in
                              a no-parking bay. This is the "where is the choke".
  2. Enforcement zones       - top zones as circles sized by ticket volume and
                              coloured by CIS tier (Critical/High/Medium), each
                              with a popup giving the patrol everything they need.
  3. Junction load           - the worst intersections, the classic congestion
                              points.
Open the HTML in any browser; no server needed.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import folium
from folium.plugins import HeatMap, MarkerCluster

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR

LABELLED_PARQUET = OUT_DIR / "violations_labelled.parquet"
HOTSPOTS_CSV = OUT_DIR / "hotspots.csv"
MAP_HTML = OUT_DIR / "parking_congestion_map.html"

TIER_COLOR = {"Critical": "#b10026", "High": "#f03b20",
              "Medium": "#feb24c", "Low": "#9ecae1"}

HEAT_SAMPLE = 45_000  # max raw points sent to the browser heat layer


def main():
    df = pd.read_parquet(LABELLED_PARQUET)
    hot = pd.read_csv(HOTSPOTS_CSV)
    center = [df["latitude"].mean(), df["longitude"].mean()]

    m = folium.Map(location=center, zoom_start=12, tiles="cartodbpositron",
                   control_scale=True)

    # ---- Layer 1: severity-weighted congestion heat ---------------------
    heat_src = df if len(df) <= HEAT_SAMPLE else df.sample(HEAT_SAMPLE, random_state=0)
    heat_data = heat_src[["latitude", "longitude", "severity"]].to_numpy().tolist()
    fg_heat = folium.FeatureGroup(name="🔥 Congestion heat (severity-weighted)", show=True)
    HeatMap(heat_data, radius=11, blur=15, min_opacity=0.25,
            max_zoom=14).add_to(fg_heat)
    fg_heat.add_to(m)

    # ---- Layer 2: ranked enforcement zones ------------------------------
    fg_zone = folium.FeatureGroup(name="🎯 Enforcement zones (top 200)", show=True)
    top = hot.head(200)
    vmax = top["n_tickets"].max()
    for _, r in top.iterrows():
        radius = 6 + 18 * np.sqrt(r["n_tickets"] / vmax)   # area ∝ volume
        color = TIER_COLOR.get(str(r["tier"]), "#9ecae1")
        popup = folium.Popup(html=(
            f"<b>#{int(r['rank'])} · {r['tier']} · CIS {r['CIS']:.1f}/100</b><br>"
            f"<b>{r['junction_name']}</b><br>"
            f"PS: {r['police_station']}<br>"
            f"Tickets: {int(r['n_tickets']):,} &nbsp; (rej {r['rejected_share']*100:.0f}%)<br>"
            f"Top violation: {r['top_violation']}<br>"
            f"Top vehicle: {r['top_vehicle']}<br>"
            f"Junction share: {r['junction_share']*100:.0f}%<br>"
            f"Peak: {int(r['peak_hour']):02d}:00, {r['peak_dow']}<br>"
            f"<hr style='margin:3px'>CIS parts — vol {r['c_volume']:.2f} · "
            f"sev {r['c_severity']:.2f} · jn {r['c_junction']:.2f} · "
            f"veh {r['c_vehicle']:.2f} · per {r['c_persistence']:.2f}"
        ), max_width=300)
        folium.CircleMarker(
            location=[r["lat"], r["lon"]], radius=radius,
            color=color, weight=1, fill=True, fill_color=color, fill_opacity=0.55,
            popup=popup,
            tooltip=f"#{int(r['rank'])} CIS {r['CIS']:.0f} · {int(r['n_tickets']):,} tickets",
        ).add_to(fg_zone)
    fg_zone.add_to(m)

    # ---- Layer 3: worst junctions ---------------------------------------
    fg_jn = folium.FeatureGroup(name="🚦 Worst junctions", show=False)
    jdf = df[df["at_junction"]]
    jt = (jdf.groupby("junction_name")
             .agg(n=("id", "size"), lat=("latitude", "mean"),
                  lon=("longitude", "mean"), sev=("severity", "mean"))
             .sort_values("n", ascending=False).head(40).reset_index())
    for _, r in jt.iterrows():
        folium.Marker(
            location=[r["lat"], r["lon"]],
            icon=folium.Icon(color="red", icon="warning-sign"),
            tooltip=f"{r['junction_name']} · {int(r['n']):,} tickets",
            popup=folium.Popup(f"<b>{r['junction_name']}</b><br>"
                               f"Tickets: {int(r['n']):,}<br>"
                               f"Mean severity: {r['sev']:.2f}", max_width=260),
        ).add_to(fg_jn)
    fg_jn.add_to(m)

    # ---- legend ----------------------------------------------------------
    legend = """
    <div style="position: fixed; bottom: 24px; left: 24px; z-index: 9999;
         background: white; padding: 10px 14px; border:1px solid #888;
         border-radius:6px; font: 12px/1.4 sans-serif; box-shadow:0 1px 4px #0003;">
      <b>Congestion Impact tier</b><br>
      <span style="color:#b10026">&#9679;</span> Critical (CIS &gt; 65)<br>
      <span style="color:#f03b20">&#9679;</span> High (45-65)<br>
      <span style="color:#feb24c">&#9679;</span> Medium (25-45)<br>
      <span style="color:#9ecae1">&#9679;</span> Low (&lt; 25)<br>
      <i>circle size &#8733; ticket volume</i>
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(MAP_HTML))
    print(f"Wrote {MAP_HTML}")
    print(f"  heat points : {len(heat_data):,}")
    print(f"  zone markers: {len(top):,}")
    print(f"  junctions   : {len(jt):,}")


if __name__ == "__main__":
    main()
