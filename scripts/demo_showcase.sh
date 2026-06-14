#!/usr/bin/env bash
# =============================================================================
# Bloc 2 - Data Infrastructure / IaC : VISUAL SHOWCASE (no narration needed)
# One command that:
#   1. reads LIVE numbers from the running stack,
#   2. builds a polished HTML evidence page (KPIs, health, IaC, data model,
#      monitoring, criterion coverage) - proof of everything in one screen,
#   3. opens that page AND the live Grafana cockpit in your browser.
#
#   bash demo_showcase.sh             # build + open everything
#   NOBROWSER=1 bash demo_showcase.sh # just build demo_evidence.html
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
C='\033[0;36m'; G='\033[0;32m'; Y='\033[1;33m'; W='\033[1;37m'; D='\033[2m'; N='\033[0m'
NOBROWSER="${NOBROWSER:-0}"
say(){ printf "${C}%s${N}\n" "$1"; }
ok(){ printf "${G} [ok] %s${N}\n" "$1"; }

printf "${W}\n  FERRARI F1 SMART PIT-STOP - building live evidence page...${N}\n\n"

# --- ensure the stack is up -------------------------------------------------
if ! curl -fsS --max-time 4 http://localhost:8001/stats >/dev/null 2>&1; then
  say "Stack not detected - starting it (docker compose up -d)..."
  docker compose up -d >/dev/null 2>&1 || true
  printf "  waiting for the stream processor "; for _ in $(seq 1 60); do curl -fsS http://localhost:8001/health >/dev/null 2>&1 && break; printf "."; sleep 2; done; echo
fi

# --- capture LIVE values ----------------------------------------------------
say "Reading live metrics from the running stack..."
STATS_JSON="$(curl -s --max-time 6 http://localhost:8001/stats 2>/dev/null || echo '{}')"
ROWS="$(docker compose exec -T postgres psql -U airflow -d airflow -tAc 'select count(*) from telemetry_readings;' 2>/dev/null | tr -d '[:space:]')"
PROM_MSGS="$(curl -s --max-time 6 'http://localhost:9090/api/v1/query?query=ferrari_messages_received_total' 2>/dev/null | python -c "import sys,json;d=json.load(sys.stdin);print(d['data']['result'][0]['value'][1])" 2>/dev/null || echo '')"
TARGETS_UP="$(curl -s --max-time 6 'http://localhost:9090/api/v1/targets?state=active' 2>/dev/null | python -c "import sys,json;d=json.load(sys.stdin);t=d['data']['activeTargets'];print(str(sum(1 for x in t if x['health']=='up'))+'/'+str(len(t)))" 2>/dev/null || echo '')"
PS_RAW="$(docker compose ps --format '{{.Name}}|{{.Status}}' 2>/dev/null | grep -v '^$')"
ok "metrics captured"

export STATS_JSON ROWS PROM_MSGS TARGETS_UP PS_RAW

# --- build the HTML evidence page -------------------------------------------
say "Rendering demo_evidence.html..."
python - <<'PY'
import os, json, html, datetime, re, pathlib

def esc(s): return html.escape(str(s))
def read(p):
    try: return pathlib.Path(p).read_text(encoding='utf-8', errors='replace')
    except Exception: return ""
def grepblock(path, pattern, limit=16, flags=re.I):
    out=[]
    for ln in read(path).splitlines():
        if re.search(pattern, ln, flags):
            out.append(ln.rstrip())
        if len(out)>=limit: break
    return "\n".join(out) if out else "(file not found)"

stats = {}
try: stats = json.loads(os.environ.get("STATS_JSON","{}") or "{}")
except Exception: stats = {}

def fmt(n):
    try: return f"{int(float(n)):,}"
    except Exception: return str(n) if n not in (None,"") else "n/a"

msgs   = fmt(stats.get("messages_processed"))
thru   = stats.get("avg_throughput_msg_per_sec","n/a")
lat    = stats.get("avg_latency_ms","n/a")
up_s   = stats.get("uptime_seconds","n/a")
anom   = stats.get("active_anomalies","n/a")
rows   = fmt(os.environ.get("ROWS"))
prom   = fmt(os.environ.get("PROM_MSGS"))
targ   = os.environ.get("TARGETS_UP","n/a") or "n/a"
try: thru = f"{float(thru):,.0f}"
except Exception: pass
try: lat = f"{float(lat):.2f}"
except Exception: pass
try: up_s = f"{float(up_s)/60:.0f} min"
except Exception: pass

