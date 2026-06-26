#!/bin/sh
set -e

# ============================================================
# BIQU Panda Breath Mod – Docker Entrypoint
# ------------------------------------------------------------
# Erzeugt beim ersten Start die TLS-Zertifikate unter /certs
# (persistent via Volume) und startet anschließend Panda.py.
# Der Cert-Subject ist identisch zu cert_gen.sh.
# ============================================================

CERT_DIR="/certs"
CERT_FILE="${CERT_DIR}/cert.pem"
KEY_FILE="${CERT_DIR}/key.pem"

mkdir -p "${CERT_DIR}"

if [ ! -f "${CERT_FILE}" ] || [ ! -f "${KEY_FILE}" ]; then
    echo "[entrypoint] Keine Zertifikate gefunden – generiere neue (rsa:4096, 3650 Tage)..."
    openssl req -x509 -newkey rsa:4096 \
        -keyout "${KEY_FILE}" \
        -out "${CERT_FILE}" \
        -sha256 -days 3650 -nodes \
        -subj "/C=DE/ST=Panda/L=Panda/O=Bambu/OU=Printer/CN=bambulab.local"
    chmod 600 "${KEY_FILE}"
    chmod 644 "${CERT_FILE}"
    echo "[entrypoint] Zertifikate erstellt unter ${CERT_DIR}."
else
    echo "[entrypoint] Vorhandene Zertifikate in ${CERT_DIR} werden verwendet."
fi

exec python3 Panda.py
