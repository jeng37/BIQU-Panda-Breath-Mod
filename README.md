![GitHub Views](https://komarev.com/ghpvc/?username=DeinGitHubUsername&repo=BIQU-Panda-Breath-Mod&style=flat-square)
# BIQU-Panda-Breath-Mod 🚀

Eine intelligente Steuerung für die **BIQU Panda Breath** Bauraumheizung.  
Dieses Skript simuliert einen **Bambu Lab Drucker** auf einem Host-System (PC/Server) und ermöglicht es, die Heizung basierend auf **realen Temperaturdaten aus Home Assistant** (via Moonraker/Klipper) zu steuern.

---

## ✨ Key Features

- **Universelle Auto-Funktion**  
  Schaltet die intelligente Automatik des Panda Breath für **jedes Druckermodell** frei (Voron, Creality, Anycubic usw.).  
  Voraussetzung: Der Drucker ist in Home Assistant eingebunden – dieses Skript fungiert als Protokoll-Übersetzer.

- **Bidirektionaler MQTT-Sync**  
  Volle Kontrolle über Home Assistant.  
  Werte werden synchron gehalten zwischen:
   
- Home Assistant  
  *(HA → Panda und Panda → HA)*

- **Intelligente Hysterese**  
  Präzise Steuerung mit konfigurierbarer Schaltschwelle, um unnötig häufiges Schalten der Hardware zu vermeiden.

- **Sicherheits-Cutoff**  
  Automatischer Heiz-Stopp basierend auf der Betttemperatur  
  (Druckende-Erkennung über Home Assistant Sensor).

- **Live-Monitor**  
  Hochoptimierte **Ein-Zeilen-Terminalanzeige** inklusive ANSI-Cursor-Fix für maximale Übersicht **ohne Flackern**.

---

## 🛠️ Funktionsweise & Slicer-Support

Der Mod nutzt das **Bambu Lab Protokoll**, um dem Panda-Ökosystem eine kompatible Hardware vorzugaukeln. Dadurch akzeptiert die Panda Breath externe Temperaturdaten als „interne“ Werte und erlaubt die Nutzung der **nativen Automatik-Logik**.

### OrcaSlicer Integration
In **OrcaSlicer** kann unter den Filamenteinstellungen (`Filament` -> `Cooling`) die Kammertemperatur aktiviert werden. Das Skript scannt den G-Code-Header via Moonraker-API und setzt den Wert (z. B. 42°C) automatisch als `Kammer Soll`.

<img width="931" height="781" alt="Screenshot from 2026-02-19 07-12-31" src="https://github.com/user-attachments/assets/bb5a8699-3e3f-45b9-a11f-f408459e9dbf" />


---

## 🚀 Installation & Setup

### 1. System vorbereiten

Das Host-System (Server oder PC) muss sich im **selben Netzwerk** wie die Panda Breath befinden.

```bash
# Repository klonen
git clone https://github.com/jeng37/BIQU-Panda-Breath-Mod.git
cd BIQU-Panda-Breath-Mod

# Abhängigkeiten installieren
pip install -r requirements.txt

# SSL-Zertifikate generieren (wichtig für die verschlüsselte Verbindung)
chmod +x cert_gen.sh
./cert_gen.sh
```
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
Anschließend starten
(sudo wird benötigt wegen Port 8883):
```bash
sudo python3 Panda.py
```
3. Verbindung herstellen (Binding)

Öffne die Panda Web-UI im Browser:
http://<PANDA_IP>

Trage manuell ein:

Printer SN / 
Access Code / 
Printer IP → IP deines Host-Systems
<img width="1864" height="932" alt="image" src="https://github.com/user-attachments/assets/cb2b26c5-3f24-4ba3-904a-0a7f5e6e76ac" />


⚠️ Wichtig:
Nicht auf „Scan“ klicken – der Drucker-Simulator wird beim Scan nicht gefunden.

Klicke direkt auf Bind

Sobald der Button zu Unbind wechselt, ist die Verbindung aktiv und die Panda Breath übernimmt die externen Werte.

📊 Dashboard & Monitoring
Home Assistant Dashboard (Beispiel)

<img width="1835" height="836" alt="image" src="https://github.com/user-attachments/assets/1b1b7d8a-9fc1-4e6f-ab15-3ba944f3f9ea" />
<img width="510" height="617" alt="image" src="https://github.com/user-attachments/assets/11cb85bf-6958-4620-b237-6a130bea637a" />
<img width="1519" height="790" alt="image" src="https://github.com/user-attachments/assets/450b3fa4-51ad-4219-89e7-ff3abf4ad2d8" />
<img width="1511" height="606" alt="image" src="https://github.com/user-attachments/assets/9265ca56-cee2-455b-b43a-f306706e9709" />

Live-Terminal-Monitor

Dank optimiertem Cursor-Handling erfolgt die Anzeige ruhig und flackerfrei:

<img width="1467" height="264" alt="image" src="https://github.com/user-attachments/assets/020dd9ee-66c3-40db-b827-0f8574147a4b" />

📝 Lizenz & Disclaimer

Dieses Projekt steht unter der MIT-Lizenz.

Disclaimer:
Die Nutzung erfolgt auf eigene Gefahr.
Achte stets auf die geltenden Brandschutzbestimmungen deines 3D-Druckers sowie deiner lokalen Umgebung.

