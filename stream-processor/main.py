#!/usr/bin/env python3
"""
Ferrari F1 Stream Processor - High Performance Edition
Traite les données télémétrie en temps réel avec détection d'anomalies
et calcul de stratégie pit-stop
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field, fields
from collections import deque
import os
import sys

# FastAPI pour REST et métriques
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
import uvicorn

# Prometheus
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Persistance PostgreSQL optionnelle (module local au service)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_writer import TelemetryDBWriter

# Mode REST uniquement

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# MÉTRIQUES PROMETHEUS
# ============================================================================

# Compteurs
messages_received = Counter(
    'ferrari_messages_received_total',
    'Nombre total de messages de télémétrie reçus'
)

anomalies_detected = Counter(
    'ferrari_anomalies_detected_total',
    'Nombre total d\'anomalies détectées',
    ['anomaly_type', 'severity']
)

pitstop_recommendations = Counter(
    'ferrari_pitstop_recommendations_total',
    'Nombre de recommandations de pit-stop générées'
)

# Histogrammes
processing_latency = Histogram(
    'ferrari_processing_latency_seconds',
    'Latence de traitement des messages',
    buckets=[.001, .0025, .005, .01, .025, .05, .1, .25, .5, 1.0]
)

message_size = Histogram(
    'ferrari_message_size_bytes',
    'Taille des messages reçus',
    buckets=[100, 250, 500, 1000, 2500, 5000, 10000]
)

# Jauges
current_throughput = Gauge(
    'ferrari_current_throughput_msg_per_sec',
    'Débit actuel en messages par seconde'
)

avg_processing_latency = Gauge(
    'ferrari_avg_processing_latency_ms',
    'Latence moyenne de traitement en millisecondes'
)

active_anomalies = Gauge(
    'ferrari_active_anomalies',
    'Nombre d\'anomalies actives actuellement'
)

pitstop_score = Gauge(
    'ferrari_pitstop_score',
    'Score de stratégie pit-stop (0-100)',
    ['car_id', 'team', 'driver']
)


# ============================================================================
# STRUCTURES DE DONNÉES
# ============================================================================

@dataclass
class TelemetryData:
    """Structure de données télémétrie Ferrari F1 - Schema complet"""
    timestamp: str
    car_id: str
    team: str
    driver: str
    car_number: int
    car_model: str
    lap: int

    # Données de base
    speed_kmh: float
    rpm: int
    gear: int
    throttle_percent: float
    
    # Moteur
    engine_temp_celsius: float
    
    # Freinage
    brake_pressure_bar: float
    brake_temp_fl_celsius: float
    brake_temp_fr_celsius: float
    brake_temp_rl_celsius: float
    brake_temp_rr_celsius: float
    
    # Pneus
    tire_compound: str
    tire_temp_fl_celsius: float
    tire_temp_fr_celsius: float
    tire_temp_rl_celsius: float
    tire_temp_rr_celsius: float
    tire_pressure_fl_psi: float
    tire_pressure_fr_psi: float
    tire_pressure_rl_psi: float
    tire_pressure_rr_psi: float
    tire_wear_percent: float
    
    # Aérodynamique et électrique
    drs_status: str
    ers_power_kw: float
    fuel_remaining_kg: float
    
    # Environnement
    track_temp_celsius: float
    air_temp_celsius: float
    humidity_percent: float

    # Insights stratégie (ajout multi-équipe)
    lap_time_seconds: float
    stint_health_score: float
    pit_window_probability: float
    surface_condition: str
    strategy_recommendation: str

    # Anomalies du simulateur
    has_anomaly: bool = False
    anomaly_type: Optional[str] = None
    anomaly_severity: Optional[str] = None


@dataclass
class AnomalyEvent:
    """Événement d'anomalie détecté"""
    timestamp: datetime
    car_id: str
    anomaly_type: str
    severity: str
    value: float
    threshold: float
    duration_seconds: float
    message: str


@dataclass
class PitStopRecommendation:
    """Recommandation de pit-stop"""
    timestamp: datetime
    car_id: str
    lap: int
    score: float  # 0-100
    tire_wear: float
    avg_speed_loss: float
    brake_degradation: float
    recommendation: str
    urgency: str  # low, medium, high, critical


