#!/usr/bin/env python3
import asyncio, ssl, json, time, requests, websockets, os
import logging
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

# ============================================================
# ✅ FIX / ERWEITERUNG: SLICER MODE + FEHLENDE ENTITÄTEN (HA)
# ------------------------------------------------------------
# - Implementiert "Slicer Priority Mode" (Switch)
# - Implementiert "Heizung Stop" (Button)
# - Implementiert Slicer-Auto-Erkennung (G-Code Analyse via Moonraker)
# - Fügt fehlende MQTT Discovery Entities hinzu (damit "Entity not found" weg ist)
# - Entfernt NICHTS: Original bleibt, Erweiterungen sind additiv/ersetzend innerhalb
#   der bestehenden Struktur (nur ergänzt/erweitert).
# ============================================================

# ==========================================
# KONFIGURATION - BITTE HIER ANPASSEN
# ==========================================
# Konsolen-Ausgabe: True zeigt detaillierte MQTT-Befehle im Terminal, False hält es sauber.
DEBUG = False
# Logging: True speichert alle Ereignisse (Verbindungen, Fehler, Sync) in 'panda_debug.log'.
DEBUG_TO_FILE = True
# Schaltschwelle: Temperatur muss um diesen Wert unter 'Soll' fallen, bevor wieder geheizt wird.
HYSTERESE = 1.5
# Schutzzeit: Mindestpause (in Sek.) zwischen zwei Schaltvorgängen, um die Hardware zu schonen.
MIN_SWITCH_TIME = 10
# MQTT Broker Adresse: Die IP-Adresse deines Home Assistant oder MQTT-Servers.
MQTT_BROKER = "192.168.8.195"
# MQTT Benutzername: In HA unter Einstellungen -> Personen -> Benutzer angelegt.
MQTT_USER = "mqttadmin"
# MQTT Passwort: Das zugehörige Passwort für den MQTT-Benutzer.
MQTT_PASS = "rootlu"

# MQTT Präfix: Die Basis für alle Topics (z.B. panda_breath_mod/soll).
# ⚠️ WICHTIG: Deine Screenshots zeigen entity_ids wie:
# - button.panda_breath_mod_heizung_stop
# - switch.panda_breath_mod_slicer_priority_mode
# - sensor.panda_breath_mod_slicer_target_temp
# Darum MUSS der Prefix "panda_breath_mod" sein, sonst passt HA/YAML nicht.
MQTT_TOPIC_PREFIX = "panda_breath_mod"

# Host IP: Die statische IP-Adresse des Rechners, auf dem dieses Skript läuft.
HOST_IP = "192.168.8.174"
# Panda IP: Die IP-Adresse deines Panda Touch Displays im WLAN.
PANDA_IP = "192.168.8.142"
# Seriennummer: Die SN deines Druckers (findest du in der Panda-UI oder auf dem Sticker).
PRINTER_SN = "01P00A123456789"
# Access Code: Der Sicherheitscode deines Druckers für die WebSocket-Verbindung.
ACCESS_CODE = "01P00A12"
# HA API URL: Link zum Bett-Temperatur-Sensor deines Druckers in Home Assistant.
HA_URL = "http://192.168.8.195:8123/api/states/sensor.ks1c_bed_temperature"
# HA Token: Ein 'Long-Lived Access Token' (erstellt im HA-Profil ganz unten).
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJmZjg4NzFjOTRiMTc0OTJlYTE4MWVhNDY1YmI5M2JjNiIsImlhdCI6MTc3MDI5OTE1OSwiZXhwIjoyMDg1NjU5MTU5fQ.Biu6Ood1bH-xMBHQnfRFE6h2yiFMWWywTfCnFmji61o"

# ============================================================
# ✅ SLICER MODE (NEU)
# ------------------------------------------------------------
# PRINTER_IP = IP vom Drucker / Moonraker (für Gcode-File Analyse)
# Funktion: liest beim Druckstart die ersten Bytes der Gcode Datei,
# sucht M191 Sxx / M141 Sxx und setzt slicer_soll.
# ============================================================
PRINTER_IP = "192.168.8.140"
# ==========================================

