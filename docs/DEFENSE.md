# Defense pack - Bloc 2 (Architecture de Données)

Project: **Ferrari F1 IoT Smart Pit-Stop**. This is your Q&A preparation for the
oral (5 min talk + 15 min Q&A). It is written in English to match the repository
documentation; if your oral is in French, ask and these can be translated.

How to use it: read the 30-second pitch until it is automatic, then rehearse the
answers out loud. The jury will probe the highest-weight criteria first
(Architecture 25%, IaC 20%), so those sections are deepest.

---

## 30-second opening pitch

"This project is a real-time telemetry and monitoring platform modelled on a
Formula 1 pit wall. A sensor simulator produces high-frequency car telemetry for a
full 20-car grid; a stream processor detects anomalies (brake and tyre overheating)
and computes a pit-stop strategy score in real time; Prometheus and Grafana give
the engineers live dashboards. The whole system is defined as code: Docker Compose
for development, Kubernetes for production, and Terraform for the cloud
infrastructure. My focus for this bloc was the architecture and its
reproducibility: every layer is documented, deployable with one command, and
validated automatically in CI."

---

## Architecture and design

**Q: Walk me through the architecture end to end.**
A: Three layers. Ingestion is the `sensor-simulator`, which emits telemetry for 20
cars over HTTP and exposes its own Prometheus metrics. Processing is the
`stream-processor` (FastAPI): it keeps a short sliding time window per car, raises
a critical anomaly when a brake or tyre stays above threshold for the whole window,
and scores pit-stop urgency from tyre wear, pace loss, brake degradation, and
active anomalies. Observability is Prometheus scraping both services plus five
Grafana dashboards. Airflow handles the batch and orchestration side. It runs on
Docker Compose for dev and Kubernetes for prod.

**Q: Why did you separate the simulator from the processor?**
A: Separation of concerns and independent scaling. The simulator is a load source;
the processor is the stateful, CPU-bound consumer. In Kubernetes only the processor
is behind a Horizontal Pod Autoscaler (2 to 10 replicas), because that is the part
that needs to scale with message volume. Keeping them separate also let me put a
NetworkPolicy around the processor so only the simulator and the ops namespace can
reach it.

**Q: Is this event-driven or request-driven, and why?**
A: In this bloc the transport is HTTP plus Prometheus pull, deliberately, to keep
the architecture readable and the infrastructure light for a demo. The design is
written so the transport is swappable: at production scale you would put a message
broker (Kafka) between the two, which is exactly the pattern I built in the
real-time pipelines bloc. I made that a conscious tradeoff rather than an omission.

## Technology choices and tradeoffs

**Q: Why Prometheus and Grafana rather than a cloud monitoring service?**
A: They are the de facto open standard, they run identically on a laptop and in the
cluster, and the pull model plus PromQL fit time-series telemetry well. A managed
service would lock the demo to one cloud and hide the mechanics I want the jury to
see. The tradeoff is that I operate them myself, which I accept at this scale.

**Q: Why both Docker Compose and Kubernetes?**
A: They serve two environments. Compose is the fast inner-loop for development: one
command brings up the whole stack. Kubernetes is the production target: it adds
self-healing, autoscaling, resource quotas, and network policy. Using both shows
the dev-to-prod path rather than just one runtime.

**Q: Why Terraform, and which cloud?**
A: Terraform because it is declarative, cloud-agnostic in style, and the plan/apply
workflow makes infrastructure reviewable. I targeted AWS: a VPC with public
subnets, an EC2 application server bootstrapped with cloud-init, and a managed RDS
PostgreSQL for the operational data. CI runs `terraform validate` on every commit
so the code never drifts from being applyable.

## Data model

**Q: Explain your data model.**
A: Two schemas for two jobs. An operational 3NF schema (teams, drivers, cars,
circuits, sessions, laps, telemetry readings, pit stops, anomalies) captures the
live domain without redundancy. An analytics star schema (conformed dimensions plus
fact tables for telemetry, laps, and pit stops) is shaped for fast aggregation and
dashboards. The ERD and the rationale are in `docs/DATA_MODEL.md`.

**Q: Today the processor writes metrics, not rows to PostgreSQL. Why model the schema then?**
A: Good catch, and I am explicit about it. The relational model is the target
operational design; in the current build the live path is optimised for monitoring
(Prometheus), and the RDS instance plus the DDL are the foundation for persistence.
The next increment is a writer from the processor into the operational schema and a
loader into the star schema. I would rather show a sound model and name the gap than
hide it.

## Scale, performance, and cost

**Q: How does this scale?**
A: Horizontally on the processing tier. The HPA scales the stream-processor on CPU
and on a custom Prometheus metric (messages received per second), from 2 to 10
replicas. The simulator can fan out to more instances to raise load. The bounded
parts are the single RDS instance and Prometheus storage, which I would address with
a read replica and longer-retention remote storage.

**Q: What would break first under 10x load?**
A: The single stream-processor replica set hitting CPU, which the HPA absorbs up to
its ceiling, then Prometheus ingestion and the single database. I would raise the
HPA ceiling, sample or aggregate metrics, and move to a managed time-series backend.

**Q: What does this cost to run?**
A: At demo scale it is a small EC2 instance plus a small RDS instance, on the order
of tens of dollars a month. The point of the IaC is that cost is visible and
adjustable through a few Terraform variables (instance types, RDS class) rather than
hidden in console clicks.

## Security and operations

**Q: How is the system secured?**
A: The stream-processor requires an API key (configurable header), so the ingestion
endpoint is not open. In Kubernetes a NetworkPolicy denies traffic by default and
only allows the simulator and the ops namespace to reach the processor. RDS is
private (no public access). Secrets are Kubernetes Secrets, not baked into images.
This is summarised in `docs/security-and-compliance.md`.

**Q: How do you deploy and roll back?**
A: Locally `docker compose up`. On the cluster `kubectl apply -f k8s/`, where every
workload has liveness and readiness probes and resource limits, so a bad pod is
caught and a rollout can be reverted with `kubectl rollout undo`. The cloud base is
`terraform apply`. CI validates compose, the Kubernetes manifests (kubeconform), and
Terraform before anything ships.

**Q: What do you monitor, and what alerts fire?**
A: Throughput, processing latency, active anomalies, and the pit-stop score per car,
on five Grafana dashboards. Prometheus alert rules cover the operational signals.
The HPA itself is a feedback loop: rising message rate scales the processor out.

## Reflection

**Q: What was the hardest part?**
A: Making the Kubernetes layer genuinely coherent. It is easy to write manifests
that pass schema validation but do not actually deploy the app. I made sure every
workload has a Deployment and a Service, that the HPA and Ingress point at real
objects, and that probes and limits are set, then verified the cross-references.

**Q: What would you do differently or next?**
A: Three things: put a broker (Kafka) on the live path for true backpressure;
persist the operational schema and load the star schema so the analytics side runs
on real rows; and add a remote Terraform backend plus separate dev and prod
environments. None are hard, they are the next iteration.

**Q: What are the limits of this project?**
A: It is a simulation, not real cars, and the analytics tables are modelled but not
yet populated by the live path. The architecture, the IaC, and the monitoring are
production-shaped; the data persistence is the part I would build out next.
