#!/bin/bash
# Cloud-init bootstrap for the F1 application/monitoring server.
# Rendered by Terraform (templatefile): ${repo_url}, ${db_host}, ${db_name},
# ${db_user}, ${db_password} are injected at apply time.
set -euxo pipefail

# 1. Docker + tooling
apt-get update
apt-get install -y docker.io docker-compose-plugin git make openssl
systemctl enable --now docker

# 2. Fetch the pipeline
git clone ${repo_url} /opt/ferrari
cd /opt/ferrari

# 3. Wire the stack to the managed PostgreSQL and a generated API key
cat > .env <<EOF
POSTGRES_HOST=${db_host}
POSTGRES_DB=${db_name}
POSTGRES_USER=${db_user}
POSTGRES_PASSWORD=${db_password}
STREAM_PROCESSOR_API_KEY=$(openssl rand -hex 16)
EOF

# 4. Launch (Grafana :3000, Airflow :8080, Prometheus :9090)
make start || docker compose up -d --build