# current_data nutzt jetzt die exakten Namen aus der Hardware (filament_temp/timer)
current_data = {
    "kammer_soll": 0.0,
    "kammer_ist": 0.0,
    "bett_limit": 50.0,
    "filtertemp": 30.0,
    "filament_temp": 45,
    "filament_timer": 3,

    # ========================================================
    # ✅ SLICER MODE STATE (NEU)
    # --------------------------------------------------------
    # slicer_priority_mode:
    #   - True  => Slicer-Wert hat Vorrang (bei erkanntem M191/M141)
    #   - False => HA / Panda Setting (soll) hat Vorrang
    #
    # slicer_soll:
    #   - letzter erkannter Wert aus dem Gcode (nur Anzeige)
    #
    # last_analyzed_file:
    #   - damit wir pro Datei nur einmal analysieren
    # ========================================================
    "slicer_priority_mode": False,
    "slicer_soll": 0.0,
    "last_analyzed_file": ""
}

ha_memory = {"kammer_soll": 30.0, "bett_limit": 50.0}
global_heating_state = 20.0
last_switch_time = 0
last_ha_change = 0
panda_ws = None
main_loop = None
terminal_cleared = False

# --- LOGGING ---
logging.basicConfig(level=logging.CRITICAL)
file_logger = logging.getLogger("PandaFullLog")
file_logger.propagate = False
file_logger.setLevel(logging.INFO)
if DEBUG_TO_FILE:
    f_handler = logging.FileHandler('panda_debug.log')
    f_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    file_logger.addHandler(f_handler)

# --- LOGGING FUNKTION ---
def log_event(msg, force_console=False):
    # 1. Immer in die Datei schreiben, wenn DEBUG_TO_FILE True ist
    if DEBUG_TO_FILE:
        file_logger.info(msg)

    # 2. In die Konsole NUR wenn DEBUG True ist ODER force_console aktiv ist
    if DEBUG or force_console:
        print(f"INFO:PandaDebug:{msg}")

# ============================================================
# ✅ HELPER (NEU)
# ------------------------------------------------------------
# sichere Zahl-Konvertierung (damit MQTT/JSON nicht abfliegt)
# ============================================================
def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

# ============================================================
# ✅ SLICER PARSER (NEU)
# ------------------------------------------------------------
# Liest Print-Status & Gcode Anfang, sucht:
#  - M191 Sxx (Chamber temperature)
#  - M141 Sxx (Chamber temperature)
# und setzt current_data["slicer_soll"]
#
# Wenn slicer_priority_mode aktiv ist, übernimmt er automatisch kammer_soll
# und sendet set_temp an Panda.
# ============================================================
async def slicer_auto_parser():
    while True:
        try:
            # Moonraker Print-Status (welche Datei wird gedruckt?)
            status_url = f"http://{PRINTER_IP}/printer/objects/query?print_stats"
            r = requests.get(status_url, timeout=2).json()

            filename = ""
            try:
                filename = r["result"]["status"]["print_stats"].get("filename", "") or ""
            except Exception:
                filename = ""

            # Nur wenn neue Datei erkannt
            if filename and filename != current_data["last_analyzed_file"]:
                log_event(f"[SLICER] Neue Datei erkannt: {filename}")

                # Gcode lesen (nur Anfang reicht, da M191/M141 meist am Start stehen)
                file_url = f"http://{PRINTER_IP}/server/files/gcodes/{filename}"
                resp = requests.get(file_url, headers={'Range': 'bytes=0-50000'}, timeout=5)

                # Suche M191 Sxx oder M141 Sxx
                import re
                match = re.search(r'(?:M191|M141)\s+S(\d+)', resp.text)
                if match:
                    new_target = safe_float(match.group(1), 0.0)
                    current_data["slicer_soll"] = new_target
                    current_data["last_analyzed_file"] = filename

                    # Publish Anzeige-Sensoren
                    mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_soll", int(new_target), retain=True)
                    mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_target_temp", int(new_target), retain=True)  # ✅ WICHTIGSTE ENTITÄT
                    mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_file", filename, retain=True)

                    log_event(f"[SLICER] gefunden: {new_target}°C (priority={'ON' if current_data['slicer_priority_mode'] else 'OFF'})")

                    # Wenn Priority aktiv: sofort übernehmen
                    if current_data["slicer_priority_mode"] and new_target > 15:
                        current_data["kammer_soll"] = new_target

                        # Panda sofort setzen
                        if panda_ws:
                            asyncio.run_coroutine_threadsafe(
                                panda_ws.send(json.dumps({"settings": {"set_temp": int(new_target)}})),
                                main_loop
                            )

                        # HA MQTT State aktualisieren
                        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/soll", int(new_target), retain=True)
                else:
                    # Auch ohne Treffer Datei merken, damit nicht dauernd neu geladen wird
                    current_data["last_analyzed_file"] = filename
                    mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_file", filename, retain=True)
                    mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_soll", int(current_data["slicer_soll"]), retain=True)
                    mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_target_temp", int(current_data["slicer_soll"]), retain=True)  # ✅ WICHTIGSTE ENTITÄT

        except Exception as e:
            if DEBUG:
                print(f"DEBUG:SLICER-ERR:{e}")
        await asyncio.sleep(5)

