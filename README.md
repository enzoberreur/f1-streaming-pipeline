# Ferrari F1 IoT Smart Pit-Stop

Plateforme de télémétrie et de monitoring inspirée d'un mur des stands de Formule 1. Le dépôt rassemble :

- un simulateur de capteurs haute fréquence (HTTP + métriques Prometheus) ;
- un service de traitement (`stream-processor`) ;
- une stack d'observabilité (Prometheus + Grafana) ;
- des orchestrations Airflow pour la donnée batch.

L'objectif : fournir un environnement réaliste pour expérimenter des pipelines IoT/streaming et des tableaux de bord stratégiques.

---

## Démarrage rapide (tout en Docker)

Pré-requis : Docker, Docker Compose et `make`.

```bash
git clone https://github.com/enzoberreur/Automation_F1.git
cd Automation_F1
# Optionnel mais recommandé : définir la clé API utilisée entre le simulateur et le stream processor
export STREAM_PROCESSOR_API_KEY="change-me-before-prod"
make start
```

Cette commande :
1. arrête toute exécution précédente (`docker compose down --remove-orphans`) ;
2. reconstruit et démarre les conteneurs nécessaires ;
3. importe automatiquement les dashboards Grafana.

> Les identifiants par défaut sont `admin / admin` pour Grafana et Airflow. La clé API `STREAM_PROCESSOR_API_KEY` est partagée automatiquement entre le simulateur et le stream processor lorsqu'elle est définie dans l'environnement.

Une fois le stack prêt, accédez au poste de commande principal : <http://localhost:3000/d/ferrari-strategy-dashboard>.

Pour arrêter et nettoyer :

```bash
make stop
```

Pour repartir de zéro (conteneurs arrêtés + volumes supprimés) :

```bash
make clean
```

La commande supprime également les dossiers `__pycache__` générés par Python.

----

## Démarrage léger (simulateur seul)

Pour tester uniquement le flux de télémétrie :

```bash
cd sensor-simulator
pip install -r requirements.txt
python main.py
```

Le simulateur publie :
- la télémétrie sur `http://localhost:8001/telemetry` (attendez-vous à un message d'erreur si le `stream-processor` n'est pas démarré) ;
- les métriques Prometheus sur `http://localhost:8000/metrics`.

Consultez `sensor-simulator/README.md` pour un guide détaillé (configuration, métriques, anomalies simulées).

---

## Services & ports

| Service | Rôle | Port local |
|---------|------|------------|
| sensor-simulator | Génère la télémétrie F1 et les métriques Prometheus | `8000` (metrics) |
| stream-processor | Reçoit la télémétrie, calcule des KPIs et expose des API | `8001` |
| prometheus | Collecte toutes les métriques | `9090` |
| grafana | Tableaux de bord temps réel | `3000` |
| airflow | Orchestration batch & maintenance de données | `8080` |
| cadvisor | Observabilité des conteneurs | `8082` |

La configuration Docker Compose se trouve dans `docker-compose.yml`. Les manifestes Kubernetes sont disponibles dans `k8s/` si vous souhaitez déployer sur un cluster.

---

## Sécurité & conformité

- **Clé API obligatoire** : le flux `/telemetry` du `stream-processor` refuse toute requête ne comportant pas l'en-tête `X-Api-Key`. La clé est injectée via la variable d'environnement `STREAM_PROCESSOR_API_KEY` partagée avec le simulateur.
- **Limitation réseau Kubernetes** : `k8s/networkpolicy.yaml` autorise uniquement le simulateur, Airflow et les outils d'observabilité à contacter le stream processor sur le cluster.
- **Journalisation** : chaque refus d'authentification est loggué côté service pour faciliter les audits.
- **Documentation dédiée** : `docs/security-and-compliance.md` résume les bonnes pratiques (rotation de secrets, TLS, audit des rejets).

---

## Dashboards Grafana

Les définitions JSON des dashboards résident dans `monitoring/` :

- `grafana_dashboard_main.json` — vue opérations & thermique : vitesse, freins/pneus, anomalies, stratégie.
- `grafana_dashboard_strategy.json` — suivi détaillé des recommandations pit-stop (probabilité de fenêtre, état de la piste, timeline stratégie).
- `grafana_dashboard_data.json`, `grafana_dashboard_data_quality.json` — analyses complémentaires (débit, fraîcheur, qualité de données).

Importer manuellement :

```bash
./import-dashboard.sh
```

ou passer par l’UI Grafana (`Dashboards → Import`) en collant le contenu JSON.

---

## Métriques clés

Les dashboards s'appuient principalement sur :