class TimeWindow:
    """Fenêtre temporelle pour détection d'anomalies"""
    
    def __init__(self, duration_seconds: float = 2.0):
        self.duration = timedelta(seconds=duration_seconds)
        self.data: deque = deque()
    
    def add(self, timestamp: datetime, value: float):
        """Ajoute une valeur avec son timestamp"""
        self.data.append((timestamp, value))
        self._cleanup(timestamp)
    
    def _cleanup(self, current_time: datetime):
        """Nettoie les anciennes données hors de la fenêtre"""
        cutoff = current_time - self.duration
        while self.data and self.data[0][0] < cutoff:
            self.data.popleft()
    
    def all_above_threshold(self, threshold: float) -> bool:
        """Vérifie si toutes les valeurs dans la fenêtre dépassent le seuil"""
        if not self.data:
            return False
        return all(value > threshold for _, value in self.data)
    
    def get_duration(self) -> float:
        """Retourne la durée des données dans la fenêtre"""
        if len(self.data) < 2:
            return 0.0
        return (self.data[-1][0] - self.data[0][0]).total_seconds()
    
    def get_average(self) -> float:
        """Calcule la moyenne des valeurs"""
        if not self.data:
            return 0.0
        return sum(value for _, value in self.data) / len(self.data)


# ============================================================================
# DÉTECTION D'ANOMALIES
# ============================================================================

class AnomalyDetector:
    """Détecteur d'anomalies en temps réel"""
    
    # Seuils de détection
    BRAKE_TEMP_CRITICAL = 950.0  # °C
    TIRE_TEMP_CRITICAL = 130.0   # °C
    DETECTION_WINDOW = 2.0       # secondes
    
    def __init__(self):
        # Fenêtres temporelles par voiture
        self.brake_windows: Dict[str, Dict[str, TimeWindow]] = {}
        self.tire_windows: Dict[str, Dict[str, TimeWindow]] = {}
        self.active_anomalies: Dict[str, List[AnomalyEvent]] = {}
    
    def _get_or_create_windows(self, car_id: str):
        """Crée les fenêtres temporelles pour une voiture"""
        if car_id not in self.brake_windows:
            self.brake_windows[car_id] = {
                'fl': TimeWindow(self.DETECTION_WINDOW),
                'fr': TimeWindow(self.DETECTION_WINDOW),
                'rl': TimeWindow(self.DETECTION_WINDOW),
                'rr': TimeWindow(self.DETECTION_WINDOW),
            }
        
        if car_id not in self.tire_windows:
            self.tire_windows[car_id] = {
                'fl': TimeWindow(self.DETECTION_WINDOW),
                'fr': TimeWindow(self.DETECTION_WINDOW),
                'rl': TimeWindow(self.DETECTION_WINDOW),
                'rr': TimeWindow(self.DETECTION_WINDOW),
            }
        
        if car_id not in self.active_anomalies:
            self.active_anomalies[car_id] = []
    
    def detect(self, data: TelemetryData) -> List[AnomalyEvent]:
        """Détecte les anomalies dans les données"""
        timestamp = datetime.fromisoformat(data.timestamp.replace('Z', '+00:00'))
        car_id = data.car_id
        
        self._get_or_create_windows(car_id)
        
        anomalies = []
        
        # Détection des surchauffes de freins
        brake_temps = {
            'fl': data.brake_temp_fl_celsius,
            'fr': data.brake_temp_fr_celsius,
            'rl': data.brake_temp_rl_celsius,
            'rr': data.brake_temp_rr_celsius,
        }
        
        for position, temp in brake_temps.items():
            window = self.brake_windows[car_id][position]
            window.add(timestamp, temp)
            
            if (window.all_above_threshold(self.BRAKE_TEMP_CRITICAL) and 
                window.get_duration() >= self.DETECTION_WINDOW):
                
                anomaly = AnomalyEvent(
                    timestamp=timestamp,
                    car_id=car_id,
                    anomaly_type=f'brake_overheat_{position}',
                    severity='critical',
                    value=temp,
                    threshold=self.BRAKE_TEMP_CRITICAL,
                    duration_seconds=window.get_duration(),
                    message=f'🔥 CRITIQUE: Frein {position.upper()} en surchauffe ({temp:.1f}°C > {self.BRAKE_TEMP_CRITICAL}°C) pendant {window.get_duration():.1f}s'
                )
                anomalies.append(anomaly)
        
        # Détection des surchauffes de pneus
        tire_temps = {
            'fl': data.tire_temp_fl_celsius,
            'fr': data.tire_temp_fr_celsius,
            'rl': data.tire_temp_rl_celsius,
            'rr': data.tire_temp_rr_celsius,
        }
        
        for position, temp in tire_temps.items():
            window = self.tire_windows[car_id][position]
            window.add(timestamp, temp)
            
            if (window.all_above_threshold(self.TIRE_TEMP_CRITICAL) and 
                window.get_duration() >= self.DETECTION_WINDOW):
                
                anomaly = AnomalyEvent(
                    timestamp=timestamp,
                    car_id=car_id,
                    anomaly_type=f'tire_overheat_{position}',
                    severity='critical',
                    value=temp,
                    threshold=self.TIRE_TEMP_CRITICAL,
                    duration_seconds=window.get_duration(),
                    message=f'🔥 CRITIQUE: Pneu {position.upper()} en surchauffe ({temp:.1f}°C > {self.TIRE_TEMP_CRITICAL}°C) pendant {window.get_duration():.1f}s'
                )
                anomalies.append(anomaly)
        
        # Mise à jour des anomalies actives
        if anomalies:
            self.active_anomalies[car_id].extend(anomalies)
            # Nettoyer les anciennes anomalies (>60s)
            cutoff = timestamp - timedelta(seconds=60)
            self.active_anomalies[car_id] = [
                a for a in self.active_anomalies[car_id] 
                if a.timestamp > cutoff
            ]
        
        return anomalies
    
    def get_active_count(self) -> int:
        """Retourne le nombre d'anomalies actives"""
        return sum(len(anomalies) for anomalies in self.active_anomalies.values())


