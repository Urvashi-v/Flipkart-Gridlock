"""
command_center.py  —  generates outputs/congestion_command.html, the Live
Congestion Command Centre.

A dark, full-screen map of the city where each police DISTRICT pulses by its
current congestion (green→amber→orange→red, blinking when heavy/severe). Click a
district to drill down: the map flies to it and a panel lists the "areas of
attention for police" — its worst hotspots — each with a recommended action, any
AI event flags, and a one-click **Google Maps live-traffic** link.

It runs standalone (open the file): congestion is simulated client-side from a
time-of-day model so it always feels live. If the API (api.py) is running it
polls `/congestion` for real values (Google travel-time indices when a key is
set). District data is embedded at build time by this script.
"""
import sys, json, os
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR, CONGESTION
from src.congestion import compute_districts

OUT_HTML = OUT_DIR / "congestion_command.html"

TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Gridlock · Live Congestion Command Centre</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root{--bg:#0b1118;--pan:#121c27;--line:#22303f;--tx:#e7edf3}
  html,body{margin:0;height:100%;background:var(--bg);color:var(--tx);
    font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
  #map{position:absolute;inset:0}
  .bar{position:absolute;top:0;left:0;right:0;z-index:1000;display:flex;
    align-items:center;gap:14px;padding:10px 16px;background:linear-gradient(#0b1118ee,#0b111800);
    pointer-events:none}
  .bar *{pointer-events:auto}
  .bar h1{margin:0;font-size:18px;font-weight:700}
  .bar h1 b{color:#f03b20}
  .pill{font-size:12px;padding:3px 9px;border-radius:20px;border:1px solid var(--line);background:#101a24}
  .live{color:#16d06a} .live::before{content:"●";margin-right:5px;animation:bl 1.1s infinite}
  @keyframes bl{50%{opacity:.25}}
  .legend{margin-left:auto;display:flex;gap:12px;font-size:12px}
  .legend i{width:11px;height:11px;border-radius:50%;display:inline-block;margin-right:4px;vertical-align:-1px}
  a.home{color:#9fb0c0;text-decoration:none;font-size:12px;border:1px solid var(--line);
    padding:4px 9px;border-radius:6px;background:#101a24}
  /* district markers */
  .dmark{display:flex;align-items:center;justify-content:center}
  .dot{border-radius:50%;border:2px solid #0008;box-shadow:0 0 0 0 #0000;transition:all .4s}
  .dot.heavy{animation:pulse 1.6s infinite}
  .dot.severe{animation:pulse .85s infinite}
  @keyframes pulse{0%{box-shadow:0 0 0 0 var(--c)}70%{box-shadow:0 0 0 16px #0000}100%{box-shadow:0 0 0 0 #0000}}
  .dlabel{font-size:10px;color:#cdd9e5;text-shadow:0 1px 3px #000;white-space:nowrap;margin-top:2px;text-align:center}
  /* panel */
  #panel{position:absolute;top:0;right:0;bottom:0;width:388px;max-width:92vw;z-index:1001;
    background:var(--pan);border-left:1px solid var(--line);transform:translateX(105%);
    transition:transform .28s;overflow:auto;box-shadow:-8px 0 30px #0007}
  #panel.open{transform:none}
  .ph{padding:16px 16px 10px;border-bottom:1px solid var(--line)}
  .ph .x{float:right;cursor:pointer;color:#9fb0c0;font-size:20px;line-height:1}
  .ph h2{margin:0 0 2px;font-size:18px}
  .ph .sub{color:#9fb0c0;font-size:12px}
  .gauge{height:10px;border-radius:6px;background:#0c141d;overflow:hidden;margin:10px 0 4px}
  .gauge i{display:block;height:100%;transition:all .5s}
  .pb{padding:12px 16px}
  .stat{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:8px}
  .stat div{background:#0e1822;border:1px solid var(--line);border-radius:8px;padding:8px}
  .stat b{display:block;font-size:16px}.stat span{font-size:11px;color:#8aa}
  h3{font-size:13px;margin:14px 0 6px;color:#bcd;border-left:3px solid #f03b20;padding-left:8px}
  .hs{background:#0e1822;border:1px solid var(--line);border-radius:9px;padding:9px 11px;margin-bottom:8px;cursor:pointer}
  .hs:hover{border-color:#f03b20}
  .hs .t{font-weight:600} .hs .m{font-size:12px;color:#9fb0c0;margin-top:2px}
  .hs a{color:#5ab0ff;text-decoration:none;font-size:12px}
  .ev{background:#1a1330;border:1px solid #3a2a5a;border-radius:9px;padding:9px 11px;margin-bottom:8px}
  .ev .r{font-weight:700}
  .tag{font-size:10px;padding:2px 7px;border-radius:10px;border:1px solid var(--line)}
</style></head><body>
<div id="map"></div>
<div class="bar">
  <h1>Grid<b>lock</b> · Live Congestion Command Centre</h1>
  <span class="pill live" id="clock">LIVE</span>
  <span class="pill" id="src">source</span>
  <span class="legend">
    <span><i style="background:#16d06a"></i>Free</span>
    <span><i style="background:#ffd23f"></i>Moderate</span>
    <span><i style="background:#ff8c1a"></i>Heavy</span>
    <span><i style="background:#ff3b30"></i>Severe</span>
  </span>
  <a class="home" href="dashboard.html">← Dashboard</a>
</div>
<div id="panel"><div id="pcontent"></div></div>
<script>
// When embedded inside the dashboard (iframe), hide the "← Dashboard" link so it
// doesn't load a dashboard-inside-the-dashboard. Only show it when standalone.
if (window.self !== window.top) { var _h = document.querySelector('.home'); if (_h) _h.remove(); }
const DATA = __DATA__;
const API = "http://localhost:8000";   // optional live API (api.py)
let districts = DATA.districts, source = DATA.source, openIdx = -1, focusLayer = null;

const map = L.map('map',{zoomControl:false}).setView([12.968,77.59],12);
L.control.zoom({position:'bottomright'}).addTo(map);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  {maxZoom:19,attribution:'© OpenStreetMap, © CARTO'}).addTo(map);

function todFactor(){const d=new Date();const h=d.getHours()+d.getMinutes()/60;
  const a=Math.exp(-Math.pow((h-9.5)/2.2,2)),b=Math.exp(-Math.pow((h-18.5)/2.2,2));
  return Math.min(1,0.15+0.92*Math.max(a,b));}
function congestionOf(d){
  if(d.congestion!=null) return d.congestion;               // server/Google value
  const tod=todFactor();
  const jit=0.8+0.28*Math.sin(Date.now()/2500+(d._seed||0))+0.12*Math.random();
  const live=Math.min(1,(0.32+0.78*d.pressure)*tod*jit);
  return Math.round(100*(0.45*d.pressure+0.55*live));
}
function level(c){ if(c>=75)return{n:'Severe',c:'#ff3b30',k:'severe'};
  if(c>=55)return{n:'Heavy',c:'#ff8c1a',k:'heavy'};
  if(c>=32)return{n:'Moderate',c:'#ffd23f',k:''};
  return{n:'Free',c:'#16d06a',k:''}; }

districts.forEach((d,i)=>{ d._seed=i*1.7;
  const m=L.marker([d.lat,d.lon],{icon:L.divIcon({className:'dmark',
    html:`<div><div class="dot" id="dot${i}"></div><div class="dlabel">${d.district}</div></div>`,
    iconSize:[0,0]})}).addTo(map);
  m.on('click',()=>openDistrict(i)); d._m=m;
});

function paint(){
  districts.forEach((d,i)=>{
    const c=congestionOf(d), L1=level(c), el=document.getElementById('dot'+i);
    if(!el)return; const r=12+26*d.pressure;
    el.style.width=r+'px'; el.style.height=r+'px';
    el.style.background=L1.c; el.style.setProperty('--c',L1.c+'aa');
    el.className='dot '+L1.k; d._c=c; d._lv=L1;
  });
  if(openIdx>=0) refreshPanel();
}
function gauge(c,col){return `<div class="gauge"><i style="width:${c}%;background:${col}"></i></div>`;}

function openDistrict(i){ openIdx=i; const d=districts[i];
  map.flyTo([d.lat,d.lon],14,{duration:.6});
  document.getElementById('panel').classList.add('open'); refreshPanel();
}
function closePanel(){openIdx=-1;document.getElementById('panel').classList.remove('open');
  if(focusLayer){map.removeLayer(focusLayer);focusLayer=null;}}
function refreshPanel(){ const d=districts[openIdx]; const c=d._c??congestionOf(d), L1=d._lv||level(c);
  let h=`<div class="ph"><span class="x" onclick="closePanel()">✕</span>
    <h2>${d.district}</h2><div class="sub">${L1.n} congestion · ${d.n_hotspots} parking hotspots</div>
    ${gauge(c,L1.c)}<div class="sub">${c}/100 ${source==='google'?'· live Google traffic':'· live (simulated)'}</div></div>
    <div class="pb">
      <div class="stat">
        <div><b>${(d.violations||0).toLocaleString()}</b><span>violations</span></div>
        <div><b>${d.n_hotspots}</b><span>hotspots</span></div>
        <div><b style="color:${L1.c}">${L1.n}</b><span>road state</span></div>
      </div>
      <a class="tag" style="color:#5ab0ff" href="${d.gmaps}" target="_blank">🛰️ Open live Google traffic for this district →</a>`;
  if(d.events&&d.events.length){ h+=`<h3>⚠ AI event flags this week</h3>`;
    d.events.forEach(e=>{h+=`<div class="ev"><span class="r" style="color:#ff8c1a">${e.risk}</span> · ${e.date} — ${e.event}
      <div class="m" style="font-size:12px;color:#bcd">${e.why}</div></div>`;});}
  h+=`<h3>🎯 Areas of attention for police</h3>`;
  d.hotspots.forEach((s,j)=>{ h+=`<div class="hs" onclick="focusHS(${openIdx},${j})">
      <div class="t">${s.junction}</div>
      <div class="m">${s.context} · top: ${s.violation} · ${(s.tickets||0).toLocaleString()} violations</div>
      <div class="m"><b>Do:</b> ${s.action}</div>
      <a href="${s.gmaps}" target="_blank" onclick="event.stopPropagation()">🛰️ live traffic here →</a></div>`;});
  h+=`</div>`;
  document.getElementById('pcontent').innerHTML=h;
}
function focusHS(i,j){ const s=districts[i].hotspots[j];
  if(focusLayer)map.removeLayer(focusLayer);
  focusLayer=L.circle([s.lat,s.lon],{radius:90,color:'#ff3b30',weight:3,fill:false,className:'foc'}).addTo(map);
  map.flyTo([s.lat,s.lon],17,{duration:.6});
}
async function poll(){ try{ const r=await fetch(API+"/congestion",{cache:'no-store'});
  if(r.ok){const f=await r.json(); if(f.districts){ const by={}; f.districts.forEach(x=>by[x.district]=x);
    districts.forEach(d=>{const u=by[d.district]; if(u){d.congestion=u.congestion; d.tti=u.tti;}});
    source=f.source; document.getElementById('src').textContent='source: '+f.source.toUpperCase();}}
  }catch(e){} }

document.getElementById('src').textContent='source: '+source.toUpperCase()+' (standalone)';
setInterval(()=>{document.getElementById('clock').textContent='LIVE · '+new Date().toLocaleTimeString();},1000);
paint(); setInterval(paint,2500);
poll(); setInterval(poll,15000);          // upgrades to real /congestion if api.py is running
</script></body></html>"""


def main():
    feed = compute_districts()
    # attach a stable seed-friendly structure; strip server congestion for embed so
    # the standalone page simulates live (the API poll overrides it when running).
    for d in feed["districts"]:
        d.setdefault("congestion", None)
    html = (TEMPLATE
            .replace("__DATA__", json.dumps(feed, ensure_ascii=False)))
    OUT_HTML.write_text(html, encoding="utf-8")
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    print(f"Wrote {OUT_HTML}")
    print(f"  districts: {len(feed['districts'])}  ·  source: {feed['source']}")
    print(f"  Google live travel-times: {'ON (key set)' if key else 'OFF (using simulation + Google deep-links)'}")
    print("  Open the file, or run api.py for live /congestion polling.")


if __name__ == "__main__":
    main()
