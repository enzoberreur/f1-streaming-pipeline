# Simplified automation entry points

COMPOSE ?= docker compose

.PHONY: help start stop clean import-dashboards demo-links demo

help: ## Show available commands
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*##/: /'

start: ## Rebuild and start the full stack
	$(COMPOSE) down --remove-orphans
	$(COMPOSE) up --build -d
	scripts/import-dashboard.sh --silent

stop: ## Stop all services
	$(COMPOSE) down --remove-orphans

clean: ## Remove containers, volumes and Python caches
	$(COMPOSE) down --volumes --remove-orphans
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +

import-dashboards: ## Reload Grafana dashboards
	scripts/import-dashboard.sh

demo-links: ## Print URLs for demo dashboards and services
	@echo "Ferrari F1 demo endpoints:"
	@echo "  Grafana dashboards:       http://localhost:3000"
	@echo "    Strategy cockpit:      http://localhost:3000/d/ferrari-strategy-dashboard"
	@echo "  Airflow web UI:          http://localhost:8080"
	@echo "  Prometheus console:      http://localhost:9090"
	@echo "  cAdvisor metrics:        http://localhost:8082"
	@echo "  Sensor simulator metrics: http://localhost:8000/metrics"
	@echo "  Stream processor API:    http://localhost:8001"
	@echo "  PostgreSQL connection:   postgresql://airflow:airflow@postgres:5432/airflow (inside Docker network)"

demo: ## Run the one-shot recorded demo (boots the stack + walks the pipeline)
	bash scripts/demo.sh

.DEFAULT_GOAL := help
