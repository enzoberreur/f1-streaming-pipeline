#!/bin/bash

# Script de déploiement Kubernetes pour Ferrari F1 IoT
# Usage: ./deploy-k8s.sh [environment]
# Environments: dev, staging, prod

set -e

ENVIRONMENT=${1:-dev}
NAMESPACE="ferrari-f1"
K8S_DIR="k8s"

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fonction d'affichage
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

# Vérifications préalables
check_prerequisites() {
    log "Vérification des prérequis..."
    
    # Vérifier kubectl
    if ! command -v kubectl &> /dev/null; then
        error "kubectl n'est pas installé"
    fi
    
    # Vérifier la connexion au cluster
    if ! kubectl cluster-info &> /dev/null; then
        error "Impossible de se connecter au cluster Kubernetes"
    fi
    
    # Vérifier les fichiers K8s
    if [ ! -d "$K8S_DIR" ]; then
        error "Dossier $K8S_DIR non trouvé"
    fi
    
    # Vérifier les StorageClass disponibles
    log "StorageClasses disponibles:"
    kubectl get storageclass
    
    success "Prérequis validés"
}

# Créer le namespace et les ressources de base
setup_namespace() {
    log "Configuration du namespace $NAMESPACE..."
    
    kubectl apply -f $K8S_DIR/namespace.yaml
    kubectl apply -f $K8S_DIR/config.yaml
    kubectl apply -f $K8S_DIR/rbac.yaml

    success "Namespace configuré"
}

# Déployer les services de données (PostgreSQL, Redis)
deploy_data_services() {
    log "Déploiement des services de données..."
    
    # PostgreSQL pour Airflow
    kubectl apply -f $K8S_DIR/postgres.yaml -n $NAMESPACE
    
    # Redis pour Airflow
    kubectl apply -f $K8S_DIR/redis.yaml -n $NAMESPACE
    
    # Attendre que les services soient prêts avec timeout plus court et diagnostic
    log "Attente que PostgreSQL soit prêt..."
    if ! kubectl wait --for=condition=ready pod -l app=postgres -n $NAMESPACE --timeout=120s; then
        warning "PostgreSQL prend plus de temps à démarrer - vérification des détails..."
        kubectl get pods -l app=postgres -n $NAMESPACE
        kubectl describe pod -l app=postgres -n $NAMESPACE | tail -20
        log "Continuons avec Redis pendant que PostgreSQL démarre..."
    fi
    
    log "Attente que Redis soit prêt..."
    if ! kubectl wait --for=condition=ready pod -l app=redis -n $NAMESPACE --timeout=60s; then
        warning "Redis a des problèmes - diagnostic:"
        kubectl get pods -l app=redis -n $NAMESPACE
        kubectl describe pod -l app=redis -n $NAMESPACE | tail -10
    fi
    
    success "Services de données déployés"
}

# Déployer les services de monitoring
deploy_monitoring() {
    log "Déploiement du monitoring..."
    
    # Monitoring (Prometheus + Grafana dans un seul fichier)
    kubectl apply -f $K8S_DIR/monitoring.yaml -n $NAMESPACE
    
    # Attendre que les services soient prêts
    log "Attente que Prometheus soit prêt..."
    kubectl wait --for=condition=ready pod -l app=prometheus -n $NAMESPACE --timeout=120s || warning "Prometheus prend plus de temps"
    
    log "Attente que Grafana soit prêt..."
    kubectl wait --for=condition=ready pod -l app=grafana -n $NAMESPACE --timeout=120s || warning "Grafana prend plus de temps"
    
    success "Services de monitoring déployés"
}

# Déployer Airflow
deploy_airflow() {
    log "Déploiement d'Airflow..."
    
    kubectl apply -f $K8S_DIR/airflow.yaml -n $NAMESPACE
    
    # Attendre que les services soient prêts
    log "Attente qu'Airflow soit prêt..."
    kubectl wait --for=condition=ready pod -l app=airflow-webserver -n $NAMESPACE --timeout=600s
    
    success "Airflow déployé"
}

# Déployer les applications Ferrari F1
deploy_applications() {
    log "Déploiement des applications Ferrari F1..."
    
    # Stream Processor
    kubectl apply -f $K8S_DIR/stream-processor.yaml -n $NAMESPACE
    
    # Sensor Simulator
    kubectl apply -f $K8S_DIR/sensor-simulator.yaml -n $NAMESPACE
    
    # Attendre que les services soient prêts
    log "Attente que Stream Processor soit prêt..."
    kubectl wait --for=condition=ready pod -l app=stream-processor -n $NAMESPACE --timeout=300s
    
    log "Attente que Sensor Simulator soit prêt..."
    kubectl wait --for=condition=ready pod -l app=sensor-simulator -n $NAMESPACE --timeout=300s
    
    success "Applications Ferrari F1 déployées"
}

# Configurer l'ingress selon l'environnement
deploy_ingress() {
    log "Configuration de l'ingress pour l'environnement $ENVIRONMENT..."
    
    if [ "$ENVIRONMENT" == "prod" ]; then
        # En production, utiliser l'ingress avec certificats SSL
        kubectl apply -f $K8S_DIR/ingress.yaml -n $NAMESPACE
        success "Ingress de production configuré"
    else
        # En dev/staging, utiliser NodePort ou port-forward
        warning "Environnement $ENVIRONMENT: utiliser 'make k8s-port-forward' pour accéder aux services"
    fi
}

# Afficher le statut final
show_status() {
    log "Statut du déploiement Ferrari F1 IoT:"
    echo
    
    kubectl get pods -n $NAMESPACE -o wide
    echo
    
    kubectl get services -n $NAMESPACE
    echo
    
    if [ "$ENVIRONMENT" == "prod" ]; then
        log "URLs de production (via ingress):"
        INGRESS_IP=$(kubectl get ingress ferrari-f1-ingress -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "En attente...")
        echo "  Grafana: http://$INGRESS_IP/grafana"
        echo "  Prometheus: http://$INGRESS_IP/prometheus"
        echo "  Airflow: http://$INGRESS_IP/airflow"
        echo "  Stream Processor API: http://$INGRESS_IP/api"
        echo "  Metrics: http://$INGRESS_IP/metrics"
    else
        log "Pour accéder aux services en $ENVIRONMENT:"
        echo "  make k8s-port-forward  # Puis aller sur http://localhost:3000 (Grafana)"
    fi
    
    echo
    success "Déploiement Ferrari F1 IoT terminé avec succès!"
}

# Fonction de nettoyage en cas d'erreur
cleanup_on_error() {
    error "Erreur pendant le déploiement. Nettoyage..."
    kubectl delete namespace $NAMESPACE --ignore-not-found=true
    exit 1
}

# Piège pour nettoyer en cas d'erreur
trap cleanup_on_error ERR

# Fonction principale
main() {
    log "🏁 Démarrage du déploiement Ferrari F1 IoT (environnement: $ENVIRONMENT)"
    
    check_prerequisites
    setup_namespace
    deploy_data_services
    deploy_monitoring
    deploy_airflow
    deploy_applications
    deploy_ingress
    show_status
}

# Exécuter le script principal
main