# ============================================================================
# CALCUL DE STRATÉGIE PIT-STOP
# ============================================================================

class PitStopStrategyCalculator:
    """Calcule le score de stratégie pit-stop"""
    
    def __init__(self):
        self.history: Dict[str, deque] = {}  # Historique par voiture
        self.max_history = 100  # Garder 100 dernières mesures
    
    def calculate_score(self, data: TelemetryData, anomalies: List[AnomalyEvent]) -> PitStopRecommendation:
        """Calcule le score de stratégie pit-stop"""
        car_id = data.car_id
        
        # Initialiser l'historique si nécessaire
        if car_id not in self.history:
            self.history[car_id] = deque(maxlen=self.max_history)
        
        self.history[car_id].append(data)
        
        # Facteur 1: Usure des pneus (0-100, poids: 40%)
        tire_wear_score = data.tire_wear_percent
        tire_wear_weight = 0.40
        
        # Facteur 2: Perte de vitesse (0-100, poids: 30%)
        speed_loss_score = self._calculate_speed_loss(car_id, data)
        speed_loss_weight = 0.30
        
        # Facteur 3: Dégradation des freins (0-100, poids: 20%)
        brake_degradation_score = self._calculate_brake_degradation(data)
        brake_degradation_weight = 0.20
        
        # Facteur 4: Présence d'anomalies (0-100, poids: 10%)
        anomaly_score = len(anomalies) * 25  # Chaque anomalie ajoute 25 points
        anomaly_score = min(anomaly_score, 100)
        anomaly_weight = 0.10
        
        # Score pondéré (0-100)
        total_score = (
            tire_wear_score * tire_wear_weight +
            speed_loss_score * speed_loss_weight +
            brake_degradation_score * brake_degradation_weight +
            anomaly_score * anomaly_weight
        )
        
        # Déterminer l'urgence
        if total_score >= 90:
            urgency = "critical"
            recommendation = "PIT-STOP IMMÉDIAT REQUIS!"
        elif total_score >= 75:
            urgency = "high"
            recommendation = "Pit-stop fortement recommandé au prochain tour"
        elif total_score >= 50:
            urgency = "medium"
            recommendation = "Pit-stop recommandé dans les 3-5 prochains tours"
        else:
            urgency = "low"
            recommendation = "Continuer, surveillance normale"
        
        return PitStopRecommendation(
            timestamp=datetime.utcnow(),
            car_id=car_id,
            lap=data.lap,
            score=round(total_score, 2),
            tire_wear=round(tire_wear_score, 2),
            avg_speed_loss=round(speed_loss_score, 2),
            brake_degradation=round(brake_degradation_score, 2),
            recommendation=recommendation,
            urgency=urgency
        )
    
    def _calculate_speed_loss(self, car_id: str, current_data: TelemetryData) -> float:
        """Calcule la perte de vitesse relative (0-100)"""
        history = self.history.get(car_id)
        if not history or len(history) < 10:
            return 0.0
        
        # Vitesse moyenne des 10 premières mesures vs 10 dernières
        early_speeds = [d.speed_kmh for d in list(history)[:10]]
        recent_speeds = [d.speed_kmh for d in list(history)[-10:]]
        
        avg_early = sum(early_speeds) / len(early_speeds)
        avg_recent = sum(recent_speeds) / len(recent_speeds)
        
        if avg_early == 0:
            return 0.0
        
        # Perte en pourcentage
        loss_percent = ((avg_early - avg_recent) / avg_early) * 100
        
        # Normaliser sur 0-100
        return max(0, min(100, loss_percent * 5))  # Amplifier pour avoir un score significatif
    
    def _calculate_brake_degradation(self, data: TelemetryData) -> float:
        """Calcule la dégradation des freins (0-100)"""
        # Moyenne des températures de frein
        avg_brake_temp = (
            data.brake_temp_fl_celsius +
            data.brake_temp_fr_celsius +
            data.brake_temp_rl_celsius +
            data.brake_temp_rr_celsius
        ) / 4
        
        # Score basé sur la température (250°C = 0%, 950°C = 100%)
        temp_min = 250.0
        temp_max = 950.0
        
        score = ((avg_brake_temp - temp_min) / (temp_max - temp_min)) * 100
        return max(0, min(100, score))


