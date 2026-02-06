# BIQU-Panda-Breath-Mod 🚀

Eine intelligente Steuerung für die **BIQU Panda Breath** Bauraumheizung. Dieses Skript simuliert einen Bambu Lab Drucker auf einem Host-System (PC/Server) und ermöglicht es, die Heizung basierend auf realen Temperaturdaten von **Home Assistant** (via Moonraker) zu steuern.

## ✨ Features
- **Intelligente Hysterese:** Verhindert schnelles Schalten des Relais (1°C Spanne).
- **Sicherheits-Cutoff:** Schaltet die Heizung automatisch ab, wenn das Druckbett unter 50°C fällt (Druckende-Erkennung).
- beispiel:
- <img width="1835" height="836" alt="image" src="https://github.com/user-attachments/assets/692eb6bf-31bb-4c4f-b39f-48d98bb463d0" />

- **Live-Monitor:** Saubere Ein-Zeilen-Anzeige im Terminal für HA-Werte, Zieltemperatur und Relais-Status.
- **Dynamic Sync:** Übernimmt Zieltemperaturen sofort aus der Panda Web-UI.

---

## 🛠️ Installation & Setup

### 1. System vorbereiten
Das Host-System (Server/PC) muss sich im **selben Netzwerk** wie die Panda Breath befinden.

```bash
# Repository klonen
git clone https://github.com/DEIN_USER/BIQU-Panda-Breath-Mod.git
cd BIQU-Panda-Breath-Mod

# Abhängigkeiten installieren
pip install -r requirements.txt

# SSL-Zertifikate generieren
Die Hardware benötigt eine verschlüsselte Verbindung. Nutze das mitgelieferte Hilfsskript:

chmod +x cert_gen.sh
./cert_gen.sh

# Panda.py configuration
nano Panda.py

# danach starten
sudo python3 Panda.py
```
### 2. Verbindung herstellen
1. Öffne die Panda Web-UI (`http://<PANDA_IP>`).
2. Trage **Printer SN**, **Access Code** und die **Printer IP** (deine `HOST_IP`) manuell ein.
 - <img width="1807" height="829" alt="image" src="https://github.com/user-attachments/assets/6e57abe3-633a-431b-8f70-e4918ec9adeb" />

4. **Wichtig:** Drücke **NICHT** auf "Scan". Der Drucker-Simulator wird beim Scan nicht gefunden.
5. Klicke direkt auf den Button **Bind**.
6. Sobald der Button zu **Unbind** wechselt, steht die Verbindung.

Im Terminal sollte es jetzt so aussehen:
 - <img width="1327" height="58" alt="image" src="https://github.com/user-attachments/assets/9b9942e1-35ad-4af5-8ad4-33dde610baf2" />
