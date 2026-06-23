"""
ingest_console.py  —  generates outputs/ingest_console.html, the data-intake &
retraining UI. Three input modes (drag-drop file, pick-on-map field report, paste)
plus a live "retrain the system" flow with a step progress bar, streaming log, and
a before/after delta. Talks to the FastAPI backend (api.py) — start it first:
    uvicorn api:app
"""
import sys, os
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR

OUT_HTML = OUT_DIR / "ingest_console.html"

TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Gridlock · Data Ingestion & Retraining</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 :root{--bg:#0b1118;--card:#121c27;--line:#22303f;--tx:#e7edf3;--red:#f03b20;--grn:#16d06a}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--tx);
   font:14px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
 .wrap{max-width:980px;margin:0 auto;padding:26px}
 h1{margin:0;font-size:24px} h1 b{color:var(--red)}
 .sub{color:#9fb0c0;margin:4px 0 18px}
 .api{font-size:12px;padding:4px 9px;border-radius:6px;border:1px solid var(--line);background:#101a24}
 .ok{color:var(--grn)} .bad{color:#ff6a5a}
 .row{display:flex;gap:14px;flex-wrap:wrap}
 .stat{flex:1;min-width:150px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
 .stat b{font-size:26px;display:block} .stat span{font-size:12px;color:#8aa}
 .tabs{display:flex;gap:8px;margin:20px 0 12px}
 .tab{padding:9px 14px;border-radius:9px;border:1px solid var(--line);background:#101a24;cursor:pointer;font-size:13px}
 .tab.on{background:var(--red);border-color:var(--red);color:#fff;font-weight:600}
 .pane{display:none;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
 .pane.on{display:block}
 #drop{border:2px dashed #34506a;border-radius:14px;padding:46px;text-align:center;transition:all .2s;cursor:pointer}
 #drop.hot{border-color:var(--red);background:#1a0f0c;transform:scale(1.01)}
 #drop .big{font-size:38px} #drop .h{font-size:16px;margin-top:6px} #drop .s{color:#8aa;font-size:13px}
 #map{height:300px;border-radius:12px;border:1px solid var(--line)}
 label{font-size:12px;color:#9fb0c0;display:block;margin:10px 0 4px}
 select,textarea,input{width:100%;background:#0e1822;border:1px solid var(--line);color:var(--tx);
   border-radius:8px;padding:9px;font:inherit}
 textarea{min-height:130px;font-family:ui-monospace,Consolas,monospace;font-size:12px}
 button.go{background:var(--red);color:#fff;border:none;border-radius:9px;padding:11px 18px;
   font-weight:600;cursor:pointer;margin-top:12px;font-size:14px}
 button.go:disabled{opacity:.5;cursor:default}
 button.ghost{background:#101a24;border:1px solid var(--line);color:var(--tx)}
 .result{margin-top:14px;display:none;gap:12px}
 .result.on{display:flex} .rc{flex:1;background:#0e1822;border:1px solid var(--line);border-radius:10px;padding:12px;text-align:center}
 .rc b{font-size:24px;display:block} .rc.acc b{color:var(--grn)} .rc.rej b{color:#ff6a5a}
 /* retrain */
 .retrain{margin-top:22px;background:linear-gradient(135deg,#161028,#101a24);border:1px solid #2a2150;border-radius:16px;padding:20px}
 .retrain h2{margin:0 0 4px;font-size:18px}
 .pbar{height:12px;background:#0c141d;border-radius:7px;overflow:hidden;margin:14px 0 6px}
 .pbar i{display:block;height:100%;width:0;background:linear-gradient(90deg,#f03b20,#ff8c1a);transition:width .4s}
 .log{background:#070c12;border:1px solid var(--line);border-radius:10px;padding:10px;height:150px;overflow:auto;
   font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#bcd;margin-top:8px}
 .log div{padding:1px 0} .log .ok{color:var(--grn)}
 .delta{display:none;gap:12px;margin-top:14px} .delta.on{display:flex}
 .dc{flex:1;background:#0e1822;border:1px solid var(--line);border-radius:10px;padding:12px}
 .dc b{font-size:22px} .dc .d{font-size:13px;font-weight:700} .up{color:#ff8c1a} .dn{color:var(--grn)}
 a.home{color:#9fb0c0;text-decoration:none;font-size:12px;border:1px solid var(--line);padding:5px 10px;border-radius:6px}
</style></head><body><div class="wrap">
 <div style="display:flex;align-items:center;gap:12px">
   <div><h1>Grid<b>lock</b> · Data Ingestion &amp; Retraining</h1>
     <div class="sub">Feed the system fresh violations — then retrain it on the new data.</div></div>
   <span class="api" id="api" style="margin-left:auto">API: checking…</span>
   <a class="home" href="dashboard.html">← Dashboard</a>
 </div>

 <div class="row">
   <div class="stat"><b>~298k</b><span>base records (immutable)</span></div>
   <div class="stat"><b id="ingn">0</b><span>records you've ingested</span></div>
   <div class="stat"><b id="zonesn">—</b><span>current enforcement zones</span></div>
 </div>

 <div class="tabs">
   <div class="tab on" data-m="file">📁 Drop a file</div>
   <div class="tab" data-m="map">📍 Report on map</div>
   <div class="tab" data-m="paste">📋 Paste records</div>
 </div>

 <div class="pane on" id="pane-file">
   <div id="drop"><div class="big">⬇️</div><div class="h">Drag &amp; drop a CSV, XLSX or JSON</div>
     <div class="s">or click to choose · messy columns auto-map · bad rows auto-reject</div>
     <input type="file" id="fileinp" accept=".csv,.xlsx,.xls,.json" style="display:none"></div>
   <div class="result" id="res-file">
     <div class="rc"><b id="rf-r">0</b>received</div>
     <div class="rc acc"><b id="rf-a">0</b>accepted</div>
     <div class="rc rej"><b id="rf-j">0</b>rejected</div>
   </div>
 </div>

 <div class="pane" id="pane-map">
   <div id="map"></div>
   <div class="row">
     <div style="flex:1"><label>Vehicle type</label>
       <select id="veh"><option>CAR</option><option>SCOOTER</option><option>MOTOR CYCLE</option>
       <option>BUS (BMTC/KSRTC)</option><option>LGV</option><option>TEMPO</option>
       <option>PASSENGER AUTO</option><option>LORRY/GOODS VEHICLE</option></select></div>
     <div style="flex:1"><label>Violation</label>
       <select id="vio"><option>WRONG PARKING</option><option>NO PARKING</option>
       <option>PARKING IN A MAIN ROAD</option><option>DOUBLE PARKING</option>
       <option>PARKING NEAR ROAD CROSSING</option><option>PARKING ON FOOTPATH</option></select></div>
   </div>
   <div class="sub" id="pin" style="margin-top:10px">Click the map to drop a pin…</div>
   <button class="go" id="addbtn" disabled>＋ Add this violation</button>
 </div>

 <div class="pane" id="pane-paste">
   <label>Paste CSV (with a header row) or a JSON array of records</label>
   <textarea id="pastebox" placeholder='lat,lng,vehicle,violation
12.9767,77.5713,BUS,PARKING IN A MAIN ROAD

— or —
[{"lat":12.98,"lng":77.60,"vehicle":"CAR","violation":"NO PARKING"}]'></textarea>
   <button class="go" id="pastebtn">Ingest pasted data</button>
   <div class="result" id="res-paste">
     <div class="rc"><b id="rp-r">0</b>received</div>
     <div class="rc acc"><b id="rp-a">0</b>accepted</div>
     <div class="rc rej"><b id="rp-j">0</b>rejected</div>
   </div>
 </div>

 <div class="retrain">
   <h2>🧠 Retrain the system on your new data</h2>
   <div class="sub">Rebuilds everything on <b>base + ingested</b> — re-detects hotspots,
     re-scores impact, and <b>retrains the forecast model</b>. ~1 minute.</div>
   <button class="go" id="trainbtn">🧠 Retrain system now</button>
   <span id="tstatus" style="margin-left:10px;color:#9fb0c0;font-size:13px"></span>
   <div class="pbar"><i id="pbar"></i></div>
   <div class="log" id="tlog"></div>
   <div class="delta" id="delta">
     <div class="dc"><span class="d">Enforcement zones</span><br><b id="dz">—</b> <span id="dzd" class="d"></span></div>
     <div class="dc"><span class="d">Violations analysed</span><br><b id="dc">—</b> <span id="dcd" class="d"></span></div>
   </div>
 </div>
</div>
<script>
const API="__API__";
let mode="file", pin=null, marker=null, lmap=null;

async function api(path,opts){ opts=opts||{}; opts.headers=Object.assign({},opts.headers||{});
  const r=await fetch(API+path,opts);
  if(!r.ok) throw new Error(await r.text()); return r.json(); }
function animate(el,to){ const from=parseInt(el.textContent.replace(/\D/g,''))||0; const t0=performance.now();
  (function step(t){const p=Math.min(1,(t-t0)/500); el.textContent=Math.round(from+(to-from)*p).toLocaleString();
   if(p<1)requestAnimationFrame(step);})(t0);}

async function ping(){ try{const s=await api("/summary"); document.getElementById('api').innerHTML='API: <span class=ok>online</span>';
   document.getElementById('zonesn').textContent=s.zones.toLocaleString(); refreshStats();}
  catch(e){document.getElementById('api').innerHTML='API: <span class=bad>offline — run <code>uvicorn api:app</code></span>';}}
async function refreshStats(){ try{const s=await api("/dataset/stats"); animate(document.getElementById('ingn'),s.ingested);}catch(e){} }

// tabs
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{ mode=t.dataset.m;
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===t));
  document.querySelectorAll('.pane').forEach(p=>p.classList.remove('on'));
  document.getElementById('pane-'+mode).classList.add('on');
  if(mode==='map'&&!lmap){ setTimeout(initMap,60); }});

// file drop
const drop=document.getElementById('drop'), fi=document.getElementById('fileinp');
drop.onclick=()=>fi.click();
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('hot');}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('hot');}));
drop.addEventListener('drop',ev=>{ if(ev.dataTransfer.files[0]) uploadFile(ev.dataTransfer.files[0]); });
fi.onchange=()=>{ if(fi.files[0]) uploadFile(fi.files[0]); };
async function uploadFile(f){ drop.querySelector('.h').textContent='Uploading '+f.name+'…';
  const fd=new FormData(); fd.append('file',f);
  try{ const rep=await api("/ingest/file",{method:'POST',body:fd}); showResult('rf',rep,'res-file');
    drop.querySelector('.h').textContent='Drag & drop a CSV, XLSX or JSON'; refreshStats(); }
  catch(e){ drop.querySelector('.h').textContent='Upload failed — '+e.message.slice(0,80); } }

function showResult(pfx,rep,box){ document.getElementById(box).classList.add('on');
  animate(document.getElementById(pfx+'-r'),rep.received);
  animate(document.getElementById(pfx+'-a'),rep.accepted);
  animate(document.getElementById(pfx+'-j'),(rep.rejected_geo||0)+(rep.rejected_nonparking||0)); }

// map mode
function initMap(){ lmap=L.map('map').setView([12.968,77.59],12);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{maxZoom:19}).addTo(lmap);
  lmap.on('click',e=>{ pin=e.latlng; if(marker)marker.setLatLng(pin); else marker=L.marker(pin).addTo(lmap);
    document.getElementById('pin').textContent='📍 '+pin.lat.toFixed(5)+', '+pin.lng.toFixed(5);
    document.getElementById('addbtn').disabled=false; }); }
document.getElementById('addbtn').onclick=async()=>{ if(!pin)return;
  const rec={lat:pin.lat,lng:pin.lng,vehicle:document.getElementById('veh').value,violation:document.getElementById('vio').value};
  try{ const rep=await api("/ingest/record",{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(rec)});
    document.getElementById('pin').textContent= rep.accepted? '✅ Added! Drop another pin…':'⚠ Rejected (outside city)';
    refreshStats(); }catch(e){ document.getElementById('pin').textContent='Failed: '+e.message.slice(0,60); } };

// paste mode
document.getElementById('pastebtn').onclick=async()=>{ const t=document.getElementById('pastebox').value.trim(); if(!t)return;
  try{ let rep;
    if(t[0]==='['||t[0]==='{'){ const arr=JSON.parse(t); rep=await api("/ingest/records",{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Array.isArray(arr)?arr:[arr])}); }
    else{ const fd=new FormData(); fd.append('file',new Blob([t],{type:'text/csv'}),'pasted.csv'); rep=await api("/ingest/file",{method:'POST',body:fd}); }
    showResult('rp',rep,'res-paste'); refreshStats(); }
  catch(e){ alert('Ingest failed: '+e.message.slice(0,120)); } };

// retrain
let poll=null;
document.getElementById('trainbtn').onclick=async()=>{ const b=document.getElementById('trainbtn'); b.disabled=true;
  document.getElementById('tlog').innerHTML=''; document.getElementById('delta').classList.remove('on');
  document.getElementById('tstatus').textContent='starting…';
  try{ await api("/rebuild",{method:'POST'}); poll=setInterval(pollStatus,1000); }
  catch(e){ document.getElementById('tstatus').textContent='Error: '+e.message.slice(0,80); b.disabled=false; } };
let lastStep=0;
async function pollStatus(){ let s; try{ s=await api("/rebuild/status"); }catch(e){ return; }
  const pct=s.total? Math.round(100*s.step/s.total):0;
  document.getElementById('pbar').style.width=pct+'%';
  document.getElementById('tstatus').textContent=`step ${s.step}/${s.total} · ${s.elapsed||0}s`;
  const log=document.getElementById('tlog');
  while(lastStep<s.log.length){ const d=document.createElement('div'); const line=s.log[lastStep];
    d.textContent='› '+line; if(line.includes('DONE'))d.className='ok'; log.appendChild(d); lastStep++; }
  log.scrollTop=log.scrollHeight;
  if(s.done){ clearInterval(poll); poll=null; lastStep=0;
    document.getElementById('trainbtn').disabled=false;
    if(s.error){ document.getElementById('tstatus').textContent='❌ '+s.error; return; }
    document.getElementById('tstatus').textContent='✅ retrained in '+(s.elapsed||0)+'s';
    showDelta(s.before,s.after); ping(); }
}
function showDelta(b,a){ if(!a||!a.zones)return; document.getElementById('delta').classList.add('on');
  const dz=document.getElementById('dz'), dc=document.getElementById('dc');
  animate(dz,a.zones); animate(dc,a.violations||0);
  const zdiff=(a.zones||0)-(b.zones||0), cdiff=(a.violations||0)-(b.violations||0);
  document.getElementById('dzd').innerHTML=zdiff>=0?`<span class=up>▲ +${zdiff}</span>`:`<span class=dn>▼ ${zdiff}</span>`;
  document.getElementById('dcd').innerHTML=cdiff>=0?`<span class=up>▲ +${cdiff.toLocaleString()}</span>`:`<span class=dn>▼ ${cdiff.toLocaleString()}</span>`;
}
ping(); setInterval(refreshStats,5000);
</script></body></html>"""


def main():
    api_url = os.environ.get("GRIDLOCK_API_URL", "")
    OUT_HTML.write_text(TEMPLATE.replace("__API__", api_url), encoding="utf-8")
    print(f"Wrote {OUT_HTML}")
    print(f"  API target: {api_url}  (start it with: uvicorn api:app)")


if __name__ == "__main__":
    main()