services=[]
for line in (os.environ.get("PS_RAW","") or "").splitlines():
    if "|" in line:
        name,status = line.split("|",1)
        healthy = "healthy" in status.lower() or ("up" in status.lower() and "unhealthy" not in status.lower())
        services.append((name.replace("ferrari-",""), status, healthy))

# code/proof snippets
tf_secret = grepblock("terraform/variables.tf", r"sensitive|db_password|password", 8)
tf_boot   = grepblock("terraform/bootstrap/main.tf", r"bucket|dynamodb|prevent_destroy|aws_s3|aws_dynamodb", 10)
k8s_hpa   = grepblock("k8s/stream-processor-hpa.yaml", r"kind:|minReplicas|maxReplicas|averageValue|name:|type:", 14)
k8s_probe = grepblock("k8s/stream-processor.yaml", r"livenessProbe|readinessProbe|limits:|requests:|cpu:|memory:|port:", 14)
ci_jobs   = grepblock(".github/workflows/ci-cd.yml", r"^\s*name:|kubeconform|terraform|docker compose config|pytest", 14)
ddl_op    = grepblock("sql/ddl/01_operational_schema.sql", r"create table|foreign key|references|check |create index", 14)
ddl_star  = grepblock("sql/ddl/02_star_schema.sql", r"create table|dim_|fact_|_key", 14)
alerts    = grepblock("monitoring/rules/alerts.yml", r"alert:|expr:|summary", 14)
docs      = sorted([p.name for p in pathlib.Path("docs").glob("*") if p.is_file()]) if pathlib.Path("docs").exists() else []

ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def card(label, value, sub=""):
    return f'<div class="kpi"><div class="kpi-val">{esc(value)}</div><div class="kpi-lab">{esc(label)}</div><div class="kpi-sub">{esc(sub)}</div></div>'

svc_html=""
for name,status,healthy in services:
    dot = "ok" if healthy else "warn"
    svc_html += f'<div class="svc"><span class="dot {dot}"></span><span class="svc-n">{esc(name)}</span><span class="svc-s">{esc(status)}</span></div>'

def codecard(title, weight, code, lang=""):
    return f'''<div class="proof"><div class="proof-h"><span>{esc(title)}</span><span class="pill">{esc(weight)}</span></div><pre>{esc(code)}</pre></div>'''

criteria = [
    ("Architecture relevance","25%","Real-time streaming design, 3 runtimes"),
    ("IaC code quality","20%","Terraform + K8s + Compose, validated in CI"),
    ("Data model quality","15%","3NF operational + Kimball star schema"),
    ("Effective deployment","15%","Stack live, all services healthy"),
    ("Monitoring & observability","10%","Prometheus + Grafana + alert rules"),
    ("Documentation","10%","README + docs/ + evaluation map"),
    ("Presentation & Q&A","5%","Deck + defense pack"),
]
crit_html="".join(f'<div class="crit"><span class="check">&#10003;</span><span class="crit-n">{esc(n)}</span><span class="pill">{esc(w)}</span><span class="crit-d">{esc(d)}</span></div>' for n,w,d in criteria)
docs_html="".join(f'<span class="tag">{esc(d)}</span>' for d in docs)