# --- MQTT LOGIK ---
def on_mqtt_message(client, userdata, msg):
    global current_data, last_ha_change, ha_memory

    # ============================================================
    # ✅ FEHLENDE ENTITÄT 1: switch.panda_breath_mod_slicer_priority_mode
    # ------------------------------------------------------------
    # Dashboard erwartet diesen Switch -> sonst "Entity not found"
    # Topic: panda_breath_mod/slicer_priority_mode
    # Set:   panda_breath_mod/slicer_priority_mode/set
    # ============================================================
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/slicer_priority_mode/set":
        payload = msg.payload.decode().strip().lower()
        is_on = payload in ("on", "1", "true", "on\n")

        current_data["slicer_priority_mode"] = is_on
        log_event(f"[MQTT->SLICER] slicer_priority_mode -> {is_on}")

        mqtt_client.publish(
            f"{MQTT_TOPIC_PREFIX}/slicer_priority_mode",
            "ON" if is_on else "OFF",
            retain=True
        )
        return

    # ============================================================
    # ✅ FEHLENDE ENTITÄT 2: button.panda_breath_mod_heizung_stop
    # ------------------------------------------------------------
    # Funktion: Heizung sofort AUS
    # ============================================================
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/heizung_stop/set":
        log_event("[MQTT->PANDA] HEIZUNG STOP")
        current_data["kammer_soll"] = 0.0

        if panda_ws:
            asyncio.run_coroutine_threadsafe(
                panda_ws.send(json.dumps({"settings": {"set_temp": 0}})),
                main_loop
            )

        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/soll", 0, retain=True)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/status", "Heizung gestoppt", retain=True)
        return

    # --- MANUELL MODUS ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/manual/set":
        log_event("[MQTT->PANDA] work_mode -> 2 (MANUELL)")

        async def flow():
            if panda_ws:
                # laufenden Modus sauber stoppen (z.B. Auto oder Dry)
                await panda_ws.send(json.dumps({"settings": {"isrunning": 0}}))
                await asyncio.sleep(0.2)

                # Manuell-Modus setzen
                await panda_ws.send(json.dumps({"settings": {"work_mode": 2}}))

        asyncio.run_coroutine_threadsafe(flow(), main_loop)

        # ❗ KEIN panda_modus publish hier!
        # Status kommt ausschließlich aus dem WS-Loop (work_mode)

        return
        
    # --- AUTO MODUS ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/auto/set":
        log_event("[MQTT->PANDA] work_mode -> 1 (AUTO)")

        async def flow():
            if panda_ws:
                # laufenden Modus sauber stoppen (z.B. Dry)
                await panda_ws.send(json.dumps({"settings": {"isrunning": 0}}))
                await asyncio.sleep(0.2)

                # Auto-Modus setzen
                await panda_ws.send(json.dumps({"settings": {"work_mode": 1}}))

        asyncio.run_coroutine_threadsafe(flow(), main_loop)

        # ❗ KEIN panda_modus publish hier!
        # Status kommt NUR aus dem WS-Loop (work_mode)

        return


    # --- DRYING START (FIXED & STABIL) ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/drying/set":
        log_event("[MQTT->PANDA] DRYER START (NATIVE CMD)")

        async def d_flow():
            if panda_ws:
                # laufenden Modus sauber stoppen (Auto / Manuell)
                await panda_ws.send(json.dumps({"settings": {"isrunning": 0}}))
                await asyncio.sleep(0.2)

                # Dryer Parameter setzen
                t = int(current_data.get("filament_temp", 50))
                h = int(current_data.get("filament_timer", 3))
                await panda_ws.send(json.dumps({
                    "settings": {
                        "filament_temp": t,
                        "filament_timer": h,
                        "filament_drying_mode": 3  # 3 = Custom
                    },
                    "ui_action": "custom"
                }))
                await asyncio.sleep(0.5)

                # Dry-Modus starten
                await panda_ws.send(json.dumps({
                    "settings": {
                        "work_mode": 3,
                        "isrunning": 1
                    }
                }))

        asyncio.run_coroutine_threadsafe(d_flow(), main_loop)

        # ❗ KEIN panda_modus publish hier!
        # Status kommt ausschließlich aus dem WS-Loop (work_mode)

        return
        
    # --- START / STOP ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/work_on/set":
        payload = msg.payload.decode().strip().lower()
        is_on = payload in ("on", "1", "true")

        async def p_flow():
            if panda_ws:
                if not is_on:
                    await panda_ws.send(json.dumps({"settings": {"isrunning": 0}}))
                    await asyncio.sleep(0.2)
                    await panda_ws.send(json.dumps({"settings": {"work_mode": 0}}))
                    await asyncio.sleep(0.2)
                await panda_ws.send(json.dumps({"settings": {"work_on": is_on}}))

        asyncio.run_coroutine_threadsafe(p_flow(), main_loop)
        mqtt_client.publish(
            f"{MQTT_TOPIC_PREFIX}/work_on",
            "1" if is_on else "0",
            retain=True
        )
        return

    # ============================================================
    # TEMPERATUREN & NUMERISCHE SET-WERTE (FIX)
    # ------------------------------------------------------------
    # - verarbeitet NUR echte Zahlen
    # - NUR Topics mit /set
    # - verhindert Text -> float Fehler
    # ============================================================
    try:
        if not msg.topic.endswith("/set"):
            return

        val_str = msg.payload.decode().strip()

        try:
            val = float(val_str)
        except ValueError:
            if DEBUG:
                log_event(f"[MQTT] Ignoriere Textwert: '{val_str}' ({msg.topic})")
            return

        last_ha_change = time.time()

        if msg.topic.endswith("/dry_temp/set"):
            current_data["filament_temp"] = int(val)
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/dry_temp", int(val), retain=True)
            return

        if msg.topic.endswith("/dry_time/set"):
            current_data["filament_timer"] = int(val)
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/dry_time", int(val), retain=True)
            return

        key = None
        if msg.topic.endswith("/soll/set"):
            key, data_key = "set_temp", "kammer_soll"
        elif msg.topic.endswith("/limit/set"):
            key, data_key = "hotbedtemp", "bett_limit"
        elif msg.topic.endswith("/filtertemp/set"):
            key, data_key = "filtertemp", "filtertemp"
        else:
            return

        if data_key == "kammer_soll" and current_data.get("slicer_priority_mode", False):
            ha_memory["kammer_soll"] = val
            mqtt_client.publish(
                f"{MQTT_TOPIC_PREFIX}/soll",
                int(current_data.get("kammer_soll", 0)),
                retain=True
            )
            return

        current_data[data_key] = val

        if panda_ws:
            asyncio.run_coroutine_threadsafe(
                panda_ws.send(json.dumps({"settings": {key: int(val)}})),
                main_loop
            )

        mqtt_client.publish(msg.topic.replace("/set", ""), int(val), retain=True)

    except Exception as e:
        log_event(f"[TEMP-SET-ERR] {e}", force_console=True)

