# Loom Demo Script - Bloc 2 (Data Infrastructure / IaC)

**Goal:** in one take, show everything the jury grades: the architecture, the
Infrastructure as Code, a live deployment, the data model, monitoring and
observability, and the documentation.

**Required flow:** deployed infrastructure -> components walkthrough -> monitoring
in action -> proof it works.

**Target length:** 4 to 5 minutes. Record at 1920x1080, browser zoom ~110%.

**Repo:** `github.com/enzoberreur/f1-streaming-pipeline` (Ferrari F1 IoT smart
pit-stop). Internal metrics and namespaces use the `ferrari_` / `ferrari-f1`
prefixes; the deck brand is "F1 Smart Pit-Stop".

---

## Pre-flight (off camera, so the recording stays smooth)

1. Open a terminal where `docker` works, at the repo root.
2. Pre-build images so the on-camera start is fast:
   `docker compose build`
3. Have these browser tabs ready but not yet loaded: Grafana `http://localhost:3000`,
   Prometheus `http://localhost:9090`, Airflow `http://localhost:8088`.
4. Open your editor on the repo so you can show files quickly.
5. (Optional, for the autoscaling shot) have a local cluster ready:
   `kubectl get nodes` returns a node, and you can run `./deploy-k8s.sh dev`.
6. Have the deck open to the architecture slide for the 20-second intro.

---

## 0:00 - 0:30 - Intro and architecture  *(criterion: Architecture relevance, 25%)*

**SAY:** "This is the data infrastructure for an F1 smart pit-stop platform.
On-car sensors stream telemetry through a stream processor that detects anomalies
and scores pit-stop strategy in real time, writes to Postgres, and exposes
everything to Prometheus and Grafana. The whole stack is Infrastructure as Code:
it runs as Docker Compose locally, on Kubernetes with autoscaling, and on AWS
through Terraform."

**SHOW:** the architecture diagram (`docs/ARCHITECTURE.md` or the deck slide):
sensor-simulator -> stream-processor -> Postgres + Prometheus -> Grafana, with
Airflow for the batch layer.

---

## 0:30 - 1:15 - Infrastructure as Code  *(criterion: IaC code quality, 20%)*

**SAY:** "The same architecture is defined three ways, all in code." Move quickly.

**SHOW + CMD:**
- Terraform: open `terraform/` and scroll `network.tf`, `compute.tf`,
  `database.tf`. Point out the `sensitive` database password and tfvars kept out
  of git, and the remote-state bootstrap in `terraform/bootstrap/` (S3 + DynamoDB
  with `prevent_destroy`). If terraform is installed you can validate on camera
  (`terraform -chdir=terraform init -backend=false && terraform -chdir=terraform validate`);
  if not, skip it, because CI already validates it (next bullet).
- Kubernetes: open `k8s/` and show `stream-processor.yaml` (liveness/readiness
  probes, resource limits), `stream-processor-hpa.yaml` (autoscaling on a custom
  Prometheus metric), `networkpolicy.yaml` and `rbac.yaml`.
- "And every push runs this in CI": open the green run on the GitHub **Actions**
  tab (or `.github/workflows/ci-cd.yml`). It lints and unit-tests, builds and
  pushes the image to GHCR, validates the compose file (`docker compose config`),
  runs `kubeconform` on the k8s manifests, and runs the Terraform job. This is your
  authoritative IaC validation, so the demo does not depend on a local terraform.

---

## 1:15 - 2:00 - Deploy it live  *(criterion: Effective deployment, 15%)*

**SAY:** "Let me bring the stack up from nothing."

**CMD:**
```
docker compose up -d        # images are pre-built, so this is fast
docker compose ps           # everything healthy
```
**SHOW:** the `ps` output with all services Up/healthy.

**SAY (optional Kubernetes shot):** "The same stack deploys to Kubernetes."
**CMD (optional):**
```
./deploy-k8s.sh dev
kubectl get pods -n ferrari-f1
```

---

## 2:00 - 2:45 - Telemetry flowing end to end  *(criteria: Architecture 25% + proof it works)*

**SAY:** "Telemetry is already flowing. The processor counts what it ingests and
scores it live."

