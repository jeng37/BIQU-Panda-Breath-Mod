# Home Assistant Add-on for BIQU Panda Breath Mod

**Date:** 2026-06-26
**Status:** Approved
**Builds on:** 2026-06-26-docker-support-design.md

## Goal

Package the Panda Breath backend as a **Home Assistant Add-on** (Supervisor-managed
container) so HAOS/Supervised users can install it from Settings → Add-ons with a
config UI, instead of running `docker compose` themselves.

## Why an Add-on, not HACS

HACS distributes custom *integrations* (Python loaded into HA core) and Lovelace
cards. `Panda.py` is a standalone daemon that talks to the Panda Touch over
WebSocket/TLS and integrates with HA purely via **MQTT discovery**. It does not run
inside HA. The Supervisor-managed **Add-on** is the correct "native HA container"
mechanism.

## Discovery / networking analysis (the user's core question)

- **MQTT discovery is topology-independent.** `Panda.py` publishes retained
  `homeassistant/.../config` messages to the broker (`Panda.py:622`). HA reads them
  from the broker. Works regardless of Docker network mode — it is NOT mDNS/SSDP.
- **The Panda Touch WebSocket + the TLS server on `0.0.0.0:8883` require host
  networking.** The Panda Touch connects directly to the host IP. Therefore the
  add-on sets `host_network: true`. Same constraint as `network_mode: host` in the
  compose file; the add-on does not remove it, it just declares it.

## Key constraint: build context

HA's Supervisor builds an add-on with the **add-on folder as the Docker build
context** (verified against developers.home-assistant.io). A Dockerfile in
`addon/` cannot `COPY ../Panda.py`. To keep a single source of truth, the add-on
Dockerfile uses `ADD https://raw.githubusercontent.com/.../${SOURCE_REF}/Panda.py`
with `SOURCE_REF` defaulting to `main` (overridable build arg). HA add-on builds
always have network access, so this is safe.

## Components

### `addon/config.yaml`
- `name`, `slug: panda_breath`, `version`, `arch: [aarch64, amd64, armv7]`
- `host_network: true` (required — Panda WebSocket + TLS server)
- `services: ["mqtt:want"]` — pull broker host/port/user/pass from the HA MQTT
  integration via the Supervisor.
- `map: ["addon_config:rw"]` — not strictly needed; certs persist in `/data`
  (the add-on's persistent volume) so no extra map required.
- `options` + `schema`: PANDA_IP, PANDA_SN, PANDA_ACCESS_CODE, HOST_IP, HA_TOKEN,
  HA_SENSOR_URL, and optional MQTT_BROKER/PORT/USER/PASSWORD overrides,
  MQTT_TOPIC_PREFIX, PRINTER_IP, HYSTERESE, DEBUG.
- `init: false` (we provide our own run.sh as the command).

### `addon/Dockerfile`
- `ARG BUILD_FROM` + `FROM ${BUILD_FROM}` (HA base image, includes bashio).
- `apt`/`apk` install openssl + python3 + pip; `pip install websockets requests
  paho-mqtt` (asyncio is stdlib in 3.12; keep it for parity but harmless).
- `ARG SOURCE_REF=main` + `ADD https://raw.githubusercontent.com/jeng37/BIQU-Panda-Breath-Mod/${SOURCE_REF}/Panda.py /app/Panda.py`
- `COPY run.sh /` ; `chmod +x` ; `CMD ["/run.sh"]`.

### `addon/run.sh` (bashio)
- `#!/usr/bin/with-contenv bashio`
- Read each option via `bashio::config`.
- MQTT: if the user left `MQTT_BROKER` blank AND `bashio::services.available
  mqtt`, pull host/port/user/password from `bashio::services mqtt ...`; otherwise
  use the option values (option overrides Supervisor when set).
- Generate `/data/certs/cert.pem` + `key.pem` if missing (subject identical to
  `cert_gen.sh`); export `CERT_PATH`/`KEY_PATH`.
- `export` all the env vars that `Panda.py` already reads (reusing the exact
  contract from the Docker work — no Python changes).
- `cd /app && exec python3 Panda.py`.

### `repository.yaml`
Repo-level metadata so the GitHub repo can be added as a **custom add-on
repository** in HA. Add-on lives under `addon/`.

### Docs
- `addon/DOCS.md` — the in-UI documentation tab.
- README: add an "HA Add-on" subsection under the Docker section, explaining
  install-via-custom-repo, the host-network requirement, and that MQTT creds are
  auto-filled from the MQTT integration.

## No changes to `Panda.py`

The add-on reuses the env-var config contract already added. `run.sh` simply maps
add-on options → the same env var names. Zero Python diff.

## Out of scope
- GUI (`PandaGui.py`).
- Publishing to the community add-on store / multi-arch CI image hosting (users
  build locally on install, which is standard for custom add-ons).

## Testing
- `bash -n addon/run.sh`, `python3 -c "import yaml; yaml.safe_load(...)"` on
  config.yaml + repository.yaml.
- Validate the openssl invocation matches `cert_gen.sh` (already verified in the
  Docker work).
- Static review of bashio calls against bashio API (services, config).
- Note: a real Supervisor build/install can't run in this environment; flag as
  reviewer-verify.