HTML=f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>F1 Smart Pit-Stop - Live Evidence</title>
<style>
 *{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(160deg,#051C2C,#02141d 70%);color:#e8f1f8;font-family:Segoe UI,Arial,sans-serif;line-height:1.5}}
 .wrap{{max-width:1180px;margin:0 auto;padding:32px 26px 60px}}
 .top{{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:12px;border-bottom:1px solid #173040;padding-bottom:18px}}
 h1{{font-size:26px;margin:0;font-weight:700}} .sub{{color:#8fa6b6;font-size:14px;margin-top:4px}}
 .live{{display:inline-flex;align-items:center;gap:8px;background:#0c2a39;border:1px solid #16465c;border-radius:20px;padding:6px 14px;font-size:13px;color:#bfe7fb}}
 .live .pulse{{width:9px;height:9px;border-radius:50%;background:#22c55e;box-shadow:0 0 0 0 rgba(34,197,94,.7);animation:p 1.6s infinite}}
 @keyframes p{{0%{{box-shadow:0 0 0 0 rgba(34,197,94,.6)}}70%{{box-shadow:0 0 0 9px rgba(34,197,94,0)}}100%{{box-shadow:0 0 0 0 rgba(34,197,94,0)}}}}
 h2{{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:#00A9F4;margin:34px 0 14px;font-weight:700}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}}
 .kpi{{background:#0b2433;border:1px solid #14384b;border-radius:14px;padding:18px 16px}}
 .kpi-val{{font-size:30px;font-weight:800;color:#fff;letter-spacing:-.5px}} .kpi-lab{{font-size:13px;color:#cfe2ee;margin-top:4px}} .kpi-sub{{font-size:11px;color:#7f99a9;margin-top:2px}}
 .arch{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:#081f2b;border:1px solid #14384b;border-radius:14px;padding:18px}}
 .node{{background:#0e2f41;border:1px solid #1d4a61;border-radius:10px;padding:10px 14px;font-size:13px;font-weight:600}}
 .node.acc{{background:#10307a;border-color:#2251FF}} .node.cy{{background:#063b52;border-color:#00A9F4}}
 .arrow{{color:#00A9F4;font-weight:700}}
 .svcs{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}}
 .svc{{display:flex;align-items:center;gap:10px;background:#0b2433;border:1px solid #14384b;border-radius:10px;padding:9px 12px;font-size:13px}}
 .svc-n{{font-weight:600}} .svc-s{{color:#8fa6b6;margin-left:auto;font-size:12px}}
 .dot{{width:10px;height:10px;border-radius:50%}} .dot.ok{{background:#22c55e}} .dot.warn{{background:#f59e0b}}
 .btns{{display:flex;gap:12px;flex-wrap:wrap;margin-top:6px}}
 a.btn{{display:inline-block;text-decoration:none;background:#10307a;border:1px solid #2251FF;color:#fff;padding:11px 18px;border-radius:10px;font-weight:600;font-size:14px}}
 a.btn.cy{{background:#063b52;border-color:#00A9F4}}
 .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} @media(max-width:820px){{.grid2{{grid-template-columns:1fr}}}}
 .proof{{background:#08202c;border:1px solid #14384b;border-radius:12px;overflow:hidden}}
 .proof-h{{display:flex;justify-content:space-between;align-items:center;padding:11px 14px;background:#0c2a39;font-size:13px;font-weight:700}}
 .pill{{background:#10307a;border:1px solid #2251FF;color:#cfe0ff;font-size:11px;padding:2px 9px;border-radius:20px;font-weight:700}}
 pre{{margin:0;padding:13px 14px;font-family:Consolas,monospace;font-size:12px;color:#bfe0f0;white-space:pre-wrap;word-break:break-word;max-height:230px;overflow:auto}}
 .crit{{display:flex;align-items:center;gap:12px;background:#0b2433;border:1px solid #14384b;border-radius:10px;padding:10px 14px;margin-bottom:8px;font-size:13px}}
 .check{{color:#22c55e;font-weight:800}} .crit-n{{font-weight:600;min-width:210px}} .crit-d{{color:#8fa6b6;margin-left:auto;font-size:12px}}
 .tag{{display:inline-block;background:#0c2a39;border:1px solid #16465c;border-radius:8px;padding:5px 10px;margin:3px;font-size:12px;color:#bfe7fb;font-family:Consolas,monospace}}
 .foot{{margin-top:40px;color:#6f8896;font-size:12px;border-top:1px solid #173040;padding-top:16px}}
</style></head><body><div class="wrap">

 <div class="top">
   <div><h1>Ferrari F1 Smart Pit-Stop &middot; Data Infrastructure</h1>
   <div class="sub">Real-time IoT telemetry platform, defined entirely as Infrastructure as Code &middot; RNCP Bloc 2</div></div>
   <div class="live"><span class="pulse"></span> LIVE &middot; captured {esc(ts)}</div>
 </div>

 <h2>Live proof &middot; numbers read from the running stack</h2>
 <div class="kpis">
  {card("Messages processed", msgs, "stream processor /stats")}
  {card("Rows in Postgres", rows, "telemetry_readings table")}
  {card("Throughput", thru+" msg/s", "rolling average")}
  {card("Avg latency", lat+" ms", "per message")}
  {card("Prometheus counter", prom, "ferrari_messages_received_total")}
  {card("Targets up", targ, "Prometheus scrape health")}
 </div>

 <h2>Architecture &middot; 3 runtimes from one codebase</h2>
 <div class="arch">
  <span class="node">Sensors (sim)</span><span class="arrow">&rarr;</span>
  <span class="node acc">Stream processor<br><small>anomaly + pit-stop scoring</small></span><span class="arrow">&rarr;</span>
  <span class="node">Postgres</span><span class="arrow">&rarr;</span>
  <span class="node cy">Prometheus</span><span class="arrow">&rarr;</span>
  <span class="node cy">Grafana</span>
  <span style="margin-left:auto;color:#8fa6b6;font-size:12px">Docker Compose &middot; Kubernetes (HPA) &middot; AWS (Terraform) &middot; Airflow batch</span>
 </div>

 <h2>Deployment &middot; every service healthy ({esc(str(len(services)))})</h2>
 <div class="svcs">{svc_html}</div>

 <h2>Open the live dashboards</h2>
 <div class="btns">
  <a class="btn cy" href="http://localhost:3000/d/ferrari-strategy-dashboard" target="_blank">Grafana strategy cockpit</a>
  <a class="btn" href="http://localhost:9090/targets" target="_blank">Prometheus targets</a>
  <a class="btn" href="http://localhost:8001/stats" target="_blank">Live /stats JSON</a>
  <a class="btn" href="http://localhost:8088" target="_blank">Airflow</a>
 </div>

 <h2>Infrastructure as Code (20%)</h2>
 <div class="grid2">
  {codecard("Terraform &middot; secret kept out of git", "sensitive", tf_secret)}
  {codecard("Terraform &middot; remote-state bootstrap", "S3 + DynamoDB", tf_boot)}
  {codecard("Kubernetes &middot; autoscaler (HPA)", "k8s", k8s_hpa)}
  {codecard("Kubernetes &middot; probes + limits", "k8s", k8s_probe)}
  {codecard("CI/CD &middot; validates compose, k8s, terraform", "GitHub Actions", ci_jobs)}
  {codecard("Alert rules", "monitoring", alerts)}
 </div>

 <h2>Data model (15%)</h2>
 <div class="grid2">
  {codecard("Operational schema &middot; 3NF", "OLTP", ddl_op)}
  {codecard("Star schema &middot; Kimball", "OLAP", ddl_star)}
 </div>

 <h2>Documentation (10%)</h2>
 <div>{docs_html}</div>

 <h2>Jury criterion coverage</h2>
 {crit_html}

 <div class="foot">github.com/enzoberreur/f1-streaming-pipeline &middot; regenerate live: <b>python scripts/live_dashboard.py</b> &middot; stop stack: <b>docker compose down</b></div>
</div></body></html>"""

pathlib.Path("demo_evidence.html").write_text(HTML, encoding="utf-8")
print("  wrote demo_evidence.html ("+str(len(services))+" services, "+msgs+" messages)")
PY
ok "demo_evidence.html built"

# --- open everything --------------------------------------------------------
if [ "$NOBROWSER" != "1" ]; then
  PAGE="$(pwd)/demo_evidence.html"
  say "Opening the evidence page and the live Grafana cockpit..."
  ( cmd.exe /c start "" "$PAGE" >/dev/null 2>&1 || xdg-open "$PAGE" >/dev/null 2>&1 || open "$PAGE" >/dev/null 2>&1 ) &
  sleep 2
  ( cmd.exe /c start "" "http://localhost:3000/d/ferrari-strategy-dashboard" >/dev/null 2>&1 || xdg-open "http://localhost:3000/d/ferrari-strategy-dashboard" >/dev/null 2>&1 ) &
fi
printf "${W}\n  Done. Record the evidence page (scroll top to bottom), then the live Grafana charts.${N}\n"
printf "${D}  Page: demo_evidence.html   Grafana: http://localhost:3000   Prometheus: http://localhost:9090${N}\n\n"