- **Flux** : `ferrari_simulator_messages_generated_total`, `ferrari_simulator_messages_sent_total`, `ferrari_simulator_current_throughput_msg_per_sec` (toutes taguées par `car_id`, `team`, `driver`).
- **Thermique** : `ferrari_simulator_brake_temp_*_celsius`, `ferrari_simulator_tire_temp_*_celsius`, `ferrari_simulator_engine_temp_celsius`.
- **Pneus & carburant** : `ferrari_simulator_tire_wear_percent`, `ferrari_simulator_fuel_remaining_kg`.
- **Stratégie** : `ferrari_simulator_lap_time_seconds`, `ferrari_simulator_stint_health_score`, `ferrari_simulator_pit_window_probability`, `ferrari_simulator_surface_condition_state`, `ferrari_simulator_strategy_recommendation_state`.

Toutes les métriques exposées par le simulateur sont décrites dans `sensor-simulator/README.md`. Celles du `stream-processor` sont consultables via `http://localhost:8001/metrics`.

---

## Architecture (aperçu)

1. **Sensor Simulator** — orchestre 20 voitures (10 équipes officielles), applique anomalies et calcule des insights de stratégie.
2. **Stream Processor** — consomme les événements HTTP, calcule des KPI temps réel et persiste l’état.
3. **Prometheus** — scrappe le simulateur, le stream-processor, cAdvisor.
4. **Grafana** — visualise la télémétrie, les insights de stratégie et la santé système.
5. **Airflow** — planifie des jobs batch (relectures, calculs périodiques, tests de qualité).

Le document `ARCHITECTURE.md` fournit une description complète (diagrammes, flux détaillés, cas d'usage).

---

## Infrastructure as Code (Terraform)

Le dossier [`terraform/`](terraform/) provisionne l'infrastructure cloud sur AWS :
VPC + sous-réseaux multi-AZ, serveur EC2 (qui démarre la stack Docker via
cloud-init), base **PostgreSQL managée (RDS)** et security groups restrictifs.
Détails dans [`terraform/README.md`](terraform/README.md).

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # éditer
terraform init && terraform validate && terraform plan
terraform apply
```

Déploiement local / on-premise : `make start` (Docker Compose) ou les manifestes
[`k8s/`](k8s/). Une CI GitHub Actions ([`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml))
lint + build + publie les images, puis valide Compose, Kubernetes et Terraform.

## Modèle de données

Deux couches PostgreSQL (DDL dans [`sql/ddl/`](sql/ddl/)) :
- **Opérationnel (3NF)** : source de vérité de la télémétrie historique.
- **Analytique (star schema)** : dimensions conformes + tables de faits pour la BI.

ERD, star schema et justifications dans [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md).

---

## Pourquoi cette architecture ?

### 1. Ingestion HTTP + métriques Prometheus
- **Choix actuel** : un simulateur Python publie la télémétrie via une API HTTP et expose les métriques Prometheus sur le même pod.
- **Pourquoi** : HTTP reste trivial à faire tourner localement, ne nécessite aucun cluster Kafka et permet de brancher n’importe quel outil de test (curl, Postman) quand on développe les algorithmes.
- **Alternative envisagée** : un bus Kafka ou NATS pour de l’ingestion massive. On le garde sous le coude car le simulateur sait déjà produire du JSON compatible Kafka, mais on évite la dette opérationnelle tant que la charge reste inférieure au million d’événements/s.

### 2. Traitement temps réel monolithique
- **Choix actuel** : un `stream-processor` unique (FastAPI + worker interne) calcule les KPI et relaye les événements critiques.
- **Pourquoi** : l’algorithme métier (recommandation pit-stop, anomalies) partage énormément de contexte ; garder un seul processus simplifie la cohérence et permet d’itérer vite.
- **Alternative** : découper en micro-services (détection anomalies, scoring pit-stop, enrichissement) ou passer sur un moteur stream (Flink, Spark). Pertinent uniquement si l’on veut paralléliser sur plusieurs nœuds ou appliquer du ML temps réel.

### 3. Stockage orienté séries temporelles minimaliste
- **Choix actuel** : Prometheus uniquement pour les métriques temps réel, PostgreSQL pour l’historique batch.
- **Pourquoi** : Prometheus suffit pour des fenêtres courtes (quelques heures) et Grafana sait interroger directement PromQL. PostgreSQL déjà présent avec Airflow couvre les besoins d’archives.
- **Alternatives** : TimescaleDB, InfluxDB ou ClickHouse si on doit requêter plusieurs semaines/mois de télémétrie avec agrégations lourdes.

