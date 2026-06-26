<!-- REPO_VIEWS_BADGE_START -->
![Repository Views](https://img.shields.io/badge/Repository%20Views-9988-blue?style=flat-square)
<!-- REPO_VIEWS_BADGE_END -->

# BIQU Panda Breath Mod 🚀
### Panda Logic Sync v1.9.3 (Bug Fix Release)

Intelligent control system for the **BIQU Panda Breath** chamber heater.

This project simulates a **Bambu Lab printer** on a host system (PC / server) and enables fully synchronized chamber heating using **real-time Home Assistant data**.

<img width="1839" height="912" src="https://github.com/user-attachments/assets/50aab4bf-ccf9-4eea-8567-7ef40c84fd36" />

<img width="1329" height="897" src="https://github.com/user-attachments/assets/89309991-4a4c-4611-bd0c-f5e7c97c90c9" />
<img width="1329" height="897" src="https://github.com/user-attachments/assets/e15c096e-c885-4e7c-b7a1-fb6e755795f8" />

<img width="526" height="780" src="https://github.com/user-attachments/assets/cb2ca112-8e07-41d9-a7cc-d286a7d684fa" />

<img width="1261" height="953" alt="gui-1" src="https://github.com/user-attachments/assets/90471014-9753-4d1b-a004-66d0f439cf7d" />
<img width="1261" height="953" alt="gui-2" src="https://github.com/user-attachments/assets/1188fb61-830d-4218-b6a7-e62999cfdc75" />
<img width="1261" height="958" alt="gui-3" src="https://github.com/user-attachments/assets/73b04da5-b450-473a-af27-99695b913f9a" />


---

# ✨ Key Features (v1.9.3)

- 🔥 Immediate heating in all modes (no bed wait)
- 🔐 Global lock / unlock safety system
- ⚡ Stable power sync (no UI bounce or reset)
- 🧠 Slicer Priority Mode (M191 / M141 detection via Moonraker)
- 🔄 Full bidirectional MQTT sync (Home Assistant auto-discovery)
- 🎛 Dry mode support
- 📊 Live terminal monitor (flicker-free)
- 🔒 TLS secure connection (Port 8883)

---

# ➕ Firmware v1.0.3 Support

## Direct Klipper Binding
Firmware v1.0.3 allows direct connection to Klipper or a remote backend.

## Remote Backend (Raspberry Pi)
`Panda.py` can run on a separate system while the GUI connects via MQTT.

## Remote GUI Mode
- No local backend required
- GUI acts as control + monitoring interface only
- Start/Stop disabled in this mode

## MQTT Improvements
New topics:
- `panda_breath_mod/bed` → Bed temperature
- `panda_breath_mod/heizung` → Heater state (ON/OFF)

## Instant Mode Switching
- Immediate updates when switching Auto / Manual / Dry
- No stuck or outdated states

---

# 🔗 Binding (v1.0.3)

When using **Klipper + Panda Backend**:

👉 `Printer IP` = system running `Panda.py`

Example:

Printer IP → 192.168.8.8


⚠ Important:
- Panda connects to backend (not directly to Klipper)
- Backend handles MQTT, logic, Moonraker

---

# 🛠 How It Works

The script emulates a **Bambu-compatible printer** using Panda WebSocket protocol.

**Data flow:**

Moonraker → Home Assistant → Panda Logic Sync → Panda Touch


---

# 🧠 Heating Logic

## Immediate Heating (All Modes)

Heating starts instantly when:

Chamber Temp < Target - Hysteresis


- No bed wait
- No start delay

## Bed Temperature Role

Used only for:
- Safety limit
- Filter fan activation

If exceeded:

Bed Limit reached


(Heating still continues)

---

# 🔐 Lock System

**Button:** Heater Stop

Activates global lock:
- work_on = 0
- work_mode = 0
- set_temp = 0
- MQTT ignored

Unlock only via **Unlock button**

---

# ⚡ Power System

Switch:

switch.panda_breath_mod_panda_power


Fixes:
- No UI bounce
- No feedback loops
- Stable sync

---

# 🧩 Slicer Integration (OrcaSlicer)

Supports:

M191 Sxx
M141 Sxx


When **Slicer Priority Mode = ON**:
- Automatically sets chamber target

---

# 📦 Installation

## 1. Clone
```bash
git clone https://github.com/bdavj/BIQU-Panda-Breath-Mod.git
cd BIQU-Panda-Breath-Mod
2. Install Dependencies
sudo apt update
sudo apt install python3-pip -y
pip install asyncio websockets requests paho-mqtt
3. Generate SSL Certificates
chmod +x cert_gen.sh
./cert_gen.sh

Or manually:

openssl req -x509 -newkey rsa:4096 \
-keyout key.pem \
-out cert.pem \
-sha256 -days 3650 -nodes \
-subj "/C=DE/ST=Panda/L=Panda/O=Bambu/OU=Printer/CN=bambulab.local"
⚙ Configuration

Edit:

nano Panda.py

Configure:

MQTT (Broker, User, Password)
Panda (IP, SN, Access Code)
Home Assistant (Token, Sensor URL)
▶ Start
sudo python3 Panda.py

---

# 🐳 Docker

Run the backend as a container instead of `sudo python3 Panda.py`. Certificates
are generated automatically on first run and config comes from a `config.env`
file.

## Quick Start

```bash
git clone https://github.com/bdavj/BIQU-Panda-Breath-Mod.git
cd BIQU-Panda-Breath-Mod

# 1. Create your config from the template
cp config.env.example config.env
nano config.env          # fill in the values (see below)

# 2. Build and start
docker compose up -d --build

# 3. Follow the logs
docker compose logs -f
```

## Configuration (`config.env`)

All settings come from `config.env` (loaded via `env_file` in
`docker-compose.yml`). At minimum you must set:

| Variable | Description |
| --- | --- |
| `MQTT_BROKER` | IP/hostname of your MQTT broker (Home Assistant) |
| `MQTT_PORT` | MQTT port (default `1883`) |
| `MQTT_USER` / `MQTT_PASSWORD` | MQTT credentials |
| `PANDA_IP` | IP of the Panda Touch display |
| `PANDA_SN` | Printer serial number |
| `PANDA_ACCESS_CODE` | Printer access code |
| `HOST_IP` | IP of the host running the container (enter this as *Printer IP* in the Panda UI) |
| `HA_TOKEN` | Home Assistant long-lived access token |
| `HA_SENSOR_URL` | Full URL to the bed-temperature sensor, e.g. `http://homeassistant.local:8123/api/states/sensor.ks1c_bed_temperature` |

See `config.env.example` for the full list (including optional values like
`HYSTERESE`, `DEBUG`, and `PRINTER_IP`). Environment variables override
`panda_config.json`, so the existing standalone setup keeps working unchanged.

## Certificates

The TLS certificates (`cert.pem` / `key.pem`) are **generated automatically on
first run** into `./certs/` (mounted as `/certs` in the container) using the same
parameters as `cert_gen.sh`. They persist across restarts and rebuilds. To force
regeneration, delete `./certs/` and restart the container.

## `network_mode: host`

The compose file uses `network_mode: host` — this is **required**. The container
runs a TLS server on port `8883` and the Panda Touch connects directly to the
host's IP over WebSocket. With Docker's default bridge networking the Panda Touch
cannot reach the container, so host networking is non-negotiable here.

## Home Assistant Add-on

If you run **Home Assistant OS** or **Supervised**, you can install this as a
managed add-on instead of using `docker compose` — it shows up under
**Settings → Add-ons** with a configuration UI.

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Add `https://github.com/bdavj/BIQU-Panda-Breath-Mod` and close.
3. Install **Panda Breath Mod** from the store, fill in the options, and start it.

Notes:

- **MQTT credentials are auto-filled** from the Home Assistant MQTT integration —
  leave the `MQTT_*` options blank unless you want to override them.
- The add-on runs with **host networking** (`host_network: true`), required for the
  same reason as `network_mode: host` above: the Panda Touch connects directly to
  the host IP. MQTT *discovery* works regardless of network mode (it goes through
  the broker), so entities appear automatically.
- Certificates are auto-generated on first start into the add-on's persistent
  storage (`/data/certs`).

> HA **Container/Core** installs (HA running as a plain Docker container or in a
> venv) have no Supervisor and cannot run add-ons — use the `docker compose` setup
> above instead.

See [`addon/DOCS.md`](addon/DOCS.md) for the full option reference.

---

🔗 Binding

Open:

http://<PANDA_IP>

Enter:

Printer SN
Access Code
Printer IP → HOST_IP

⚠ Do NOT use Scan

📊 Live Monitor Example
READY | Bed:61° | Chamber:50/43° | Heat:ON | Fan:ON
🏠 Home Assistant Entities
Numbers
Chamber Target
Bed Limit
Filter Temp
Dry Temp
Dry Time
Switches
Panda Power
Slicer Priority Mode
Buttons
Auto
Manual
Dry
Heater Stop
Unlock
Sensors
Chamber Current
Slicer Target
Status
Mode
Lock State
Version
🛡 Safety Behavior
Situation	Result
HA sensor failure	Heating OFF
Lock active	Everything OFF
Work mode 0	Standby
Panda Power OFF	Shutdown
🖥 Panda Control GUI

Desktop GUI for controlling the Panda Breath Mod via MQTT.

Features
Start/Stop backend script
Live monitoring (temps, status, power, lock)
MQTT control (Auto, Manual, Dry, Power, Unlock)
Set values (temps, limits, timers)
Live log output
MQTT connection status display
Requirements
Python 3.10+
PySide6
paho-mqtt
Linux with pkexec

Install:

pip install PySide6 paho-mqtt
Start GUI
python3 PandaGui.py

Default script:

~/Panda/Panda.py
📡 MQTT Configuration
Broker: 192.168.x.xxx
Port: 1883
Topic prefix:
panda_breath_mod

Subscribes to:

panda_breath_mod/#
⚠ Current State

Still partially dependent on Home Assistant.

Planned Improvements
Remove Home Assistant dependency
Full MQTT-only system
Config file instead of hardcoded values
Better error handling
Cleaner architecture
Optional standalone Linux app
📝 License

MIT License

⚠ Disclaimer

Use at your own risk.
Always follow fire safety regulations when operating heated 3D printer enclosures.


---

## 🕹️ Live bOX BBS

Want to see this project in action? Connect to my live old-school **PCBoard bOX BBS** over SSH.

```text
Host:     mybbs.duckdns.org
Port:     2222
Protocol: SSH
Login:    bbs
Password: bbs
```

Example:

```bash
ssh bbs@mybbs.duckdns.org -p 2222
```

For the best ANSI/PCBoard experience, use the preconfigured SyncTERM package included in this repository:

```text
syncterm/syncterm_v1.9.rc3_bOX_ALL_BUILDS.zip
```

Included builds:

```text
Win_x86
Win_x64
Linux_x86
Linux_x64
```

The SyncTERM package is already configured for the bOX BBS. You can also connect with any ANSI-capable terminal such as SyncTERM, ZOC, NetRunner, PuTTY, or another classic Telnet/ANSI client.

> Nostalgia mode: real old-school PCBoard BBS experience.