def setup_mqtt():
    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id=f"PandaNative_{PRINTER_SN}")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_message = on_mqtt_message
    client.connect(MQTT_BROKER, 1883, 60)

    # Original: client.subscribe(f"{MQTT_TOPIC_PREFIX}/+/set")
    # ✅ FIX: Für neue Entities (switch/button/text) sauber alles mitnehmen:
    client.subscribe(f"{MQTT_TOPIC_PREFIX}/#")

    client.loop_start()
    return client

mqtt_client = setup_mqtt()

def setup_mqtt_discovery():
    base, dev = MQTT_TOPIC_PREFIX, {"identifiers": [PRINTER_SN], "name": "Panda Breath Mod", "model": "V6.8 Final", "manufacturer": "Biqu"}

    # Alle numerischen Eingabefelder (Numbers)
    # Hier wurde "filtertemp" hinzugefügt, damit das Feld in HA erscheint
    for sfx, name in [("soll", "Kammer Soll"), ("limit", "Bett Limit"), ("filtertemp", "Filter Fan Activation"), ("dry_temp", "Drying Temp"), ("dry_time", "Drying Time")]:
        u_id = f"pb_v66_{PRINTER_SN}_{sfx}"

        # Bestimme Einheit und Icon basierend auf dem Suffix
        unit = "h" if "time" in sfx else "°C"
        icon = "mdi:fan-clock" if "filter" in sfx else "mdi:thermometer"

        mqtt_client.publish(f"homeassistant/number/{u_id}/config", json.dumps({
            "name": name,
            "state_topic": f"{base}/{sfx}",
            "command_topic": f"{base}/{sfx}/set",
            "unique_id": u_id,
            "device": dev,
            "min": 1,
            "max": 120 if ("limit" in sfx or "filter" in sfx) else 80,
            "unit_of_measurement": unit,
            "icon": icon,
            "mode": "box"
        }), retain=True)

    # Schalter für Panda Power
    mqtt_client.publish(f"homeassistant/switch/pb_v66_on/config", json.dumps({
        "name": "Panda Power",
        "state_topic": f"{base}/work_on",
        "command_topic": f"{base}/work_on/set",
        "unique_id": f"pb_v66_on",
        "device": dev,
        "payload_on": "1",
        "payload_off": "0",
        "icon": "mdi:power"
    }), retain=True)

    # Panda Power (AN/AUS)
    mqtt_client.publish(
        f"homeassistant/switch/{base}_panda_power/config",
        json.dumps({
            "name": "Panda Power",
            "object_id": f"{base}_panda_power",
            "state_topic": f"{base}/work_on",
            "command_topic": f"{base}/work_on/set",
            "payload_on": "1",
            "payload_off": "0",
            "unique_id": f"{PRINTER_SN}_panda_power",
            "device": dev,
            "icon": "mdi:power"
        }),
        retain=True
    )
 
     # Panda Modus (Auto / Manuell / Dry)
    mqtt_client.publish(
        f"homeassistant/sensor/{base}_panda_modus/config",
        json.dumps({
            "name": "Panda Modus",
            "object_id": f"{base}_panda_modus",
            "state_topic": f"{base}/panda_modus",
            "unique_id": f"{PRINTER_SN}_panda_modus",
            "device": dev,
            "icon": "mdi:state-machine"
        }),
        retain=True
    )
       
    # Kammer Ist Temperatur (FEHLTE)
    mqtt_client.publish(f"homeassistant/sensor/{base}_kammer_ist/config", json.dumps({
        "name": "Kammer Ist",
        "object_id": f"{base}_kammer_ist",
        "state_topic": f"{base}/ist",
        "unique_id": f"{PRINTER_SN}_kammer_ist",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "device": dev
    }), retain=True)
    
    # Modus Buttons
    for b in ["manual", "auto", "drying"]:
        mqtt_client.publish(f"homeassistant/button/pb_v66_{b}/config", json.dumps({
            "name": f"Panda {b.capitalize()}",
            "command_topic": f"{base}/{b}/set",
            "unique_id": f"pb_v66_{b}",
            "device": dev
        }), retain=True)

    # IST-Temperatur Sensor
    mqtt_client.publish(f"homeassistant/sensor/pb_v66_ist/config", json.dumps({
        "name": "Kammer Ist",
        "state_topic": f"{base}/ist",
        "unique_id": f"pb_v66_ist",
        "device": dev,
        "unit_of_measurement": "°C",
        "device_class": "temperature"
    }), retain=True)

    # Heiz-Status Sensor (Klartext-Anzeige)
    u_id_status = f"pb_v66_{PRINTER_SN}_status"
    mqtt_client.publish(f"homeassistant/sensor/{u_id_status}/config", json.dumps({
        "name": "Panda Heiz Status",
        "state_topic": f"{base}/status",
        "unique_id": u_id_status,
        "device": dev,
        "icon": "mdi:fire-circle"
    }), retain=True)

    # Lüfter Status Sensor (Binary Sensor)
    u_id_fan = f"pb_v66_{PRINTER_SN}_fan"
    mqtt_client.publish(f"homeassistant/binary_sensor/{u_id_fan}/config", json.dumps({
        "name": "Panda Filter Lüfter",
        "state_topic": f"{base}/fan",
        "unique_id": u_id_fan,
        "device": dev,
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": "fan"
    }), retain=True)

    # ============================================================
    # ✅ FEHLENDE ENTITÄTEN AUS DEINEN BILDERN (NEU)
    # ------------------------------------------------------------
    # 1) switch.panda_breath_mod_slicer_priority_mode
    # 2) button.panda_breath_mod_heizung_stop
    # 3) sensor.panda_breath_mod_slicer_soll (Anzeige)
    # 4) sensor.panda_breath_mod_slicer_file (Anzeige)
    # 5) sensor.panda_breath_mod_slicer_target_temp (WICHTIGSTE ENTITÄT)
    #
    # WICHTIG:
    # - Wir setzen object_id explizit, damit entity_id exakt passt.
    # - So verschwinden die "Unknown entity selected" / "Entity not found" Kacheln.
    # ============================================================

    # 1) Slicer Priority Switch
    mqtt_client.publish(f"homeassistant/switch/{base}_slicer_priority_mode/config", json.dumps({
        "name": "Slicer Priority Mode",
        "object_id": f"{base}_slicer_priority_mode",          # -> switch.panda_breath_mod_slicer_priority_mode
        "state_topic": f"{base}/slicer_priority_mode",
        "command_topic": f"{base}/slicer_priority_mode/set",
        "unique_id": f"{PRINTER_SN}_slicer_priority_mode_sw",
        "device": dev,
        "payload_on": "ON",
        "payload_off": "OFF",
        "icon": "mdi:priority-high"
    }), retain=True)

    # 2) Heizung Stop Button
    mqtt_client.publish(f"homeassistant/button/{base}_heizung_stop/config", json.dumps({
        "name": "Heizung Stop",
        "object_id": f"{base}_heizung_stop",                  # -> button.panda_breath_mod_heizung_stop
        "command_topic": f"{base}/heizung_stop/set",
        "unique_id": f"{PRINTER_SN}_heizung_stop_btn",
        "device": dev,
        "icon": "mdi:radiator-off"
    }), retain=True)

    # 3) Slicer Soll Sensor
    mqtt_client.publish(f"homeassistant/sensor/{base}_slicer_soll/config", json.dumps({
        "name": "Slicer Soll",
        "object_id": f"{base}_slicer_soll",                   # -> sensor.panda_breath_mod_slicer_soll
        "state_topic": f"{base}/slicer_soll",
        "unique_id": f"{PRINTER_SN}_slicer_soll_sns",
        "device": dev,
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "icon": "mdi:thermometer-lines"
    }), retain=True)

    # 4) Slicer File Sensor
    mqtt_client.publish(f"homeassistant/sensor/{base}_slicer_file/config", json.dumps({
        "name": "Slicer Datei",
        "object_id": f"{base}_slicer_file",                   # -> sensor.panda_breath_mod_slicer_file
        "state_topic": f"{base}/slicer_file",
        "unique_id": f"{PRINTER_SN}_slicer_file_sns",
        "device": dev,
        "icon": "mdi:file"
    }), retain=True)

    # 5) ✅ WICHTIGSTE ENTITÄT: Slicer Target Temp Sensor
    mqtt_client.publish(f"homeassistant/sensor/{base}_slicer_target_temp/config", json.dumps({
        "name": "Slicer Target Temp",
        "object_id": f"{base}_slicer_target_temp",            # -> sensor.panda_breath_mod_slicer_target_temp
        "state_topic": f"{base}/slicer_target_temp",
        "unique_id": f"{PRINTER_SN}_slicer_target_temp_sns",
        "device": dev,
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "icon": "mdi:thermometer-chevron-up"
    }), retain=True)

