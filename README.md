![GitHub Views](https://komarev.com/ghpvc/?username=jeng37&repo=BIQU-Panda-Breath-Mod&style=flat-square)

Intelligent control for the **BIQU Panda Breath** chamber heater.
# BIQU-Panda-Breath-Mod 🚀

Intelligent control for the **BIQU Panda Breath** chamber heater.  
This script simulates a **Bambu Lab printer** on a host system (PC/Server), allowing the heater to be controlled based on **real-time temperature data from Home Assistant**.

---

## ✨ Key Features

- **Universal Auto-Function** Unlocks the intelligent automatic mode of the Panda Breath for **any printer model** (Voron, Creality, Anycubic, etc.).  
  *Requirement:* The printer must be integrated into Home Assistant (e.g., via the [Moonraker Home Assistant Integration](https://github.com/marcolivierarsenault/moonraker-home-assistant)) – this script acts as the protocol translator.

- **Bidirectional MQTT Sync** Full control via Home Assistant.  
  Values are kept in sync between:
  - Home Assistant  
  - *(HA → Panda and Panda → HA)*

- **Intelligent Hysteresis** Precise control with a configurable switching threshold to prevent excessive hardware cycling.

- **Safety Cutoff** Automatic heating stop based on bed temperature  
  (End-of-print detection via Home Assistant sensor).

- **Live Monitor** Highly optimized **single-line terminal display** including an ANSI cursor fix for maximum clarity **without flickering**.

---

## 🛠️ How it Works & Slicer Support

The mod utilizes the **Bambu Lab protocol** to spoof compatible hardware for the Panda ecosystem. This allows the Panda Breath to accept external temperature data as "internal" values and utilize its **native automation logic**.

### OrcaSlicer Integration
In **OrcaSlicer**, you can enable the chamber temperature under filament settings (`Filament`). The script scans the G-code header via the Moonraker API and automatically sets the value (e.g., 42°C) as the `Chamber Target`.

<img width="931" height="781" alt="Screenshot from 2026-02-19 07-12-31" src="https://github.com/user-attachments/assets/bb5a8699-3e3f-45b9-a11f-f408459e9dbf" />

---

## 🚀 Installation & Setup

### 1. Prepare the System

The host system (Server or PC) must be in the **same network** as the Panda Breath.

```bash

# Clone the repository
git clone [https://github.com/jeng37/BIQU-Panda-Breath-Mod.git](https://github.com/jeng37/BIQU-Panda-Breath-Mod.git)
cd BIQU-Panda-Breath-Mod

# Install dependencies
pip install -r requirements.txt

# Generate SSL certificates (essential for the encrypted connection)
chmod +x cert_gen.sh
./cert_gen.sh
2. Konfiguration

Öffne die Datei Panda.py und passe die Konfigurationssektion an.
Alle Parameter sind im Skript selbst ausführlich dokumentiert.

Benötigte Angaben:

MQTT
Broker-IP
Benutzername
Passwort
Panda Breath Hardware
Panda-IP
Printer Serial Number (SN)
Access Code
Home Assistant
Long-Lived Access Token
Sensor-URL
```bash
nano Panda.py
```
2. Configuration
Open the Panda.py file and adjust the configuration section. All parameters are extensively documented within the script itself.

Required Information:

MQTT: Broker IP, Username, Password

Panda Breath Hardware: Panda IP, Printer Serial Number (SN), Access Code

Home Assistant: Long-Lived Access Token, Sensor URL

Bash
nano Panda.py
Afterward, start the script (sudo is required for port 8883):

Bash
sudo python3 Panda.py
3. Establish Connection (Binding)
Open the Panda Web UI in your browser:

http://<PANDA_IP>

Enter the following manually:

Printer SN

Access Code

Printer IP → The IP of your host system

<img width="1864" height="932" alt="image" src="https://github.com/user-attachments/assets/cb2b26c5-3f24-4ba3-904a-0a7f5e6e76ac" />

⚠️ Important: Do not click "Scan" – the printer simulator will not be found via scanning. Click Bind directly.

Once the button changes to "Unbind", the connection is active and the Panda Breath will use the external values.

📊 Dashboard & Monitoring
Home Assistant Dashboard (Example)
<img width="1835" height="836" alt="image" src="https://github.com/user-attachments/assets/1b1b7d8a-9fc1-4e6f-ab15-3ba944f3f9ea" />
<img width="510" height="617" alt="image" src="https://github.com/user-attachments/assets/11cb85bf-6958-4620-b237-6a130bea637a" />
<img width="1519" height="790" alt="image" src="https://github.com/user-attachments/assets/450b3fa4-51ad-4219-89e7-ff3abf4ad2d8" />
<img width="1511" height="606" alt="image" src="https://github.com/user-attachments/assets/9265ca56-cee2-455b-b43a-f306706e9709" />

Live Terminal Monitor
Thanks to optimized cursor handling, the display is smooth and flicker-free:

<img width="1467" height="264" alt="image" src="https://github.com/user-attachments/assets/020dd9ee-66c3-40db-b827-0f8574147a4b" />

📝 License & Disclaimer
This project is licensed under the MIT License.

Disclaimer: Use at your own risk. Always pay attention to the applicable fire safety regulations for your 3D printer and your local environment.
