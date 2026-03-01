![GitHub Views](https://komarev.com/ghpvc/?username=jeng37&repo=BIQU-Panda-Breath-Mod&style=flat-square&label=Repository+Views&color=blue)

# BIQU-Panda-Breath-Mod 🚀
### Panda-Logic-Sync v1.9

Intelligent control for the **BIQU Panda Breath** chamber heater.

This script simulates a **Bambu Lab printer** on a host system (PC/Server) and enables fully synchronized, intelligent chamber heating based on **real-time Home Assistant temperature data**.

# 🛠 How It Works

The script emulates a **Bambu-compatible printer** using the native Panda WebSocket protocol.

Data flow:

![GitHub Views](https://komarev.com/ghpvc/?username=jeng37&repo=BIQU-Panda-Breath-Mod&style=flat-square&label=Repository+Views&color=blue)

# BIQU-Panda-Breath-Mod 🚀
### Panda-Logic-Sync v1.9

Intelligent control for the **BIQU Panda Breath** chamber heater.

This script simulates a **Bambu Lab printer** on a host system (PC/Server) and enables fully synchronized, intelligent chamber heating based on **real-time Home Assistant temperature data**.

---

## ✨ Key Features (v1.9)

- 🔥 **Immediate Heating in ALL Modes**  
  No more “wait for bed temperature”. Chamber heating starts instantly when needed.

- 🔐 **Lock / Unlock Safety System**  
  Emergency stop with global lock protection.

- ⚡ **Power Sync Fix**  
  Eliminates ON → OFF bounce and UI reset issues.

- 🧠 **Slicer Priority Mode**  
  Automatically reads `M191` / `M141` from G-code via Moonraker.

- 🔄 **Bidirectional MQTT Sync**  
  Full Home Assistant integration with auto-discovery.

- 🎛 **Dry Mode Support**

- 📊 **Live Terminal Monitor (flicker-free)**

- 🔒 **TLS Secure Connection (Port 8883)**

---

# 🛠 How It Works

The script emulates a **Bambu-compatible printer** using the native Panda WebSocket protocol.

Data flow:
![GitHub Views](https://komarev.com/ghpvc/?username=jeng37&repo=BIQU-Panda-Breath-Mod&style=flat-square&label=Repository+Views&color=blue)

# BIQU-Panda-Breath-Mod 🚀
### Panda-Logic-Sync v1.9

Intelligent control for the **BIQU Panda Breath** chamber heater.

This script simulates a **Bambu Lab printer** on a host system (PC/Server) and enables fully synchronized, intelligent chamber heating based on **real-time Home Assistant temperature data**.

---

## ✨ Key Features (v1.9)

- 🔥 **Immediate Heating in ALL Modes**  
  No more “wait for bed temperature”. Chamber heating starts instantly when needed.

- 🔐 **Lock / Unlock Safety System**  
  Emergency stop with global lock protection.

- ⚡ **Power Sync Fix**  
  Eliminates ON → OFF bounce and UI reset issues.

- 🧠 **Slicer Priority Mode**  
  Automatically reads `M191` / `M141` from G-code via Moonraker.

- 🔄 **Bidirectional MQTT Sync**  
  Full Home Assistant integration with auto-discovery.

- 🎛 **Dry Mode Support**

- 📊 **Live Terminal Monitor (flicker-free)**

- 🔒 **TLS Secure Connection (Port 8883)**

---

# 🛠 How It Works

The script emulates a **Bambu-compatible printer** using the native Panda WebSocket protocol.

Data flow:
Moonraker → Home Assistant → Panda-Logic-Sync → Panda Touch


The Panda Breath believes it is connected to a real printer and therefore enables its internal automation logic.

---

# 🧠 Heating Logic (v1.9)

## Immediate Heating

In ALL modes:

- Auto  
- Manual  
- Slicer  
- Dry  

Heating starts immediately when:
Chamber Temp < Target - Hysteresis


❌ No bed wait  
❌ No start blocker  

---

## Bed Temperature Logic

Bed temperature is now used only for:

- Safety limit
- Filter fan activation

If:
Bed ≥ Bed Limit
Status will show:

Bed Limit reached


But chamber control remains active.

---

# 🔐 Lock System

Button: **Heizung Stop**

Activates GLOBAL LOCK:

- work_on = 0  
- work_mode = 0  
- set_temp = 0  
- MQTT commands ignored  

Unlock only possible via:
Unlock Button

---

# ⚡ Power System

Switch:
switch.panda_breath_mod_panda_power


Fixes:

- No UI bounce
- No WebSocket feedback loop
- Stable power sync

---

# 🧩 Slicer Integration (OrcaSlicer)

Enable chamber temperature in filament settings.

The script scans the G-code header via Moonraker:
M191 S42
M141 S42

Automatically sets "ORCAs" detected value as Chamber Target when:
Slicer Priority Mode = ON

---

# 📦 Installation

## 1️⃣ Clone Repository

```bash
git clone https://github.com/jeng37/BIQU-Panda-Breath-Mod.git
cd BIQU-Panda-Breath-Mod

2️⃣ Install Dependencies

sudo apt update
sudo apt install python3-pip -y
pip install asyncio websockets requests paho-mqtt

3️⃣ Generate SSL Certificates
Required for Panda connection:

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

MQTT
Broker IP
Username
Password
Panda Hardware
Panda IP
Printer SN
Access Code
Home Assistant
Long-Lived Access Token
Sensor URL

▶ Start Script

sudo python3 Panda.py
(Port 8883 requires root)

🔗 Binding Process
Open Panda Web UI:
http://<PANDA_IP>

Enter:

Printer SN
Access Code
Printer IP → HOST_IP

⚠ Do NOT use Scan
Click Bind directly.

When it changes to Unbind, connection is active.

📊 Live Terminal Monitor
Example:
🟢 READY | Bed:61° | Kammer:50/43° | Heiz:AN | Fan:ON | Heizen... | NORMAL:0°
Field	Meaning
Bed	Bed temperature
Kammer	Target / Current
Heiz	Relay state
Fan	Filter fan
NORMAL / SL-PRIO	Slicer mode

🏠 Home Assistant Entities (Auto-Discovery)
Numbers

Kammer Soll
Bett Limit
Filter Temp
Dry Temp
Dry Time

Switches

Panda Power
Slicer Priority Mode

Buttons

Auto
Manual
Drying
Heizung Stop
Unlock

Sensors

Kammer Ist
Slicer Soll
Slicer Target Temp
Panda Status
Panda Modus
Lock Status
Version

🛡 Safety Behaviour
Situation	Result
HA sensor failure	Heating OFF
Lock active	Everything OFF
Work mode 0	Standby
Panda Power OFF	Hard shutdown

📝 License

MIT License

⚠ Disclaimer

Use at your own risk.
Always follow fire safety regulations when operating heating devices in 3D printer enclosures.
