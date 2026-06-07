-- 02_star_schema.sql
-- Dimensional (star schema) model for analytics, built from the operational tables.
-- Conformed dimensions shared by all facts; surrogate keys (_sk) decouple analytics
-- from operational IDs and support slowly-changing dimensions later.

CREATE SCHEMA IF NOT EXISTS analytics;

-- ---------- Dimensions ----------
CREATE TABLE IF NOT EXISTS analytics.dim_team (
    team_sk SERIAL PRIMARY KEY,
    team_id INT,
    name    VARCHAR(100),
    base    VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS analytics.dim_driver (
    driver_sk  SERIAL PRIMARY KEY,
    driver_id  INT,
    full_name  VARCHAR(100),
    car_number INT,
    country    VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS analytics.dim_car (
    car_sk     SERIAL PRIMARY KEY,
    car_id     VARCHAR(50),
    chassis    VARCHAR(50),
    power_unit VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS analytics.dim_circuit (
    circuit_sk SERIAL PRIMARY KEY,
    circuit_id INT,
    name       VARCHAR(100),
    country    VARCHAR(50),
    length_km  NUMERIC(5, 3)
);

CREATE TABLE IF NOT EXISTS analytics.dim_date (
    date_sk   INT PRIMARY KEY,  -- YYYYMMDD
    full_date DATE NOT NULL,
    year      INT,
    quarter   INT,
    month     INT,
    day       INT,
    weekday   VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS analytics.dim_session (
    session_sk   SERIAL PRIMARY KEY,
    session_id   INT,
    session_type VARCHAR(20),
    start_time   TIMESTAMP
);

-- ---------- Facts ----------
-- Grain: one telemetry reading per car per timestamp.
CREATE TABLE IF NOT EXISTS analytics.fact_telemetry (
    telemetry_sk      BIGSERIAL PRIMARY KEY,
    date_sk           INT REFERENCES analytics.dim_date (date_sk),
    session_sk        INT REFERENCES analytics.dim_session (session_sk),
    car_sk            INT REFERENCES analytics.dim_car (car_sk),
    driver_sk         INT REFERENCES analytics.dim_driver (driver_sk),
    team_sk           INT REFERENCES analytics.dim_team (team_sk),
    circuit_sk        INT REFERENCES analytics.dim_circuit (circuit_sk),
    recorded_at       TIMESTAMP,
    speed_kmh         NUMERIC(6, 2),
    engine_temp_c     NUMERIC(6, 2),
    brake_temp_c      NUMERIC(6, 2),
    tire_temp_c       NUMERIC(6, 2),
    tire_wear_percent NUMERIC(5, 2),
    fuel_remaining_kg NUMERIC(6, 2)
);

CREATE INDEX IF NOT EXISTS idx_fact_telemetry_dims
    ON analytics.fact_telemetry (date_sk, car_sk, session_sk);

-- Grain: one completed lap.
CREATE TABLE IF NOT EXISTS analytics.fact_lap (
    lap_sk           BIGSERIAL PRIMARY KEY,
    date_sk          INT REFERENCES analytics.dim_date (date_sk),
    session_sk       INT REFERENCES analytics.dim_session (session_sk),
    car_sk           INT REFERENCES analytics.dim_car (car_sk),
    driver_sk        INT REFERENCES analytics.dim_driver (driver_sk),
    circuit_sk       INT REFERENCES analytics.dim_circuit (circuit_sk),
    lap_number       INT,
    lap_time_seconds NUMERIC(7, 3),
    sector1_seconds  NUMERIC(7, 3),
    sector2_seconds  NUMERIC(7, 3),
    sector3_seconds  NUMERIC(7, 3)
);

-- Grain: one pit stop.
CREATE TABLE IF NOT EXISTS analytics.fact_pit_stop (
    pit_stop_sk      BIGSERIAL PRIMARY KEY,
    date_sk          INT REFERENCES analytics.dim_date (date_sk),
    session_sk       INT REFERENCES analytics.dim_session (session_sk),
    car_sk           INT REFERENCES analytics.dim_car (car_sk),
    team_sk          INT REFERENCES analytics.dim_team (team_sk),
    lap_number       INT,
    duration_seconds NUMERIC(5, 2)
);
