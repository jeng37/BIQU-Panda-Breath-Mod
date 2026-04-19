<!-- REPO_VIEWS_BADGE_START -->
![Repository Views](https://img.shields.io/badge/Repository%20Views-3433-blue?style=flat-square)
<!-- REPO_VIEWS_BADGE_END -->

![GitHub Views](https://komarev.com/ghpvc/?username=jeng37&repo=BIQU-Panda-Breath-Mod&style=flat-square&label=Repository+Views&color=blue)

# BIQU-Panda-Breath-Mod 🚀
### Panda-Logic-Sync v1.9.3 Bug Fixes.

Intelligent control for the **BIQU Panda Breath** chamber heater.

This script simulates a **Bambu Lab printer** on a host system (PC/Server) and enables fully synchronized, intelligent chamber heating based on **real-time Home Assistant temperature data**.

<img width="1839" height="912" alt="Screenshot from 2026-03-01 10-36-31" src="https://github.com/user-attachments/assets/50aab4bf-ccf9-4eea-8567-7ef40c84fd36" />

<img width="1329" height="897" alt="Screenshot from 2026-03-01 10-37-42" src="https://github.com/user-attachments/assets/89309991-4a4c-4611-bd0c-f5e7c97c90c9" />
<img width="1329" height="897" alt="Screenshot from 2026-03-01 10-37-47" src="https://github.com/user-attachments/assets/e15c096e-c885-4e7c-b7a1-fb6e755795f8" />

<img width="526" height="780" alt="Screenshot from 2026-03-01 10-35-56" src="https://github.com/user-attachments/assets/cb2ca112-8e07-41d9-a7cc-d286a7d684fa" />

## ✨ Key Features (v1.9.3)

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

## ➕ Firmware v1.0.3 Support (NEW)

### 🔗 Direct Klipper Binding Support
Panda Firmware **v1.0.3** allows direct binding to Klipper or host systems.

### 🌐 Remote Backend Support (Raspberry Pi)
`Panda.py` can now run on a separate system (e.g. Raspberry Pi), while the GUI connects remotely.

### 🖥 Remote GUI Mode
The Panda GUI can operate fully via MQTT:

- No local backend execution required
- GUI acts as a pure control and monitoring interface

### 🔄 Improved MQTT State Sync
New MQTT topics:

- `panda_breath_mod/bed` → Bed temperature
- `panda_breath_mod/heizung` → Heater state (ON / OFF)

### ⚡ Instant Mode Switching Fix
- Heater state updates instantly when switching between **Auto / Manual / Dry**
- No more “stuck” or outdated states

---

## 🔗 Binding Process (Firmware v1.0.3 Update)

### ➕ New (v1.0.3)

When using **Klipper + Panda Backend (e.g. Raspberry Pi)**:

👉 `Printer IP` must point to the system running `Panda.py`

**Example:**

```text
Printer IP → 192.168.8.8

⚠ Important:

The Panda connects to the backend → not directly to Klipper
The backend (Panda.py) handles all logic, MQTT, and Moonraker communication
🖥 Panda Control GUI (v1.0.3 Update)

➕ Remote Mode (NEW)

The GUI now supports Remote Backend Mode:

No local script execution required
GUI communicates only via MQTT
Backend runs independently (e.g. Raspberry Pi service)

Behavior:

Start / Stop buttons are disabled in Remote Mode
GUI acts as pure control & monitoring interface
📡 MQTT Topics (NEW)

Additional topics introduced with v1.0.3 support:

Topic	Description
panda_breath_mod/bed	Current bed temperature
panda_breath_mod/heizung	Heater state (AN / AUS)
⚠ Important Notes (v1.0.3)
TLS certificates (cert.pem, key.pem) are required for Panda connection
Backend must run continuously (systemd recommended)
MQTT must be reachable from both:
Panda backend (Raspberry Pi)
GUI (Workstation)
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

### NEW ###
# Panda Control GUI

Eine Desktop-GUI für die Steuerung und Überwachung des **Panda Breath Mod** über **MQTT**.  
Die Anwendung wurde mit **Python** und **PySide6** entwickelt und bietet eine einfache Oberfläche, um Statuswerte anzuzeigen, Modi umzuschalten und Sollwerte direkt zu senden.

## Funktionen

- Starten und Stoppen des Hauptskripts direkt aus der GUI
- Live-Anzeige von:
  - Status
  - Bett-Temperatur
  - Kammer-Soll / Kammer-Ist
  - Heizstatus
  - Lüfterstatus
  - Lock-Status
  - Panda Power
  - Version
  - Slicer-Zieltemperatur
- Steuerung per MQTT:
  - Auto-Modus
  - Manueller Modus
  - Dry-Modus
  - Heizung stoppen
  - Unlock
  - Slicer Mode ein/aus
  - Panda Power ein/aus
- Setzen von:
  - Bett-Limit
  - Kammer-Solltemperatur
  - Filter-Fan-Starttemperatur
  - Dryer-Temperatur
  - Dryer-Zeit
- Live-Log-Ausgabe des gestarteten Python-Skripts
- MQTT-Verbindungsstatus direkt in der GUI sichtbar

---

## Voraussetzungen

- Python 3.10+
- [PySide6](https://pypi.org/project/PySide6/)
- [paho-mqtt](https://pypi.org/project/paho-mqtt/)
- Linux-System mit `pkexec`, da das Hauptskript aktuell mit Root-Rechten gestartet wird

Installation der Python-Abhängigkeiten:

```bash
pip install PySide6 paho-mqtt

Starten

Die GUI kann direkt mit Python gestartet werden:

python3 PandaGui.py

Standardmäßig wird folgendes Hauptskript verwendet:

~/Panda/Panda-1.py

Dieses kann in der GUI aber auch über „Skript wählen“ geändert werden.

MQTT-Konfiguration

Aktuell sind die MQTT-Zugangsdaten direkt im Quellcode hinterlegt:

Broker: 192.168.8.195

Port: 1883

Benutzer: mqttadmin

Topic-Präfix:

panda_breath_mod

Die GUI subscribed auf:

panda_breath_mod/#

und veröffentlicht Steuerbefehle unter den jeweiligen /set Topics.

Wichtiger Hinweis: Aktueller Stand
Der aktuelle Stand ist noch Home-Assistant-abhängig

Auch wenn diese GUI bereits direkt per MQTT arbeitet, ist das Gesamtsystem im Moment noch teilweise von Home Assistant abhängig.

Das bedeutet:

Einige States bzw. Automationen kommen derzeit noch aus der bestehenden Home-Assistant-Umgebung

Die aktuelle Struktur ist noch nicht vollständig als unabhängige Standalone-MQTT-Lösung ausgelegt

Home Assistant übernimmt derzeit noch Teile der Logik bzw. Integration im Gesamtsystem

Ziel für spätere Versionen

Das wird in einer späteren Version geändert.

Geplant ist, das System so umzubauen, dass keine Home-Assistant-Abhängigkeit mehr besteht und die Anwendung bzw. das Gesamtsystem nur noch MQTT benötigt.

Das Ziel ist also:

kein Home Assistant mehr notwendig

direkte Kommunikation ausschließlich über MQTT

einfachere Integration in andere Systeme

leichtere Portierbarkeit und weniger externe Abhängigkeiten

Bedienung
Prozesssteuerung

Start startet das gewählte Hauptskript per pkexec

Stop beendet das laufende Skript

Log leeren leert die Log-Ausgabe

Modi

Auto → sendet auto/set = 1

Manuell → sendet manual/set = PRESS

Dry → sendet drying/set = 1

Weitere Befehle

Stop Heizen → heizung_stop/set = PRESS

Unlock → unlock/set = PRESS

Slicer Mode → slicer_priority_mode/set = ON/OFF

Panda Power → panda_power/set = ON/OFF

Sollwerte

Die GUI kann folgende Werte direkt senden:

Bett Limit → limit/set

Kammer Soll → soll/set

Filter Fan Start → filtertemp/set

Dryer Temp → dry_temp/set

Dryer Time → dry_time/set

Hinweise zur aktuellen Implementierung

Das Hauptskript wird derzeit mit Root-Rechten über pkexec gestartet

Die GUI verarbeitet eingehende MQTT-Nachrichten direkt und aktualisiert die Oberfläche live

Zusätzlich werden Statuszeilen aus der Skriptausgabe per Regex geparst und in der GUI dargestellt

ANSI-Steuerzeichen aus der Terminalausgabe werden entfernt, damit das Log sauber lesbar bleibt

Roadmap

 Home-Assistant-Abhängigkeit entfernen

 Reiner MQTT-Betrieb

 MQTT-Konfiguration aus Datei statt fest im Code

 Bessere Fehlerbehandlung und Rückmeldungen

 Saubere Trennung zwischen GUI, MQTT-Client und Prozesssteuerung

 Optional: Packaging als eigenständige Linux-App

📝 License

MIT License

⚠ Disclaimer

Use at your own risk.
Always follow fire safety regulations when operating heating devices in 3D printer enclosures.
