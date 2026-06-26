#!/usr/bin/with-contenv bashio
# ============================================================
# BIQU Panda Breath Mod – Home Assistant Add-on entrypoint
# ------------------------------------------------------------
# Maps add-on options -> the env vars Panda.py already reads,
# pulls MQTT broker creds from the Supervisor when not set,
# bootstraps TLS certs into /data, then starts Panda.py.
# ============================================================
set -e

CERT_DIR="/data/certs"
CERT_FILE="${CERT_DIR}/cert.pem"
KEY_FILE="${CERT_DIR}/key.pem"

# Read an add-on option, returning "" (never the literal "null") when unset/empty.
cfg() {
    bashio::config "${1}" ""
}

# --- TLS certificates (persisted in /data, generated once) ---
mkdir -p "${CERT_DIR}"
if ! bashio::fs.file_exists "${CERT_FILE}" || ! bashio::fs.file_exists "${KEY_FILE}"; then
    bashio::log.info "Generating TLS certificates (rsa:4096, 3650 days)..."
    openssl req -x509 -newkey rsa:4096 \
        -keyout "${KEY_FILE}" \
        -out "${CERT_FILE}" \
        -sha256 -days 3650 -nodes \
        -subj "/C=DE/ST=Panda/L=Panda/O=Bambu/OU=Printer/CN=bambulab.local"
    chmod 600 "${KEY_FILE}"
    chmod 644 "${CERT_FILE}"
    bashio::log.info "Certificates created in ${CERT_DIR}."
else
    bashio::log.info "Using existing certificates in ${CERT_DIR}."
fi
export CERT_PATH="${CERT_FILE}"
export KEY_PATH="${KEY_FILE}"

# --- MQTT broker: option value wins; otherwise pull from the Supervisor service ---
MQTT_BROKER="$(cfg 'MQTT_BROKER')"
MQTT_PORT="$(cfg 'MQTT_PORT')"
MQTT_USER="$(cfg 'MQTT_USER')"
MQTT_PASSWORD="$(cfg 'MQTT_PASSWORD')"

if bashio::var.is_empty "${MQTT_BROKER}"; then
    if bashio::services.available "mqtt"; then
        bashio::log.info "Using MQTT broker from the Home Assistant MQTT service."
        MQTT_BROKER="$(bashio::services mqtt 'host')"
        MQTT_PORT="$(bashio::services mqtt 'port')"
        MQTT_USER="$(bashio::services mqtt 'username')"
        MQTT_PASSWORD="$(bashio::services mqtt 'password')"
    else
        bashio::log.warning "No MQTT_BROKER set and no MQTT service available."
    fi
fi

export MQTT_BROKER MQTT_PORT MQTT_USER MQTT_PASSWORD

# --- Remaining config -> env (Panda.py reads these names directly) ---
export PANDA_IP="$(cfg 'PANDA_IP')"
export PANDA_SN="$(cfg 'PANDA_SN')"
export PANDA_ACCESS_CODE="$(cfg 'PANDA_ACCESS_CODE')"
export HOST_IP="$(cfg 'HOST_IP')"
export HA_TOKEN="$(cfg 'HA_TOKEN')"
export HA_SENSOR_URL="$(cfg 'HA_SENSOR_URL')"
export MQTT_TOPIC_PREFIX="$(cfg 'MQTT_TOPIC_PREFIX')"
export PRINTER_IP="$(cfg 'PRINTER_IP')"
export HYSTERESE="$(cfg 'HYSTERESE')"
export DEBUG="$(cfg 'DEBUG')"

bashio::log.info "Starting Panda Breath Mod..."
cd /app
exec python3 Panda.py
