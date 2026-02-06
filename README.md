# BIQU-Panda-Breath-Mod 🚀

Eine intelligente Steuerung für die **BIQU Panda Breath** Bauraumheizung. Dieses Skript simuliert einen Bambu Lab Drucker auf einem Host-System (PC/Server) und ermöglicht es, die Heizung basierend auf realen Temperaturdaten von **Home Assistant** (via Moonraker) zu steuern.

## ✨ Features
- **Intelligente Hysterese:** Verhindert schnelles Schalten des Relais (1°C Spanne).
- **Sicherheits-Cutoff:** Schaltet die Heizung automatisch ab, wenn das Druckbett unter 50°C fällt (Druckende-Erkennung).
- **Live-Monitor:** Saubere Ein-Zeilen-Anzeige im Terminal für HA-Werte, Zieltemperatur und Relais-Status.
- **Dynamic Sync:** Übernimmt Zieltemperaturen sofort aus der Panda Web-UI.

---

## 🛠️ Installation & Setup

### 1. System vorbereiten
Das Host-System (Server/PC) muss sich im **selben Netzwerk** wie die Panda Breath befinden.

```bash
# Repository klonen
git clone [https://github.com/DEIN_USER/BIQU-Panda-Breath-Mod.git](https://github.com/DEIN_USER/BIQU-Panda-Breath-Mod.git)
cd BIQU-Panda-Breath-Mod

# Abhängigkeiten installieren
pip install -r requirements.txt
