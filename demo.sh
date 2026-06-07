#!/usr/bin/env bash
# One-shot demo for Bloc 2 - Ferrari F1 IoT Smart Pit-Stop.
# Boots the full stack, shows live telemetry + anomaly detection + pit-stop
# strategy scoring, then points at the monitoring dashboards. Built to be
# screen-recorded for the Loom.
#
# Usage:
#   bash demo.sh          # pause between steps (press Enter) - best for recording
#   AUTO=1 bash demo.sh   # no pauses, fixed sleeps - unattended run
#   bash demo.sh --open   # also open the dashboards in your browser
set -uo pipefail
cd "$(dirname "$0")"

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
AUTO="${AUTO:-0}"; OPEN=0
for a in "$@"; do case "$a" in --open) OPEN=1;; --auto) AUTO=1;; esac; done

step(){ echo; echo -e "${BLUE}==================================================${NC}"; echo -e "${BLUE}>> $1${NC}"; echo -e "${BLUE}==================================================${NC}"; }
ok(){ echo -e "${GREEN}[OK] $1${NC}"; }
warn(){ echo -e "${YELLOW}[!] $1${NC}"; }
pause(){ if [ "$AUTO" = "1" ]; then sleep "${1:-3}"; else echo; echo -e "${YELLOW}-- Press Enter to continue --${NC}"; read -r; fi; }
pp(){ if command -v jq >/dev/null 2>&1; then jq .; else python -m json.tool 2>/dev/null || cat; fi; }
open_url(){ [ "$OPEN" = "1" ] || return 0; ( cmd.exe /c start "" "$1" 2>/dev/null || xdg-open "$1" 2>/dev/null || open "$1" 2>/dev/null ) & }
wait_http(){ local url="$1" name="$2" t="${3:-120}" i=0; echo -n "Waiting for $name "; while [ "$i" -lt "$t" ]; do if curl -fsS "$url" >/dev/null 2>&1; then echo; ok "$name is up"; return 0; fi; echo -n "."; sleep 2; i=$((i+2)); done; echo; warn "$name not responding after ${t}s (continuing)"; return 1; }

command -v docker >/dev/null 2>&1 || { echo -e "${RED}docker not found on PATH. Open a terminal where 'docker' works and re-run.${NC}"; exit 1; }

step "Ferrari F1 IoT - one-shot demo"
echo "This will build + start the stack, show real-time telemetry and anomaly"
echo "detection, then open the monitoring dashboards."
pause 1

step "1/5  Deploy the full stack (Infrastructure as Code)"
echo "\$ docker compose up --build -d"
docker compose up --build -d
[ -f ./import-dashboard.sh ] && bash ./import-dashboard.sh --silent 2>/dev/null && ok "Grafana dashboards imported"
pause

step "2/5  Wait for services, then list them"
wait_http "http://localhost:8001/health" "stream-processor" 150
docker compose ps
pause

step "3/5  Telemetry is flowing (sensor-simulator -> stream-processor)"
echo "Polling the processor 3 times; watch messages_processed climb:"
for n in 1 2 3; do
  echo "--- sample $n ---"
  curl -fsS http://localhost:8001/stats | pp
  sleep 3
done
ok "Real-time ingestion confirmed"
pause

step "4/5  Anomaly detection + pit-stop strategy (Prometheus metrics)"
echo "\$ curl /metrics | grep ferrari_"
curl -fsS http://localhost:8001/metrics \
  | grep -E '^ferrari_(messages_received_total|anomalies_detected_total|pitstop_score|current_throughput)' \
  | head -30
ok "Anomalies + per-car pit-stop scores are being computed live"
pause

step "5/5  Monitoring dashboards"
cat <<'URLS'
  Grafana (admin/admin):     http://localhost:3000
    Strategy cockpit:        http://localhost:3000/d/ferrari-strategy-dashboard
  Prometheus:                http://localhost:9090
  Airflow web UI:            http://localhost:8080
  cAdvisor (containers):     http://localhost:8082
  Sensor simulator metrics:  http://localhost:8000/metrics
  Stream processor API:      http://localhost:8001
URLS
open_url "http://localhost:3000"
open_url "http://localhost:8001/stats"
pause

step "Demo complete"
echo "Stop the stack:   docker compose down"
echo "Reset everything: make clean"
