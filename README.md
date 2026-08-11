<!-- REPO_VIEWS_BADGE_START -->
![Repository Views](https://img.shields.io/badge/Repository%20Views-11941-blue?style=flat-square)
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
git clone https://github.com/jeng37/BIQU-Panda-Breath-Mod.git
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