### 4. Dashboards provisionnés automatiquement
- **Choix actuel** : Grafana importé par script (`import-dashboard.sh`) avec des JSON versionnés.
- **Pourquoi** : reproductibilité totale entre dev et prod, aucun clic manuel pour installer ou mettre à jour un dashboard.
- **Alternative** : Terraform/Grafana API via CI. À prioriser si plusieurs environnements doivent être tenus à jour par une équipe ops.

### 5. Batch orchestré par Airflow
- **Choix actuel** : Airflow + PostgreSQL + Redis pour les workloads différés (rejeu, ML offline, rapports) avec un DAG principal qui enchaîne collecte, sauvegarde, contrôles qualité et calculs agrégés.
- **Pourquoi** : l’écosystème Airflow est standard en data eng, offre des hooks SQL/HTTP, et réutilise PostgreSQL/Redis déjà nécessaires à Grafana et au simulateur. Les contrôles `DataQuality` garantissent que chaque exécution dispose de données fraîches pour les 10 équipes.
- **Alternative** : Dagster ou Prefect pour des pipelines Python plus légers, ou des jobs Kubernetes CronJob si seuls quelques scripts sont à lancer.

---

## Scalabilité : aujourd'hui et demain

### Capacités actuelles
- Le simulateur sature un CPU autour de ~300k événements/s tout en gardant des latences < 1 ms.
- Le stream-processor est stateless côté HTTP : on peut lancer plusieurs réplicas derrière un load balancer si nécessaire.
- Les dashboards s’appuient sur Prometheus en mode scrape (1 instance suffit pour l’instant) et peuvent être clonés pour des équipes différentes.

### Limites à garder en tête
- **Transport HTTP** : au-delà de quelques millions d’événements/s, HTTP devient le goulot. Passage recommandé sur Kafka + partitions pour absorber le débit.
- **Persistance** : Prometheus n’est pas conçu pour conserver des années de données. Pour du long terme il faudra externaliser vers un TSDB (Thanos, Mimir, TimescaleDB).
- **Traitement monolithique** : en cas d’algorithmes hétérogènes (ML en ligne, micro-services d’enrichissement), le code unique deviendra difficile à scaler.

### Plan d’évolution réaliste
1. **Étendre l’ingestion** : activer le mode Kafka déjà esquisé dans le code (`PROCESSOR_MODE=kafka`) et basculer le simulateur sur un producteur Kafka.
2. **Partitionner le traitement** : extraire la détection d’anomalies dans un worker (Celery ou Faust) pour paralléliser selon `car_id`.
3. **Séparer l’analytique** : stocker la télémétrie agrégée dans un entrepôt colonne (BigQuery/Snowflake) pour des dashboards historiques ou du ML.
4. **Automatiser le déploiement** : Helm charts + GitOps (ArgoCD) pour monter plusieurs environnements homogènes.

Ces étapes suffisent pour passer d’un laboratoire à une plateforme qui supporte des centaines de voitures simulées ou des flux externes en production.

---

## Développement & contributions

1. Créer une branche (`git checkout -b feature/xxx`).
2. Lancer les tests locaux si disponibles (ex. `python -m compileall sensor-simulator/main.py`).
3. Respecter le style Python (type hints, pas de `try/except` autour des imports, logs structurés).
4. Soumettre une Pull Request en décrivant clairement la modification et les tests exécutés.

Des benchmarks, guides d’usage et cas métiers supplémentaires sont disponibles dans `benchmark/` et `docs/`.

---

## Dépannage rapide

---

| Problème | Diagnostic | Solution |
|----------|------------|----------|
| `make start` échoue | Docker ou docker-compose manquant | Installer Docker Desktop / Compose, ou lancer les services manuellement avec `docker-compose up` |
| `http://localhost:3000` inaccessible | Grafana pas encore démarré | Patienter quelques secondes ou vérifier `docker-compose logs grafana` |
| Pas de métriques dans Prometheus | Bibliothèque `prometheus_client` non installée dans le simulateur | Installer la dépendance (`pip install prometheus-client`) puis redémarrer |
| Erreurs HTTP dans le simulateur | Stream-processor injoignable | Lancer `docker-compose up stream-processor` ou ajuster `HTTP_ENDPOINT` |

Pour aller plus loin :
- vérifier la santé des services (`docker compose ps`),
- consulter les logs (`docker compose logs -f --tail=100 <service>`),
- explorer les runbooks directement dans Grafana (panneaux texte).

---

## Ressources complémentaires

- `ARCHITECTURE.md` — détails techniques et flux.
- `sensor-simulator/README.md` — fonctionnement du générateur de télémétrie.
- `docs/` — cas d’usage métier, FAQ, notebooks exploratoires.

Bon run !