# ============================================================================
# PROCESSEUR DE FLUX
# ============================================================================

class StreamProcessor:
    """Processeur principal de flux"""
    
    def __init__(self):
        self.anomaly_detector = AnomalyDetector()
        self.pitstop_calculator = PitStopStrategyCalculator()
        
        # Statistiques
        self.messages_count = 0
        self.start_time = time.time()
        self.last_throughput_update = time.time()
        self.messages_since_last_update = 0
        self.latencies = deque(maxlen=1000)
    
    def process_message(self, data: Dict) -> Dict:
        """Traite un message de télémétrie"""
        start_time = time.time()
        
        try:
            # Parser les données (en filtrant les champs inattendus)
            allowed_fields = {f.name for f in fields(TelemetryData)}
            unknown_keys = [key for key in data.keys() if key not in allowed_fields]
            if unknown_keys:
                logger.debug("Champs télémétrie inconnus ignorés: %s", unknown_keys)

            telemetry_payload = {key: value for key, value in data.items() if key in allowed_fields}

            try:
                telemetry = TelemetryData(**telemetry_payload)
            except TypeError as exc:
                missing = [name for name in allowed_fields if name not in telemetry_payload]
                logger.error(
                    "Payload télémétrie invalide (manquants=%s, inconnus=%s): %s",
                    missing,
                    unknown_keys,
                    exc,
                )
                raise

            # Métriques Prometheus
            messages_received.inc()
            message_size.observe(len(json.dumps(data)))
            
            # Détection d'anomalies
            anomalies = self.anomaly_detector.detect(telemetry)
            
            # Enregistrer les anomalies dans Prometheus
            for anomaly in anomalies:
                anomalies_detected.labels(
                    anomaly_type=anomaly.anomaly_type,
                    severity=anomaly.severity
                ).inc()
                logger.warning(f"⚠️  {anomaly.message}")
            
            # Persistance PostgreSQL (mise en tampon, jamais bloquante)
            if db_writer is not None:
                db_writer.add_reading(telemetry)
                for anomaly in anomalies:
                    db_writer.add_anomaly(anomaly)

            # Calcul du score pit-stop
            pitstop_rec = self.pitstop_calculator.calculate_score(telemetry, anomalies)
            
            # Mise à jour de la métrique Prometheus
            pitstop_score.labels(
                car_id=telemetry.car_id,
                team=telemetry.team,
                driver=telemetry.driver,
            ).set(pitstop_rec.score)

            if pitstop_rec.urgency in ['high', 'critical']:
                pitstop_recommendations.inc()
                logger.info(
                    "🏁 [%s] %s (%s) - Score: %.1f",
                    telemetry.team,
                    telemetry.driver,
                    pitstop_rec.recommendation,
                    pitstop_rec.score,
                )
            
            # Statistiques
            latency = time.time() - start_time
            processing_latency.observe(latency)
            self.latencies.append(latency)
            
            self.messages_count += 1
            self.messages_since_last_update += 1
            
            # Mise à jour du throughput toutes les secondes
            if time.time() - self.last_throughput_update >= 1.0:
                throughput = self.messages_since_last_update / (time.time() - self.last_throughput_update)
                current_throughput.set(throughput)
                self.messages_since_last_update = 0
                self.last_throughput_update = time.time()
            
            # Mise à jour de la latence moyenne
            if self.latencies:
                avg_lat = sum(self.latencies) / len(self.latencies) * 1000  # en ms
                avg_processing_latency.set(avg_lat)
            
            # Mise à jour des anomalies actives
            active_anomalies.set(self.anomaly_detector.get_active_count())
            
            # Résultat
            return {
                "status": "processed",
                "team": telemetry.team,
                "driver": telemetry.driver,
                "car_id": telemetry.car_id,
                "car_number": telemetry.car_number,
                "car_model": telemetry.car_model,
                "lap": telemetry.lap,
                "anomalies": [
                    {
                        "type": a.anomaly_type,
                        "severity": a.severity,
                        "value": a.value,
                        "threshold": a.threshold,
                        "duration": a.duration_seconds,
                        "message": a.message
                    }
                    for a in anomalies
                ],
                "pitstop": {
                    "score": pitstop_rec.score,
                    "urgency": pitstop_rec.urgency,
                    "recommendation": pitstop_rec.recommendation,
                    "details": {
                        "tire_wear": pitstop_rec.tire_wear,
                        "speed_loss": pitstop_rec.avg_speed_loss,
                        "brake_degradation": pitstop_rec.brake_degradation
                    }
                },
                "processing_time_ms": round(latency * 1000, 2)
            }
            
        except Exception as e:
            logger.error(f"Erreur de traitement: {e}")
            raise


