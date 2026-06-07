# Data Model

Two layers, both PostgreSQL (DDL in [`../sql/ddl`](../sql/ddl)):

1. **Operational (3NF)** - the source of truth for historical telemetry.
2. **Analytics (star schema)** - dimensional model built from the operational
   tables for fast aggregation and BI/Grafana.

## 1. Operational model (ERD)

```mermaid
erDiagram
    TEAMS ||--o{ DRIVERS : employs
    TEAMS ||--o{ CARS : owns
    CIRCUITS ||--o{ SESSIONS : hosts
    SESSIONS ||--o{ LAPS : contains
    SESSIONS ||--o{ TELEMETRY_READINGS : contains
    SESSIONS ||--o{ PIT_STOPS : contains
    SESSIONS ||--o{ ANOMALIES : contains
    CARS ||--o{ LAPS : runs
    CARS ||--o{ TELEMETRY_READINGS : emits
    CARS ||--o{ PIT_STOPS : makes
    CARS ||--o{ ANOMALIES : triggers
    DRIVERS ||--o{ LAPS : drives

    TEAMS {
        int team_id PK
        string name
        string base
    }
    DRIVERS {
        int driver_id PK
        int team_id FK
        string first_name
        string last_name
        int car_number
    }
    CARS {
        string car_id PK
        int team_id FK
        string power_unit
    }
    CIRCUITS {
        int circuit_id PK
        string name
        numeric length_km
    }
    SESSIONS {
        int session_id PK
        int circuit_id FK
        string session_type
        timestamp start_time
    }
    LAPS {
        bigint lap_id PK
        int session_id FK
        string car_id FK
        int driver_id FK
        int lap_number
        numeric lap_time_seconds
    }
    TELEMETRY_READINGS {
        bigint reading_id PK
        int session_id FK
        string car_id FK
        timestamp recorded_at
        numeric speed_kmh
        numeric tire_wear_percent
    }
    PIT_STOPS {
        bigint pit_stop_id PK
        int session_id FK
        string car_id FK
        numeric duration_seconds
    }
    ANOMALIES {
        bigint anomaly_id PK
        int session_id FK
        string car_id FK
        string anomaly_type
        string severity
    }
```

## 2. Analytics model (star schema)

Conformed dimensions shared by all facts; surrogate keys (`_sk`) decouple the
warehouse from operational IDs and leave room for slowly-changing dimensions.

```mermaid
erDiagram
    DIM_DATE ||--o{ FACT_TELEMETRY : ""
    DIM_SESSION ||--o{ FACT_TELEMETRY : ""
    DIM_CAR ||--o{ FACT_TELEMETRY : ""
    DIM_DRIVER ||--o{ FACT_TELEMETRY : ""
    DIM_TEAM ||--o{ FACT_TELEMETRY : ""
    DIM_CIRCUIT ||--o{ FACT_TELEMETRY : ""
    DIM_DATE ||--o{ FACT_LAP : ""
    DIM_CAR ||--o{ FACT_LAP : ""
    DIM_CIRCUIT ||--o{ FACT_LAP : ""
    DIM_DATE ||--o{ FACT_PIT_STOP : ""
    DIM_CAR ||--o{ FACT_PIT_STOP : ""
    DIM_TEAM ||--o{ FACT_PIT_STOP : ""

    FACT_TELEMETRY {
        bigint telemetry_sk PK
        int date_sk FK
        int car_sk FK
        int session_sk FK
        numeric speed_kmh
        numeric tire_wear_percent
        numeric fuel_remaining_kg
    }
    FACT_LAP {
        bigint lap_sk PK
        int date_sk FK
        int car_sk FK
        numeric lap_time_seconds
    }
    FACT_PIT_STOP {
        bigint pit_stop_sk PK
        int date_sk FK
        int car_sk FK
        numeric duration_seconds
    }
```

## 3. Design rationale

| Decision | Why |
|----------|-----|
| Split OLTP (3NF) and OLAP (star) | Normalised tables keep writes consistent and storage lean; the star schema makes analytical aggregations (avg lap time, tire wear over a stint, pit-stop duration by team) fast and BI-friendly. |
| Grain of `fact_telemetry` = one reading/car/timestamp | Finest useful grain; everything else (per-lap, per-stint, per-session) rolls up from it. |
| Surrogate keys on dimensions | Decouple analytics from source IDs; enable SCD Type 2 (e.g. a driver changing teams) without breaking facts. |
| `dim_date` (YYYYMMDD) | Standard date dimension for time-series rollups and Grafana time filters. |
| Index `telemetry_readings (session_id, car_id, recorded_at)` and `fact_telemetry (date_sk, car_sk, session_sk)` | The dominant query pattern is "a car's telemetry over time in a session". |
| PostgreSQL (RDS) | Already used by Airflow; managed, encrypted, point-in-time recovery. For multi-month, high-cardinality telemetry, TimescaleDB / a columnar warehouse (BigQuery, ClickHouse) is the next step. |

The real-time path (Prometheus + Grafana) covers short windows; this relational
model is the durable historical/analytical store, loaded by the Airflow batch DAG.
