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
   
  - Panda Web-UI  
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

## 🛠️ Funktionsweise

Der Mod nutzt das **Bambu Lab Protokoll**, um dem Panda-Ökosystem eine kompatible Hardware vorzugaukeln.  
Dadurch akzeptiert die Panda Breath externe Temperaturdaten als „interne“ Werte und erlaubt die Nutzung der **nativen Automatik-Logik** für **beliebige Druckermodelle**.

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
<img width="1807" height="829" alt="image" src="https://github.com/user-attachments/assets/ce9f1d40-4b09-4ee6-a1c8-edeed70f5ccd" />

⚠️ Wichtig:
Nicht auf „Scan“ klicken – der Drucker-Simulator wird beim Scan nicht gefunden.

Klicke direkt auf Bind

Sobald der Button zu Unbind wechselt, ist die Verbindung aktiv und die Panda Breath übernimmt die externen Werte.

📊 Dashboard & Monitoring
Home Assistant Dashboard (Beispiel)

<img width="1835" height="836" alt="image" src="https://github.com/user-attachments/assets/1b1b7d8a-9fc1-4e6f-ab15-3ba944f3f9ea" />
<img width="792" height="449" alt="image" src="https://github.com/user-attachments/assets/90d64e87-a897-43da-98b1-40d9bb3744b2" />
<img width="1069" height="840" alt="image" src="https://github.com/user-attachments/assets/72258e1e-06aa-4c5c-93d3-575d843aae0a" />


Live-Terminal-Monitor

Dank optimiertem Cursor-Handling erfolgt die Anzeige ruhig und flackerfrei:
<img width="734" height="108" alt="image" src="https://github.com/user-attachments/assets/1c299495-bc72-43b2-b603-89f91ebd40b6" />

📝 Lizenz & Disclaimer

Dieses Projekt steht unter der MIT-Lizenz.

Disclaimer:
Die Nutzung erfolgt auf eigene Gefahr.
Achte stets auf die geltenden Brandschutzbestimmungen deines 3D-Druckers sowie deiner lokalen Umgebung.





