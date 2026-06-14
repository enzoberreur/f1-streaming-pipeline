FROM python:3.11-slim

WORKDIR /app

# Installation des dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source
COPY main.py db_writer.py ./

# Configuration par défaut
ENV PROCESSOR_MODE=rest \
    PORT=8001 \
    LOG_LEVEL=INFO

# Exposition du port
EXPOSE 8001

# Health check (urllib: stdlib, pas de dépendance supplémentaire)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health', timeout=5)" || exit 1

# Point d'entrée
CMD ["python", "main.py"]