**CMD:**
```
curl -s http://localhost:8001/stats | jq .       # messages_processed climbing
curl -s http://localhost:8001/metrics | grep -E '^ferrari_(messages_received_total|anomalies_detected_total|pitstop_score|current_throughput)'
```
**SHOW:** run `/stats` twice a few seconds apart so the counter visibly climbs;
then the `ferrari_` metrics with live anomaly counts and per-car pit-stop scores.

**SAY:** "Those writes land in Postgres" (hundreds of thousands of rows already).
**CMD (optional):**
```
docker compose exec postgres psql -U airflow -d airflow -c "select count(*) from telemetry_readings;"
```

---

## 2:45 - 3:30 - Data model  *(criterion: Data model quality, 15%)*

**SAY:** "The data is modeled in two layers: a normalized operational schema for
the live writes, and a Kimball star schema for analytics."

**SHOW:**
- `docs/DATA_MODEL.md`: the ERD and the star-schema diagram with the rationale
  table.
- `sql/ddl/01_operational_schema.sql`: third normal form, foreign keys, CHECK
  constraints, and the composite index on the dominant query.
- `sql/ddl/02_star_schema.sql`: conformed dimensions, fact tables, surrogate keys,
  SCD2-ready design.

**SAY:** "Operational writes stay fast and consistent; the star schema is what the
dashboards and any BI tool query."

---

## 3:30 - 4:15 - Monitoring and observability  *(criterion: Monitoring, 10%)*

**SHOW:**
- Grafana `http://localhost:3000` (admin/admin) -> the strategy cockpit
  `http://localhost:3000/d/ferrari-strategy-dashboard`: live throughput, anomalies,
  per-car pit-stop scores moving.
- Prometheus `http://localhost:9090` -> Status > Targets (all up), then Alerts:
  open `monitoring/rules/alerts.yml` to show the four alert rules including the
  business alert on a low pit-stop score.

**SAY (optional autoscaling highlight):** "Under load, the HPA scales the processor."
**CMD (optional):**
```
kubectl get hpa -n ferrari-f1 -w     # show replicas increase as load rises
```

---

## 4:15 - 4:45 - Documentation  *(criterion: Documentation, 10%)*

**SHOW:** the repo `README.md` (quick start, services, "Pourquoi cette
architecture" justification, scalability, troubleshooting), then the `docs/` folder:
`ARCHITECTURE.md`, `DATA_MODEL.md`, `security-and-compliance.md`, `airflow-guide.md`,
`DEFENSE.md` (the Q&A pack), `EVALUATION.md` (criterion-to-evidence map).

**SAY:** "Every grading criterion maps to a file in `docs/EVALUATION.md`, and there
is a defense pack for the Q&A."

---

## 4:45 - 5:00 - Wrap  *(criterion: Presentation and Q&A, 5%)*

**SAY:** "Architecture, Infrastructure as Code across three runtimes, a live
deployment, a normalized plus star-schema data model, real-time monitoring with
autoscaling, and full documentation. Everything is in the repo." Show the repo
tree briefly (`terraform/ k8s/ sql/ monitoring/ docs/`).

Stop the stack after recording: `docker compose down` (or `make clean`).

---

## Rubric coverage map

| Criterion | Weight | Shown at |
|---|---|---|
| Architecture relevance | 25% | 0:00, 2:00 |
| Data model quality | 15% | 2:45 |
| IaC code quality | 20% | 0:30 |
| Effective deployment | 15% | 1:15 |
| Monitoring and observability | 10% | 3:30 |
| Documentation | 10% | 4:15 |
| Presentation and Q&A | 5% | 0:00 + 4:45 |

## Shot checklist
- [ ] Architecture diagram
- [ ] Terraform validate + k8s manifests + CI green
- [ ] `docker compose up -d` + `ps` healthy (and optional k8s deploy)
- [ ] `/stats` counter climbing + `ferrari_` live metrics
- [ ] ERD + star schema (DATA_MODEL.md, sql/ddl 01 and 02)
- [ ] Grafana strategy dashboard + Prometheus alerts (and optional HPA scale)
- [ ] README + docs/ tour
- [ ] Repo tree on the wrap

## Paste the Loom URL into
- `README.md` (top, a "Demo video" line)
- `docs/EVALUATION.md` (where the demo is referenced)
- The closing slide of `Presentation.pptx`
