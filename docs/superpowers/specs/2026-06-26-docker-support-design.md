# Docker Support for BIQU Panda Breath Mod

**Date:** 2026-06-26
**Status:** Approved

## Goal

Add Docker support so the project runs as a container rather than a bare
`sudo python3 Panda.py`. Certs are auto-generated on first run, config comes from
a `config.env` file, and host networking is used for Panda Touch WebSocket
connectivity.

## Key constraint discovered during exploration

The task premise ("all config is hardcoded in Panda.py") is inaccurate: config is
already loaded from `panda_config.json` at `Panda.py:39-89`. Two values are
genuinely hardcoded:

- Cert paths — `BASE_DIR/cert.pem`, `BASE_DIR/key.pem` (`Panda.py:1295`)
- MQTT port — `1883` (`Panda.py:545`)

The task's env-var list is also a partial subset/rename of the real config and
omits several variables the code requires (`MQTT_TOPIC_PREFIX`, `HOST_IP`,
`HA_BASE_URL`/`HA_BED_TEMPERATURE_ENTITY`, `PRINTER_IP`). Following the list
literally would crash the app.

## Decisions (confirmed with user)

1. **Env overrides JSON.** `panda_config.json` stays as a fallback. Each config
   value resolves as `os.environ.get(NAME) or CONFIG[NAME]`. The app works
   standalone (JSON, no env) and in Docker (env, JSON optional).
2. **Expose the task's variable names** in `config.env` (`PANDA_SN`,
   `PANDA_ACCESS_CODE`, `HA_SENSOR_URL`, `MQTT_PORT`, `CERT_PATH`, `KEY_PATH`)
   and map them to the internal names. Also document the extra vars the code
   needs so a Docker-only user can run without `panda_config.json`.

## Components

### `Panda.py` changes
- Add a small `get_cfg(name, default=None)` helper: returns
  `os.environ.get(name)` if set, else `CONFIG.get(name)`, else `default`.
- Wrap `panda_config.json` loading in a try/except so a missing file is fine when
  env vars supply everything (Docker case).
- Map task var names to internal names:
  - `PANDA_SN` → `PRINTER_SN`
  - `PANDA_ACCESS_CODE` → `ACCESS_CODE`
  - `PANDA_IP` → `PANDA_IP`
  - `MQTT_BROKER`/`MQTT_USER` → same
  - `MQTT_PASSWORD` → `MQTT_PASS` (note rename)
  - `HA_TOKEN` → same
  - `HA_SENSOR_URL` → `HA_URL` (falls back to `HA_BASE_URL` + entity as today)
  - `MQTT_PORT` → new, default `1883`, used at the `client.connect` call
  - `CERT_PATH`/`KEY_PATH` → new, default `cert.pem`/`key.pem` in `BASE_DIR`,
    used in `load_cert_chain`
- Startup check: if any **required** var (`MQTT_BROKER`, `PANDA_IP`,
  `PRINTER_SN`, `ACCESS_CODE`) is missing/empty, print a clear error listing the
  missing names and `sys.exit(1)`.
- MQTT port: `client.connect(MQTT_BROKER, MQTT_PORT, 60)`.
- Standalone path unchanged: existing `panda_config.json` users keep working.

### `Dockerfile`
- `python:3.12-slim`
- `apt-get install -y openssl` (cert bootstrap)
- `pip install asyncio websockets requests paho-mqtt`
- Copy source into `/app`
- `ENTRYPOINT ["/app/entrypoint.sh"]`

### `entrypoint.sh`
- If `/certs/cert.pem` or `/certs/key.pem` missing, generate both with the
  cert subject **identical** to `cert_gen.sh`
  (`/C=DE/ST=Panda/L=Panda/O=Bambu/OU=Printer/CN=bambulab.local`,
  rsa:4096, sha256, 3650 days, `-nodes`).
- `exec python3 Panda.py`
- Committed executable (`chmod +x`).

### `docker-compose.yml`
- Service `panda-breath`, `restart: unless-stopped`, `network_mode: host`
- `env_file: ./config.env`
- Volumes: `./certs:/certs`, `./config.env:/app/config.env`

### `config.env.example`
All task vars with empty values + the extra required-by-code vars documented as
comments, plus `CERT_PATH=/certs/cert.pem` / `KEY_PATH=/certs/key.pem` defaults.

### `.dockerignore`
`__pycache__`, `*.pyc`, `certs/`, `config.env`, `*.pem`.

### `README.md`
Docker section inserted after the Installation section (before Binding):
quick start, filling in `config.env`, auto-cert note, `network_mode: host`
rationale.

## Out of scope
- `PandaGui.py` (GUI)
- Changing the existing non-Docker install path beyond making config
  env-overridable.

## Testing
- Lint: `python3 -m py_compile Panda.py`.
- Verify `Panda.py` still imports with `panda_config.json` present (standalone).
- Verify `get_cfg` precedence: env beats JSON.
- `bash -n entrypoint.sh` syntax check.
- `docker compose config` validates compose file (if Docker available).