# --- WS LOOP ---
async def update_limits_from_ws():
    global current_data, panda_ws
    uri = f"ws://{PANDA_IP}/ws"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as websocket:
                panda_ws = websocket
                # Erst identifizieren, dann Settings anfordern
                await websocket.send(json.dumps({"printer": {"ip": HOST_IP, "sn": PRINTER_SN, "access_code": ACCESS_CODE}}))
                await websocket.send(json.dumps({"get_settings": 1}))

                while True:
                    msg = await websocket.recv()
                    data = json.loads(msg)
                    if 'settings' in data:
                        s = data['settings']

                        # IST-Temperatur immer sofort verarbeiten
                        if 'warehouse_temper' in s:
                            current_data["kammer_ist"] = float(s['warehouse_temper'])
                            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/ist", s['warehouse_temper'])

                        # WICHTIG: Alle Werte in current_data schreiben!
                        # Behebt "Kammer: 0.0" und synchronisiert filtertemp intern
                        if 'set_temp' in s:
                            # Wenn slicer_priority_mode aktiv ist, lassen wir Hardwarewerte zu,
                            # aber HA soll weiterhin den "aktuellen Soll" sehen.
                            current_data["kammer_soll"] = float(s['set_temp'])

                        if 'hotbedtemp' in s:
                            current_data["bett_limit"] = float(s['hotbedtemp'])

                        # NEU: Filter-Schwelle für die Lüfter-Logik synchronisieren
                        if 'filtertemp' in s:
                            current_data["filtertemp"] = float(s['filtertemp'])

                        if 'filament_temp' in s:
                            current_data["filament_temp"] = int(s['filament_temp'])

                        if 'filament_timer' in s:
                            current_data["filament_timer"] = int(s['filament_timer'])

                        # Nur wenn HA nicht gerade selbst was sendet (last_ha_change Schutz),
                        # synchronisieren wir die Werte zurück an MQTT
                        if (time.time() - last_ha_change) > 8.0:
                            # Kammer-Soll
                            if 'set_temp' in s:
                                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/soll", int(s['set_temp']), retain=True)

                            # Filter-Schwelle an Home Assistant senden
                            if 'filtertemp' in s:
                                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/filtertemp", int(s['filtertemp']), retain=True)

                            # Bett-Limit (Sicherheit)
                            if 'hotbedtemp' in s:
                                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/limit", int(s['hotbedtemp']), retain=True)

                            # Power Status
                            if 'work_on' in s:
                                p_val = "1" if s['work_on'] in (True, 1, "1") else "0"
                                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/work_on", p_val, retain=True)

                            # Dryer Werte (Trockner)
                            if 'filament_temp' in s:
                                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/dry_temp", int(s['filament_temp']), retain=True)
                            if 'filament_timer' in s:
                                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/dry_time", int(s['filament_timer']), retain=True)

                            # ✅ Slicer Priority Switch State immer mit pushen (damit HA nicht "unknown" zeigt)
                            mqtt_client.publish(
                                f"{MQTT_TOPIC_PREFIX}/slicer_priority_mode",
                                "ON" if current_data.get("slicer_priority_mode", False) else "OFF",
                                retain=True
                            )

                            # ✅ Slicer Anzeige Sensoren regelmäßig mit pushen
                            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_soll", int(current_data.get("slicer_soll", 0)), retain=True)
                            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_target_temp", int(current_data.get("slicer_soll", 0)), retain=True)  # ✅ WICHTIGSTE ENTITÄT
                            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_file", current_data.get("last_analyzed_file", ""), retain=True)

                            # Panda Modus Status + Slicer-Logik (ZENTRALE WAHRHEIT)
                            modus = "Standby"

                            if s.get("work_mode") == 1:
                                 modus = "Automatik"

                            elif s.get("work_mode") == 2:
                                modus = "Manuell"

                            elif s.get("work_mode") == 3:
                                modus = "Dry"

                            mqtt_client.publish(
                                f"{MQTT_TOPIC_PREFIX}/panda_modus",
                                modus,
                                retain=True
                            )

                        # Debug-Log für dich im Terminal
                        if DEBUG:
                            print(f"DEBUG: WS-Sync -> Soll: {current_data['kammer_soll']} | Ist: {current_data['kammer_ist']} | Filter: {current_data.get('filtertemp')}")

        except Exception as e:
            if DEBUG: print(f"DEBUG: WS-Error: {e}")
            panda_ws = None
            await asyncio.sleep(5)

