# Evaluation criteria coverage - Bloc 2 (Architecture de Données)

This table maps every jury grading criterion to exactly where it is demonstrated,
across the three graded artifacts: the slide deck, this repository, and the Loom
demo. Use it during the defense so each point is easy to verify.

| Criterion | Weight | Where it is proven |
|-----------|:------:|--------------------|
| Architecture relevance | 25% | `README.md` (architecture overview + justification of each tech choice), `docs/security-and-compliance.md`, deck "Architecture" section. Layered design: `sensor-simulator` -> `stream-processor` (FastAPI) -> Prometheus/Grafana, batch orchestration via `airflow/`, two runtimes (`docker-compose.yml` for dev, `k8s/` for prod). |
| Data model | 15% | `sql/ddl/01_operational_schema.sql` (3NF operational schema), `sql/ddl/02_star_schema.sql` (analytics star schema), `docs/DATA_MODEL.md` (ERD + star schema diagrams + modelling rationale). |
| IaC quality | 20% | `terraform/` (AWS VPC, EC2 app server with cloud-init, RDS PostgreSQL, security groups, outputs, `*.tfvars.example`), `k8s/` (Deployments, Services, HPA, Ingress, NetworkPolicy, ResourceQuota, LimitRange, RBAC), `docker-compose.yml`. All validated in CI (`.github/workflows/ci-cd.yml`: `terraform validate`, `kubeconform`, `docker compose config`). |
| Effective deployment | 15% | Local: `docker compose up`. Cluster: `kubectl apply -f k8s/` (every workload has probes + resource limits, HPA scales 2->10). Cloud: `terraform apply`. **Loom**: stack coming up, services healthy, autoscaling reacting to load. |
| Monitoring | 10% | Prometheus scrape config + alerting rules (`monitoring/rules/alerts.yml`), 5 Grafana dashboards (`monitoring/grafana_dashboard_*.json`), HPA driven by a custom Prometheus metric. **Loom**: live dashboards under telemetry load. |
| Documentation | 10% | `README.md`, `docs/DATA_MODEL.md`, `docs/airflow-guide.md`, `docs/security-and-compliance.md`, `docs/DEFENSE.md`, per-service READMEs, `terraform/README.md`, `LICENSE`. |
| Presentation | 5% | `Presentation.pptx` (merged deck) + 5-minute oral. See `docs/DEFENSE.md` for the Q&A. |

**Reading tip for the jury:** the highest weights are Architecture (25%) and IaC (20%).
The architecture rationale lives in the README and the deck; the IaC is in `terraform/`
and `k8s/`, and CI proves it is valid on every commit.
