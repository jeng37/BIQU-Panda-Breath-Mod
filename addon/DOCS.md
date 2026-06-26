# Panda Breath Mod – Home Assistant Add-on

Runs the Panda Breath backend (`Panda.py`) as a Supervisor-managed add-on. It
emulates a Bambu printer for the Panda Touch and exposes everything to Home
Assistant via MQTT discovery.

## Requirements

- A Home Assistant install **with the Supervisor** (Home Assistant OS or
  Supervised). HA Container/Core installs cannot run add-ons — use the
  `docker compose` setup in the repository root instead.
- The **MQTT integration** configured in Home Assistant (e.g. the Mosquitto
  broker add-on). The add-on pulls broker host/user/password from it
  automatically.

## Installation

1. In Home Assistant go to **Settings → Add-ons → Add-on Store**.
2. Open the **⋮** menu (top right) → **Repositories**.
3. Add `https://github.com/jeng37/BIQU-Panda-Breath-Mod` and close.
4. Find **Panda Breath Mod** in the store and click **Install**.

## Configuration

| Option | Required | Description |
| --- | --- | --- |
| `PANDA_IP` | yes | IP of the Panda Touch display |
| `PANDA_SN` | yes | Printer serial number |
| `PANDA_ACCESS_CODE` | yes | Printer access code |
| `HOST_IP` | yes | IP of the HA host (enter this as *Printer IP* in the Panda UI) |
| `HA_TOKEN` | yes | Long-lived access token for the bed-temperature sensor |
| `HA_SENSOR_URL` | yes | Full URL to the bed-temperature sensor state, e.g. `http://homeassistant.local:8123/api/states/sensor.ks1c_bed_temperature` |
| `MQTT_TOPIC_PREFIX` | yes | Keep `panda_breath_mod` so HA entity IDs match |
| `PRINTER_IP` | no | Moonraker host for slicer G-code analysis |
| `MQTT_BROKER` / `MQTT_PORT` / `MQTT_USER` / `MQTT_PASSWORD` | no | **Leave blank** to use the broker from the HA MQTT integration. Set them only to override. |
| `HYSTERESE` | no | Switching threshold in °C (default `1.5`) |
| `DEBUG` | no | Verbose logging |

## Networking

The add-on runs with **host networking** (`host_network: true`). This is required:
the add-on runs a TLS server on port `8883` and the Panda Touch connects directly
to the host's IP over WebSocket. With isolated networking the Panda Touch could not
reach the add-on.

MQTT discovery itself does **not** depend on host networking — it works through the
broker — so all Home Assistant entities appear automatically once the add-on can
reach the broker.

## Certificates

TLS certificates are generated automatically on first start into the add-on's
persistent storage (`/data/certs`), using the same parameters as `cert_gen.sh`.
They survive restarts and updates. To regenerate, delete them from `/data/certs`
and restart.