# ============================================================================
# API REST (FastAPI)
# ============================================================================

app = FastAPI(
    title="Ferrari F1 Stream Processor",
    description="Traitement en temps réel des données télémétrie avec détection d'anomalies",
    version="1.0.0"
)

# Instance du processeur
processor = StreamProcessor()

# Writer PostgreSQL optionnel (actif si DATABASE_URL + ENABLE_DB_WRITES=true)
db_writer = TelemetryDBWriter.from_env()
if db_writer is not None:
    db_writer.start()


@app.get("/")
async def root():
    """Page d'accueil"""
    uptime = time.time() - processor.start_time
    return {
        "service": "Ferrari F1 Stream Processor",
        "status": "running",
        "uptime_seconds": round(uptime, 2),
        "messages_processed": processor.messages_count,
        "avg_throughput": round(processor.messages_count / uptime, 2) if uptime > 0 else 0
    }


API_KEY = os.getenv("STREAM_PROCESSOR_API_KEY")
API_KEY_HEADER = os.getenv("STREAM_PROCESSOR_API_KEY_HEADER", "X-Api-Key")


def _assert_authorized(request: Request) -> None:
    """Enforce simple API key authentication when configured."""

    if not API_KEY:
        return

    provided_key = request.headers.get(API_KEY_HEADER)
    if provided_key and provided_key == API_KEY:
        return

    logger.warning(
        "Unauthorized telemetry submission rejected (header=%s)",
        API_KEY_HEADER,
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


@app.post("/telemetry")
async def receive_telemetry(request: Request, data: Dict):
    """Reçoit et traite un message de télémétrie"""
    try:
        _assert_authorized(request)

        result = processor.process_message(data)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.on_event("shutdown")
async def shutdown_event():
    """Flush final du writer PostgreSQL à l'arrêt du service"""
    if db_writer is not None:
        db_writer.stop()


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Endpoint Prometheus metrics"""
    return generate_latest().decode('utf-8')


@app.get("/stats")
async def get_stats():
    """Statistiques du processeur"""
    uptime = time.time() - processor.start_time
    avg_latency = sum(processor.latencies) / len(processor.latencies) * 1000 if processor.latencies else 0
    
    return {
        "uptime_seconds": round(uptime, 2),
        "messages_processed": processor.messages_count,
        "avg_throughput_msg_per_sec": round(processor.messages_count / uptime, 2) if uptime > 0 else 0,
        "avg_latency_ms": round(avg_latency, 2),
        "active_anomalies": processor.anomaly_detector.get_active_count()
    }


# ============================================================================
# CONSUMER KAFKA (optionnel)
# ============================================================================


# ============================================================================
# POINT D'ENTRÉE
# ============================================================================

def main():
    """Point d'entrée principal"""
    logger.info("=" * 80)
    logger.info("🏎️  Ferrari F1 Stream Processor - Starting")
    logger.info("=" * 80)
    
    mode = os.getenv("PROCESSOR_MODE", "rest").lower()
    port = int(os.getenv("PORT", "8001"))
    
    logger.info(f"Mode: {mode.upper()}")
    logger.info(f"Port: {port}")
    
    # Mode REST uniquement
    logger.info(f"🌐 API REST démarrée sur http://0.0.0.0:{port}")
    logger.info(f"📊 Métriques Prometheus: http://0.0.0.0:{port}/metrics")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
