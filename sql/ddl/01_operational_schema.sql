-- 01_operational_schema.sql
-- Normalized (3NF) operational model for Ferrari F1 telemetry (PostgreSQL).
-- Source of truth for the historical store; the star schema (02) is built from it.

CREATE TABLE IF NOT EXISTS teams (
    team_id   SERIAL PRIMARY KEY,
    name      VARCHAR(100) NOT NULL UNIQUE,
    base      VARCHAR(100),
    principal VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS drivers (
    driver_id  SERIAL PRIMARY KEY,
    team_id    INT NOT NULL REFERENCES teams (team_id),
    first_name VARCHAR(50) NOT NULL,
    last_name  VARCHAR(50) NOT NULL,
    car_number INT,
    country    VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS cars (
    car_id     VARCHAR(50) PRIMARY KEY,  -- matches the telemetry car_id (e.g. FER-16)
    team_id    INT NOT NULL REFERENCES teams (team_id),
    chassis    VARCHAR(50),
    power_unit VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS circuits (
    circuit_id SERIAL PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    country    VARCHAR(50),
    length_km  NUMERIC(5, 3),
    total_laps INT
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id   SERIAL PRIMARY KEY,
    circuit_id   INT NOT NULL REFERENCES circuits (circuit_id),
    session_type VARCHAR(20) NOT NULL CHECK (session_type IN ('practice', 'qualifying', 'race')),
    start_time   TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS laps (
    lap_id           BIGSERIAL PRIMARY KEY,
    session_id       INT NOT NULL REFERENCES sessions (session_id),
    car_id           VARCHAR(50) NOT NULL REFERENCES cars (car_id),
    driver_id        INT NOT NULL REFERENCES drivers (driver_id),
    lap_number       INT NOT NULL,
    lap_time_seconds NUMERIC(7, 3),
    sector1_seconds  NUMERIC(7, 3),
    sector2_seconds  NUMERIC(7, 3),
    sector3_seconds  NUMERIC(7, 3),
    recorded_at      TIMESTAMP NOT NULL,
    UNIQUE (session_id, car_id, lap_number)
);

CREATE TABLE IF NOT EXISTS telemetry_readings (
    reading_id        BIGSERIAL PRIMARY KEY,
    session_id        INT NOT NULL REFERENCES sessions (session_id),
    car_id            VARCHAR(50) NOT NULL REFERENCES cars (car_id),
    recorded_at       TIMESTAMP NOT NULL,
    speed_kmh         NUMERIC(6, 2),
    engine_temp_c     NUMERIC(6, 2),
    brake_temp_c      NUMERIC(6, 2),
    tire_temp_c       NUMERIC(6, 2),
    tire_wear_percent NUMERIC(5, 2),
    fuel_remaining_kg NUMERIC(6, 2),
    throttle_percent  NUMERIC(5, 2),
    brake_percent     NUMERIC(5, 2),
    gear              SMALLINT,
    rpm               INT
);

CREATE INDEX IF NOT EXISTS idx_telemetry_session_car_time
    ON telemetry_readings (session_id, car_id, recorded_at);

CREATE TABLE IF NOT EXISTS pit_stops (
    pit_stop_id       BIGSERIAL PRIMARY KEY,
    session_id        INT NOT NULL REFERENCES sessions (session_id),
    car_id            VARCHAR(50) NOT NULL REFERENCES cars (car_id),
    lap_number        INT NOT NULL,
    duration_seconds  NUMERIC(5, 2),
    tire_compound_in  VARCHAR(20),
    tire_compound_out VARCHAR(20),
    recorded_at       TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS anomalies (
    anomaly_id   BIGSERIAL PRIMARY KEY,
    session_id   INT NOT NULL REFERENCES sessions (session_id),
    car_id       VARCHAR(50) NOT NULL REFERENCES cars (car_id),
    recorded_at  TIMESTAMP NOT NULL,
    anomaly_type VARCHAR(50) NOT NULL,
    severity     VARCHAR(20) CHECK (severity IN ('info', 'warning', 'critical')),
    description  TEXT
);
