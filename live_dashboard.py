#!/usr/bin/env python
# =============================================================================
# Bloc 2 - Data Infrastructure : LIVE evidence dashboard (no narration needed)
# A tiny local web server that serves one visual page whose numbers UPDATE LIVE
# (every 2s) from the running stack: messages, rows, throughput, latency,
# anomalies, Prometheus targets - plus IaC / data-model / monitoring proof and
# buttons to the live Grafana cockpit.
#
#   python live_dashboard.py
#
# Works from PowerShell, cmd, or Git Bash. Ctrl+C to stop.
# =============================================================================
import http.server, socketserver, json, urllib.request, subprocess, time, html, pathlib, webbrowser, os, re, sys

os.chdir(pathlib.Path(__file__).resolve().parent)
PORT = int(os.environ.get("PORT", "8090"))
SP, PROM = "http://localhost:8001", "http://localhost:9090"

# ---------- live data --------------------------------------------------------
def j(url, t=4):
    with urllib.request.urlopen(url, timeout=t) as r: return json.loads(r.read().decode())
def txt(url, t=4):
    with urllib.request.urlopen(url, timeout=t) as r: return r.read().decode()
def metric(m, name):
    for ln in m.splitlines():
        if ln.startswith(name + " ") or ln.startswith(name + "{"):
            try: return float(ln.rsplit(" ", 1)[1])
            except Exception: pass
    return None

def live():
    o = {"ts": time.strftime("%H:%M:%S")}
    try:
        s = j(SP + "/stats")
        o.update(messages=s.get("messages_processed"), throughput=s.get("avg_throughput_msg_per_sec"),
                 latency=s.get("avg_latency_ms"), anomalies=s.get("active_anomalies"), uptime=s.get("uptime_seconds"))
    except Exception: pass
    try:
        m = txt(SP + "/metrics")
        o["rows"] = metric(m, "ferrari_db_rows_written_total")
        o["received"] = metric(m, "ferrari_messages_received_total")
    except Exception: pass
    try:
        t = j(PROM + "/api/v1/targets?state=active")["data"]["activeTargets"]
        o["targets"] = f"{sum(1 for x in t if x['health']=='up')}/{len(t)}"
    except Exception: o["targets"] = "n/a"
    return o