# --- EMULATION ---
# --- EMULATION ---
async def handle_panda(reader, writer):
    global last_switch_time, global_heating_state, terminal_cleared
    setup_mqtt_discovery()
    try:
        # Initialer Handshake
        await reader.read(1024); writer.write(b'\x20\x02\x00\x00'); await writer.drain()
        sub_data = await reader.read(1024)
        if sub_data and sub_data[0] == 0x82:
            writer.write(b'\x90\x03' + sub_data[2:4] + b'\x00'); await writer.drain()

        while not writer.is_closing():
            try:
                # 1. Daten von Home Assistant holen (Betttemperatur)
                h_resp = requests.get(HA_URL, headers={"Authorization": f"Bearer {HA_TOKEN}"}, timeout=2)
                bed_ist = float(h_resp.json()['state'])

                # 2. Variablen laden
                target, ist, limit = current_data["kammer_soll"], current_data["kammer_ist"], current_data["bett_limit"]
                f_threshold = current_data.get("filtertemp", 30.0)  # Schwelle für Lüfter

                # 3. Heiz-Logik & Hysterese
                if target > 15:
                    target_state = global_heating_state
                    if bed_ist < limit:
                        target_state, info = 20.0, "Bett-Stop"
                    elif ist >= target:
                        target_state, info = 20.0, "Ziel erreicht"
                    elif ist <= (target - HYSTERESE):
                        target_state, info = 85.0, "Heizen..."
                    else:
                        info = "Hysterese"

                    # Schaltschutz (MIN_SWITCH_TIME)
                    if target_state != global_heating_state and (time.time() - last_switch_time) > MIN_SWITCH_TIME:
                        global_heating_state, last_switch_time = target_state, time.time()
                else:
                    info = "Standby"
                    global_heating_state = 20.0

                # 4. NEU: Lüfter-Logik (Filter Fan)
                # Lüfter ist AN, wenn das Bett wärmer ist als die eingestellte filtertemp
                fan_state = "ON" if bed_ist >= f_threshold else "OFF"

                # 5. Anzeige & MQTT Update
                # ✅ Zusatz: Slicer Info in der Terminalzeile
                sl = int(current_data.get("slicer_soll", 0))
                sl_prio = "SL-PRIO" if current_data.get("slicer_priority_mode", False) else "NORMAL"
                line = f"\r🟢 ONLINE | Bed:{bed_ist}° | Kammer:{target}/{ist}° | Heiz:{'AN' if global_heating_state > 50 else 'AUS'} | Fan:{fan_state} | {info} | {sl_prio}:{sl}°"
                if not terminal_cleared: os.system('clear'); terminal_cleared = True
                print(f"{line}\033[K", end="", flush=True)

                # Status-Entitäten an HA senden
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/status", info, retain=True)
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/panda_heiz_status", info, retain=True)  # ✅ FIX: Heiz-Status Entity füttern
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/fan", fan_state, retain=True)

                # ✅ Slicer Entities regelmäßig aktuell halten
                mqtt_client.publish(
                    f"{MQTT_TOPIC_PREFIX}/slicer_priority_mode",
                    "ON" if current_data.get("slicer_priority_mode", False) else "OFF",
                    retain=True
                )
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_soll", int(current_data.get("slicer_soll", 0)), retain=True)
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_target_temp", int(current_data.get("slicer_soll", 0)), retain=True)  # ✅ WICHTIGSTE ENTITÄT
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_file", current_data.get("last_analyzed_file", ""), retain=True)

                # 6. Report-Paket für den Panda bauen
                data = {
                    "print": {
                        "command": "push_status",
                        "msg": 1,
                        "sequence_id": str(int(time.time())),
                        "warehouse_temper": float(ist),
                        "bed_temper": float(bed_ist),
                        "chamber_temper": float(ist),
                        "bed_target_temper": 100.0 if global_heating_state > 50 else 0.0,
                        "gcode_state": "RUNNING" if global_heating_state > 50 else "IDLE",
                        "mc_percent": 50
                    }
                }

                payload = json.dumps(data).encode()
                topic = f"device/{PRINTER_SN}/report".encode()
                vh = len(topic).to_bytes(2, 'big') + topic
                rem = len(vh) + len(payload)

                # MQTT Variable Length Encoding
                pkt = b'\x30'
                X = rem
                while X > 0:
                    eb = X % 128
                    X //= 128
                    if X > 0: eb |= 128
                    pkt += eb.to_bytes(1, 'big')

                writer.write(pkt + vh + payload)
                await writer.drain()

            except Exception as e:
                log_event(f"[EMU-LOOP-ERR] {e}", force_console=True)
                break

            await asyncio.sleep(2)

    finally:
        writer.close()

async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()

    # ✅ Original WS Sync Task
    asyncio.create_task(update_limits_from_ws())

    # ✅ NEU: Slicer Parser Task
    asyncio.create_task(slicer_auto_parser())

    ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_ctx.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
    ssl_ctx.set_ciphers('DEFAULT@SECLEVEL=1')
    server = await asyncio.start_server(handle_panda, '0.0.0.0', 8883, ssl=ssl_ctx)
    print(f"\n🚀 Panda-Logic-Sync V1.5")
    print(f"👉 BITTE 'BIND' DRÜCKEN FÜR START...\n")

    log_event("🚀 V1.5 gestartet.", force_console=True)

    async with server: await server.serve_forever()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n🛑 Stopp.")
