FROM python:3.12-slim

# openssl wird für das Bootstrapping der TLS-Zertifikate (entrypoint.sh) benötigt.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

# Python-Laufzeitabhängigkeiten (ohne PySide6 — die GUI ist nicht Teil des Containers).
RUN pip install --no-cache-dir asyncio websockets requests paho-mqtt

WORKDIR /app

# Quellcode kopieren (config.env und certs/ sind via .dockerignore ausgeschlossen
# und werden zur Laufzeit als Volume eingebunden).
COPY . /app

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