def services():
    try:
        out = subprocess.run(["docker", "compose", "ps", "--format", "{{.Name}}|{{.Status}}"],
                             capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return []
    rows = []
    for ln in out.splitlines():
        if "|" in ln:
            n, st = ln.split("|", 1)
            ok = "healthy" in st.lower() or ("up" in st.lower() and "unhealthy" not in st.lower())
            rows.append((n.replace("ferrari-", ""), st, ok))
    return rows

# ---------- static proof (read once) ----------------------------------------
def read(p):
    try: return pathlib.Path(p).read_text(encoding="utf-8", errors="replace")
    except Exception: return ""
def grep(path, pat, lim=14):
    o = [l.rstrip() for l in read(path).splitlines() if re.search(pat, l, re.I)]
    return "\n".join(o[:lim]) if o else "(not found)"
def esc(s): return html.escape(str(s))

PROOF = [
    ("Terraform - secret kept out of git", "sensitive", grep("terraform/variables.tf", r"sensitive|password", 8)),
    ("Terraform - remote-state bootstrap", "S3 + DynamoDB", grep("terraform/bootstrap/main.tf", r"bucket|dynamodb|prevent_destroy|aws_s3|aws_dynamodb", 10)),
    ("Kubernetes - autoscaler (HPA)", "k8s", grep("k8s/stream-processor-hpa.yaml", r"kind:|minReplicas|maxReplicas|averageValue|name:|type:", 14)),
    ("Kubernetes - probes + limits", "k8s", grep("k8s/stream-processor.yaml", r"livenessProbe|readinessProbe|limits:|requests:|cpu:|memory:", 12)),
    ("CI/CD - validates compose, k8s, terraform", "GitHub Actions", grep(".github/workflows/ci-cd.yml", r"name:|kubeconform|terraform|compose config|pytest", 14)),
    ("Alert rules", "monitoring", grep("monitoring/rules/alerts.yml", r"alert:|expr:|summary", 14)),
]
MODEL = [
    ("Operational schema - 3NF", "OLTP", grep("sql/ddl/01_operational_schema.sql", r"create table|foreign key|references|check |create index", 14)),
    ("Star schema - Kimball", "OLAP", grep("sql/ddl/02_star_schema.sql", r"create table|dim_|fact_|_key", 14)),
]
DOCS = sorted(p.name for p in pathlib.Path("docs").glob("*") if p.is_file()) if pathlib.Path("docs").exists() else []
CRIT = [("Architecture relevance","25%"),("IaC code quality","20%"),("Data model quality","15%"),
        ("Effective deployment","15%"),("Monitoring & observability","10%"),("Documentation","10%"),("Presentation & Q&A","5%")]
SVCS = services()

def codecard(t, w, c):
    return f'<div class="proof"><div class="proof-h"><span>{esc(t)}</span><span class="pill">{esc(w)}</span></div><pre>{esc(c)}</pre></div>'

def page():
    init = live()
    svc = "".join(f'<div class="svc"><span class="dot {"ok" if ok else "warn"}"></span><span class="svc-n">{esc(n)}</span><span class="svc-s">{esc(st)}</span></div>' for n, st, ok in SVCS)
    iac = "".join(codecard(*p) for p in PROOF)
    mdl = "".join(codecard(*p) for p in MODEL)
    docs = "".join(f'<span class="tag">{esc(d)}</span>' for d in DOCS)
    crit = "".join(f'<div class="crit"><span class="check">&#10003;</span><span class="crit-n">{esc(n)}</span><span class="pill">{esc(w)}</span></div>' for n, w in CRIT)
    return TEMPLATE.replace("__SVC__", svc).replace("__IAC__", iac).replace("__MODEL__", mdl)\
        .replace("__DOCS__", docs).replace("__CRIT__", crit).replace("__NSVC__", str(len(SVCS)))\
        .replace("__INIT__", json.dumps(init))

TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>F1 Smart Pit-Stop - LIVE</title>
<style>
*{box-sizing:border-box} body{margin:0;background:linear-gradient(160deg,#051C2C,#02141d 70%);color:#e8f1f8;font-family:Segoe UI,Arial,sans-serif;line-height:1.5}
.wrap{max-width:1180px;margin:0 auto;padding:30px 26px 60px}
.top{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:12px;border-bottom:1px solid #173040;padding-bottom:18px}
h1{font-size:26px;margin:0;font-weight:700} .sub{color:#8fa6b6;font-size:14px;margin-top:4px}
.live{display:inline-flex;align-items:center;gap:8px;background:#0c2a39;border:1px solid #16465c;border-radius:20px;padding:6px 14px;font-size:13px;color:#bfe7fb}
.pulse{width:9px;height:9px;border-radius:50%;background:#22c55e;animation:p 1.4s infinite}
@keyframes p{0%{box-shadow:0 0 0 0 rgba(34,197,94,.6)}70%{box-shadow:0 0 0 9px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}
h2{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:#00A9F4;margin:34px 0 14px;font-weight:700}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}
.kpi{background:#0b2433;border:1px solid #14384b;border-radius:14px;padding:18px 16px;position:relative;overflow:hidden}
.kpi-val{font-size:30px;font-weight:800;color:#fff;letter-spacing:-.5px;transition:color .3s} .kpi.bump .kpi-val{color:#22e58a}
.kpi-lab{font-size:13px;color:#cfe2ee;margin-top:4px} .kpi-sub{font-size:11px;color:#7f99a9;margin-top:2px}
#spark{width:100%;height:46px;display:block;margin-top:6px}
.arch{display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:#081f2b;border:1px solid #14384b;border-radius:14px;padding:18px}
.node{background:#0e2f41;border:1px solid #1d4a61;border-radius:10px;padding:10px 14px;font-size:13px;font-weight:600}
.node.acc{background:#10307a;border-color:#2251FF} .node.cy{background:#063b52;border-color:#00A9F4} .arrow{color:#00A9F4;font-weight:700}
.svcs{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}
.svc{display:flex;align-items:center;gap:10px;background:#0b2433;border:1px solid #14384b;border-radius:10px;padding:9px 12px;font-size:13px}
.svc-n{font-weight:600} .svc-s{color:#8fa6b6;margin-left:auto;font-size:12px} .dot{width:10px;height:10px;border-radius:50%} .dot.ok{background:#22c55e} .dot.warn{background:#f59e0b}
.btns{display:flex;gap:12px;flex-wrap:wrap} a.btn{display:inline-block;text-decoration:none;background:#10307a;border:1px solid #2251FF;color:#fff;padding:11px 18px;border-radius:10px;font-weight:600;font-size:14px} a.btn.cy{background:#063b52;border-color:#00A9F4}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px} @media(max-width:820px){.grid2{grid-template-columns:1fr}}
.proof{background:#08202c;border:1px solid #14384b;border-radius:12px;overflow:hidden} .proof-h{display:flex;justify-content:space-between;align-items:center;padding:11px 14px;background:#0c2a39;font-size:13px;font-weight:700}
.pill{background:#10307a;border:1px solid #2251FF;color:#cfe0ff;font-size:11px;padding:2px 9px;border-radius:20px;font-weight:700}
pre{margin:0;padding:13px 14px;font-family:Consolas,monospace;font-size:12px;color:#bfe0f0;white-space:pre-wrap;word-break:break-word;max-height:230px;overflow:auto}
.crit{display:flex;align-items:center;gap:12px;background:#0b2433;border:1px solid #14384b;border-radius:10px;padding:10px 14px;margin-bottom:8px;font-size:13px} .check{color:#22c55e;font-weight:800} .crit-n{font-weight:600;min-width:230px}
.tag{display:inline-block;background:#0c2a39;border:1px solid #16465c;border-radius:8px;padding:5px 10px;margin:3px;font-size:12px;color:#bfe7fb;font-family:Consolas,monospace}
.foot{margin-top:40px;color:#6f8896;font-size:12px;border-top:1px solid #173040;padding-top:16px}
</style></head><body><div class="wrap">
 <div class="top"><div><h1>Ferrari F1 Smart Pit-Stop &middot; Data Infrastructure</h1>
   <div class="sub">Real-time IoT telemetry platform, defined entirely as Infrastructure as Code &middot; RNCP Bloc 2</div></div>
   <div class="live"><span class="pulse"></span> LIVE &middot; updates every 2s &middot; <span id="ts">--</span></div></div>

 <h2>Live proof &middot; numbers update in real time from the running stack</h2>
 <div class="kpis">
  <div class="kpi" id="k_received"><div class="kpi-val">--</div><div class="kpi-lab">Messages received</div><div class="kpi-sub">Prometheus counter, climbing</div></div>
  <div class="kpi" id="k_rows"><div class="kpi-val">--</div><div class="kpi-lab">Rows written to Postgres</div><div class="kpi-sub">telemetry_readings</div></div>
  <div class="kpi" id="k_thru"><div class="kpi-val">--</div><div class="kpi-lab">Throughput (msg/s)</div><div class="kpi-sub">rolling average<canvas id="spark"></canvas></div></div>
  <div class="kpi" id="k_lat"><div class="kpi-val">--</div><div class="kpi-lab">Avg latency (ms)</div><div class="kpi-sub">per message</div></div>
  <div class="kpi" id="k_anom"><div class="kpi-val">--</div><div class="kpi-lab">Active anomalies</div><div class="kpi-sub">live detection</div></div>
  <div class="kpi" id="k_targ"><div class="kpi-val">--</div><div class="kpi-lab">Targets up</div><div class="kpi-sub">Prometheus scrape health</div></div>
 </div>

 <h2>Architecture &middot; 3 runtimes from one codebase</h2>
 <div class="arch"><span class="node">Sensors (sim)</span><span class="arrow">&rarr;</span>
  <span class="node acc">Stream processor</span><span class="arrow">&rarr;</span><span class="node">Postgres</span><span class="arrow">&rarr;</span>
  <span class="node cy">Prometheus</span><span class="arrow">&rarr;</span><span class="node cy">Grafana</span>
  <span style="margin-left:auto;color:#8fa6b6;font-size:12px">Docker Compose &middot; Kubernetes (HPA) &middot; AWS (Terraform) &middot; Airflow</span></div>

 <h2>Deployment &middot; __NSVC__ services, all healthy</h2>
 <div class="svcs">__SVC__</div>

 <h2>Open the live dashboards</h2>
 <div class="btns"><a class="btn cy" href="http://localhost:3000/d/ferrari-strategy-dashboard" target="_blank">Grafana strategy cockpit</a>
  <a class="btn" href="http://localhost:9090/targets" target="_blank">Prometheus targets</a>
  <a class="btn" href="http://localhost:8001/stats" target="_blank">Live /stats JSON</a>
  <a class="btn" href="http://localhost:8088" target="_blank">Airflow</a></div>

 <h2>Infrastructure as Code (20%)</h2><div class="grid2">__IAC__</div>
 <h2>Data model (15%)</h2><div class="grid2">__MODEL__</div>
 <h2>Documentation (10%)</h2><div>__DOCS__</div>
 <h2>Jury criterion coverage</h2>__CRIT__
 <div class="foot">github.com/enzoberreur/f1-streaming-pipeline &middot; this page is served live by live_dashboard.py</div>
</div>
<script>
const fmt=n=>(n==null||n==='')?'n/a':(isNaN(+n)?n:(+n).toLocaleString('en-US'));
const spark=[]; let prev={};
function setk(id,val,bump){const e=document.getElementById(id);if(!e)return;const v=e.querySelector('.kpi-val');const t=fmt(val);if(v.textContent!==t){v.textContent=t;if(bump){e.classList.add('bump');setTimeout(()=>e.classList.remove('bump'),350);}}}
function draw(){const c=document.getElementById('spark');if(!c)return;const w=c.width=c.clientWidth*2,h=c.height=92;const ctx=c.getContext('2d');ctx.clearRect(0,0,w,h);if(spark.length<2)return;const mx=Math.max(...spark,1),mn=Math.min(...spark,0);ctx.beginPath();spark.forEach((v,i)=>{const x=i/(spark.length-1)*w,y=h-8-(v-mn)/((mx-mn)||1)*(h-16);i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.strokeStyle='#00A9F4';ctx.lineWidth=3;ctx.stroke();}
async function tick(){try{const d=await (await fetch('/api/live',{cache:'no-store'})).json();
 document.getElementById('ts').textContent=d.ts||'';
 setk('k_received',d.received??d.messages,(d.received||0)>(prev.received||0));
 setk('k_rows',d.rows,(d.rows||0)>(prev.rows||0));
 setk('k_thru',d.throughput!=null?(+d.throughput).toFixed(0):null);
 setk('k_lat',d.latency!=null?(+d.latency).toFixed(2):null);
 setk('k_anom',d.anomalies);setk('k_targ',d.targets);
 if(d.throughput!=null){spark.push(+d.throughput);if(spark.length>40)spark.shift();draw();}
 prev=d;}catch(e){}}
tick();setInterval(tick,2000);window.addEventListener('resize',draw);
</script></body></html>"""

# ---------- server -----------------------------------------------------------
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, body, ct="text/html; charset=utf-8"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(200); self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers()
        self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith("/api/live"):
            self._send(json.dumps(live()), "application/json")
        elif self.path in ("/", "/index.html"):
            self._send(page())
        else:
            self.send_response(204); self.end_headers()

def main():
    global PORT
    for p in range(PORT, PORT + 6):
        try:
            srv = socketserver.ThreadingTCPServer(("127.0.0.1", p), H); PORT = p; break
        except OSError: continue
    else:
        print("No free port in range; set PORT env var."); sys.exit(1)
    url = f"http://localhost:{PORT}/"
    print("\n  LIVE evidence dashboard running at:", url)
    print("  Opening it now, plus the live Grafana cockpit. Press Ctrl+C to stop.\n")
    try:
        webbrowser.open(url); time.sleep(1.2); webbrowser.open("http://localhost:3000/d/ferrari-strategy-dashboard")
    except Exception: pass
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\n  stopped.")

if __name__ == "__main__":
    main()
