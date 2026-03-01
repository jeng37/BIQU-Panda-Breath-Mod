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
PANDA_VERSION = "v1.8"
last_reported_mode = None
mode_change_hint = ""
heating_locked = False
global_lock = False  # NEU: Sicherheits-Sperre für alle Modi
global_heating_state = 20.0
last_switch_time = 0
bed_sensor_error = False
bind_confirmed = False
bind_warning_shown = False
# --- POWER CONFIRM (gegen ON->OFF "Bounce") ---
desired_power_state = None           # None / True / False
power_pending_until = 0.0
POWER_CONFIRM_TIMEOUT = 6.0          # Sekunden warten, bis WS "work_on" nachzieht
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
MQTT_BROKER = "192.168.x.xxx"
# MQTT Benutzername: In HA unter Einstellungen -> Personen -> Benutzer angelegt.
MQTT_USER = "xxxxxx"
# MQTT Passwort: Das zugehörige Passwort für den MQTT-Benutzer.
MQTT_PASS = "xxxxxx"

# MQTT Präfix: Die Basis für alle Topics (z.B. panda_breath_mod/soll).
# ⚠️ WICHTIG: Deine Screenshots zeigen entity_ids wie:
# - button.panda_breath_mod_heizung_stop
# - switch.panda_breath_mod_slicer_priority_mode
# - sensor.panda_breath_mod_slicer_target_temp
# Darum MUSS der Prefix "panda_breath_mod" sein, sonst passt HA/YAML nicht.
MQTT_TOPIC_PREFIX = "panda_breath_mod"

# Host IP: Die statische IP-Adresse des Rechners, auf dem dieses Skript läuft.
HOST_IP = "192.168.x.xxx"
# Panda IP: Die IP-Adresse deines Panda Touch Displays im WLAN.
PANDA_IP = "192.168.x.xxx"
# Seriennummer: Die SN deines Druckers (findest du in der Panda-UI oder auf dem Sticker).
PRINTER_SN = "01P00A123456789"
# Access Code: Der Sicherheitscode deines Druckers für die WebSocket-Verbindung.
ACCESS_CODE = "01P00A12"
# HA API URL: Link zum Bett-Temperatur-Sensor deines Druckers in Home Assistant.
HA_URL = "http://192.168.x.xxx:8123/api/states/sensor.ks1c_bed_temperature"
# HA Token: Ein 'Long-Lived Access Token' (erstellt im HA-Profil ganz unten).
HA_TOKEN = "eyJhbGciOiJIUzI1NiI..........................................."

# ============================================================
# ✅ SLICER MODE (NEU)
# ------------------------------------------------------------
# PRINTER_IP = IP vom Drucker / Moonraker (für Gcode-File Analyse)
# Funktion: liest beim Druckstart die ersten Bytes der Gcode Datei,
# sucht M191 Sxx / M141 Sxx und setzt slicer_soll.
# ============================================================
PRINTER_IP = "192.168.x.xxx"
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
    #    - True  => Slicer-Wert hat Vorrang (bei erkanntem M191/M141)
    #    - False => HA / Panda Setting (soll) hat Vorrang
    #
    # slicer_soll:
    #    - letzter erkannter Wert aus dem Gcode (nur Anzeige)
    #
    # last_analyzed_file:
    #    - damit wir pro Datei nur einmal analysieren
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
# Merkt sich den letzten vollständigen WS-Settings-Stand
last_reported_mode = None
mode_change_hint = ""
last_ws_settings = {}
power_forced_off = False # Ergänzt für Logik-Vollständigkeit

# ============================================================
# --- LOGGING SETUP (DEBUG / CRITICAL Umschaltbar) ---
# ============================================================

LOG_LEVEL = logging.DEBUG if DEBUG else logging.CRITICAL

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(levelname)s:%(name)s:%(message)s"
)

# 🔇 Externe Libraries ruhigstellen (nur wenn DEBUG=False relevant)
#logging.getLogger("urllib3").setLevel(logging.CRITICAL)
#logging.getLogger("websockets").setLevel(logging.CRITICAL)

file_logger = logging.getLogger("PandaFullLog")
file_logger.propagate = False
file_logger.setLevel(logging.INFO)

if DEBUG_TO_FILE:
    f_handler = logging.FileHandler("panda_debug.log")
    f_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(message)s")
    )
    file_logger.addHandler(f_handler)
    
# --- LOGGING FUNKTION ---
def log_event(msg, force_console=False):

    # 1️⃣ Datei Logging
    if DEBUG_TO_FILE:
        file_logger.info(msg)

    # 2️⃣ Konsole nur bei DEBUG oder Force
    if DEBUG or force_console:
        print(f" INFO:PandaDebug:{msg}")
            
# --- HELPER ---
def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

# ✅ SLICER PARSER (OPTIMIERT: Nutzt run_in_executor gegen Blockaden)
async def slicer_auto_parser():
    loop = asyncio.get_event_loop()
    while True:
        try:
            # OPTIMIERUNG: requests in Thread auslagern, damit das Hauptskript (Heartbeat) nicht stoppt
            def fetch_moonraker():
                return requests.get(f"http://{PRINTER_IP}/printer/objects/query?print_stats", timeout=2).json()
            
            r = await loop.run_in_executor(None, fetch_moonraker)
            filename = r.get("result", {}).get("status", {}).get("print_stats", {}).get("filename", "")

            if filename and filename != current_data["last_analyzed_file"]:
                log_event(f"[SLICER] Neue Datei erkannt: {filename}")
                
                def fetch_gcode():
                    return requests.get(f"http://{PRINTER_IP}/server/files/gcodes/{filename}", 
                                        headers={'Range': 'bytes=0-50000'}, timeout=5)
                
                resp = await loop.run_in_executor(None, fetch_gcode)

                if resp.status_code in [200, 206]:
                    import re
                    match = re.search(r'(?:M191|M141)\s+S(\d+)', resp.text)
                    if match:
                        new_target = safe_float(match.group(1), 0.0)
                        current_data["slicer_soll"] = new_target
                        current_data["last_analyzed_file"] = filename

                        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_soll", int(new_target), retain=True)
                        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_target_temp", int(new_target), retain=True)
                        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_file", filename, retain=True)

                        if current_data["slicer_priority_mode"] and new_target > 15:
                            current_data["kammer_soll"] = new_target
                            if panda_ws:
                                asyncio.run_coroutine_threadsafe(
                                    panda_ws.send(json.dumps({"settings": {"set_temp": int(new_target)}})),
                                    main_loop
                                )
                            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/soll", int(new_target), retain=True)
                    else:
                        current_data["last_analyzed_file"] = filename
                        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_file", filename, retain=True)

        except Exception as e:
            if DEBUG: log_event(f"DEBUG:SLICER-ERR:{e}")
        await asyncio.sleep(5)

# --- MQTT LOGIK ---
def on_mqtt_message(client, userdata, msg):
    # ✅ FIX: Alle globalen Deklarationen MÜSSEN am Anfang der Funktion stehen
    global current_data, last_ha_change, ha_memory
    global heating_locked, power_forced_off, global_lock 

    # ============================================================
    # ✅ UNLOCK LOGIK (Muss VOR dem Lock-Check kommen!)
    # ------------------------------------------------------------
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/unlock/set":
        log_event(">>> SYSTEM UNLOCKED <<<", force_console=True)
        global_lock = False
        heating_locked = False
        power_forced_off = False

        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/lock_status", "UNLOCKED", retain=True)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/status", "Bereit", retain=True)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/panda_modus", "Standby", retain=True)
        return

# 🛑 GLOBAL LOCK CHECK: Wenn gesperrt (Emergency Stop), wird alles andere ignoriert
    if global_lock:
        # Erlaube NUR das Unlock-Topic, alles andere wird blockiert
        if msg.topic.endswith("/set") and msg.topic != f"{MQTT_TOPIC_PREFIX}/unlock/set":
            log_event(f"[BLOCKED] System ist LOCKED! Befehl ignoriert: {msg.topic}", force_console=True)
            return

    # ✅ FEHLENDE ENTITÄT 1: switch.panda_breath_mod_slicer_priority_mode
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/slicer_priority_mode/set":
        payload = msg.payload.decode().strip().lower()
        is_on = payload in ("on", "1", "true")
        current_data["slicer_priority_mode"] = is_on
        log_event(">>> SLICER MODE ENTERED <<<", force_console=True)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_priority_mode", "ON" if is_on else "OFF", retain=True)
        return

    # ============================================================
    # ✅ HEIZUNG STOP (NOT-AUS MIT LOCK) - VERBESSERT
    # ------------------------------------------------------------
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/heizung_stop/set":
        log_event(">>> !!! EMERGENCY STOP & LOCK !!! <<<", force_console=True)
        
        global_lock = True    
        heating_locked = True 
        global_heating_state = 20.0  # 🔥 FIX: Heizung SOFORT logisch ausschalten

        async def stop_flow():
            if panda_ws:
                # Wir schalten ALLES am Panda sofort aus
                await panda_ws.send(json.dumps({"settings": {"isrunning": 0, "work_mode": 0, "work_on": 0}}))
        
        asyncio.run_coroutine_threadsafe(stop_flow(), main_loop)

        # Status an HA melden
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/lock_status", "LOCKED", retain=True)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/panda_modus", "LOCKED", retain=True)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/status", "Emergency Lock", retain=True)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/work_on", "0", retain=True) 
        return

    # --- MANUELL MODUS ---
    if msg.topic.endswith("/manual/set"):
        log_event(">>> MANUELL MODE ENTERED <<<", force_console=True)
        heating_locked = False
        power_forced_off = False
        current_data["kammer_soll"] = 45.0
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/panda_modus", "Manuell", retain=True)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_priority_mode", "OFF", retain=True)
        async def flow():
            if panda_ws:
                await panda_ws.send(json.dumps({"settings": {"isrunning": 0}}))
                await asyncio.sleep(0.2)
                await panda_ws.send(json.dumps({"settings": {"work_mode": 2}}))
        asyncio.run_coroutine_threadsafe(flow(), main_loop)
        return

    # --- AUTO MODUS ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/auto/set":
        log_event(">>> AUTO MODE ENTERED <<<", force_console=True)
        heating_locked = False
        power_forced_off = False
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/panda_modus", "Automatik", retain=True)
        current_data["slicer_priority_mode"] = False
        async def flow():
            if panda_ws:
                await panda_ws.send(json.dumps({"settings": {"isrunning": 0}}))
                await asyncio.sleep(0.1)
                await panda_ws.send(json.dumps({"settings": {"work_mode": 1}, "ui_action": "auto"}))
                await asyncio.sleep(0.1)
                await panda_ws.send(json.dumps({"settings": {"isrunning": 1}}))
        asyncio.run_coroutine_threadsafe(flow(), main_loop)
        return
        
    # --- DRY MODUS ---
    if msg.topic.endswith("/drying/set"):
        log_event(">>> DRYER MODE ENTERED <<<", force_console=True)

        heating_locked = False
        power_forced_off = False

        mqtt_client.publish(
            f"{MQTT_TOPIC_PREFIX}/panda_modus",
            "Dry",
            retain=True
        )

        async def flow():
            if panda_ws:
                await panda_ws.send(json.dumps({
                    "settings": {
                        "work_mode": 3
                    }
                }))
                await asyncio.sleep(0.2)

                await panda_ws.send(json.dumps({
                    "settings": {
                        "isrunning": 1
                    }
                }))

        asyncio.run_coroutine_threadsafe(flow(), main_loop)
        return
        
    # --- START / STOP ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/work_on/set":
        payload = msg.payload.decode().strip().lower()
        is_on = payload in ("on", "1", "true")
        async def p_flow():
            if panda_ws:
                if not is_on:
                    await panda_ws.send(json.dumps({"settings": {"isrunning": 0, "work_mode": 0}}))
                else:
                    await panda_ws.send(json.dumps({"settings": {"work_on": 1, "isrunning": 1}}))
        asyncio.run_coroutine_threadsafe(p_flow(), main_loop)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/work_on", "1" if is_on else "0", retain=True)
        return
        
    # PANDA POWER SWITCH
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/panda_power/set":
        global desired_power_state, power_pending_until

        payload = msg.payload.decode().strip().upper()
        is_on = payload == "ON"

        # Optimistic / Pending setzen (damit WS-Status nicht sofort zurückflippt)
        desired_power_state = is_on
        power_pending_until = time.time() + POWER_CONFIRM_TIMEOUT

        mqtt_client.publish(
            f"{MQTT_TOPIC_PREFIX}/panda_power",
            "ON" if is_on else "OFF",
            retain=True
        )

        if not is_on:
            log_event(">>> PANDA POWER OFF <<<", force_console=True)
            heating_locked = True
            power_forced_off = True

            async def hard_power_off():
                try:
                    if panda_ws:
                        # Reihenfolge wie von dir bewiesen:
                        await panda_ws.send(json.dumps({"settings": {"isrunning": 0}}))
                        await asyncio.sleep(0.2)

                        await panda_ws.send(json.dumps({"settings": {"work_mode": 0}}))
                        await asyncio.sleep(0.2)

                        # WICHTIG: bool false (nicht 0)
                        await panda_ws.send(json.dumps({"settings": {"work_on": False}}))
                        await asyncio.sleep(0.2)

                except Exception as e:
                    log_event(f"[POWER-OFF-ERR] {e}")

            asyncio.run_coroutine_threadsafe(hard_power_off(), main_loop)

            mqtt_client.publish(
                f"{MQTT_TOPIC_PREFIX}/panda_modus",
                "Standby",
                retain=True
            )

            return

        else:
            log_event(">>> PANDA POWER ON <<<", force_console=True)
            heating_locked = False
            power_forced_off = False

            async def power_on():
                try:
                    if panda_ws:
                        # ON als bool True
                        await panda_ws.send(json.dumps({"settings": {"work_on": True}}))
                        await asyncio.sleep(0.2)
                except Exception as e:
                    log_event(f"[POWER-ON-ERR] {e}")

            asyncio.run_coroutine_threadsafe(power_on(), main_loop)
            return
        
    # TEMPERATUREN & NUMERISCHE SET-WERTE
    try:
        if not msg.topic.endswith("/set"): return
        val_str = msg.payload.decode().strip()
        try:
            val = float(val_str)
        except ValueError: return
        last_ha_change = time.time()
        if msg.topic.endswith("/dry_temp/set"):
            current_data["filament_temp"] = int(val)
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/dry_temp", int(val), retain=True)
            return
        if msg.topic.endswith("/dry_time/set"):
            current_data["filament_timer"] = int(val)
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/dry_time", int(val), retain=True)
            return
        if msg.topic.endswith("/soll/set"):
            key, data_key = "set_temp", "kammer_soll"
        elif msg.topic.endswith("/limit/set"):
            key, data_key = "hotbedtemp", "bett_limit"
        elif msg.topic.endswith("/filtertemp/set"):
            key, data_key = "filtertemp", "filtertemp"
        else: return
        if data_key == "kammer_soll" and current_data.get("slicer_priority_mode", False):
            ha_memory["kammer_soll"] = val
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/soll", int(current_data.get("kammer_soll", 0)), retain=True)
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
    client.subscribe(f"{MQTT_TOPIC_PREFIX}/#")
    client.loop_start()
    return client

mqtt_client = setup_mqtt()

def setup_mqtt_discovery():
    base, dev = MQTT_TOPIC_PREFIX, {"identifiers": [PRINTER_SN], "name": "Panda Breath Mod", "model": "V6.8 Final", "manufacturer": "Biqu"}
    for sfx, name in [("soll", "Kammer Soll"), ("limit", "Bett Limit"), ("filtertemp", "Filter Fan Activation"), ("dry_temp", "Drying Temp"), ("dry_time", "Drying Time")]:
        u_id = f"pb_v66_{PRINTER_SN}_{sfx}"
        unit = "h" if "time" in sfx else "°C"
        icon = "mdi:fan-clock" if "filter" in sfx else "mdi:thermometer"
        mqtt_client.publish(f"homeassistant/number/{u_id}/config", json.dumps({
            "name": name, "state_topic": f"{base}/{sfx}", "command_topic": f"{base}/{sfx}/set",
            "unique_id": u_id, "device": dev, "min": 1, "max": 120 if ("limit" in sfx or "filter" in sfx) else 80,
            "unit_of_measurement": unit, "icon": icon, "mode": "box"
        }), retain=True)

    mqtt_client.publish(f"homeassistant/sensor/{base}_panda_modus/config", json.dumps({
        "name": "Panda Modus", "state_topic": f"{base}/panda_modus", "unique_id": f"{PRINTER_SN}_panda_modus", "device": dev, "icon": "mdi:state-machine"
    }), retain=True)
       
    mqtt_client.publish(f"homeassistant/sensor/{base}_kammer_ist/config", json.dumps({
        "name": "Kammer Ist", "state_topic": f"{base}/ist", "unique_id": f"{PRINTER_SN}_kammer_ist", "unit_of_measurement": "°C", "device_class": "temperature", "device": dev
    }), retain=True)
    
    for b in ["manual", "auto", "drying"]:
        mqtt_client.publish(f"homeassistant/button/pb_v66_{b}/config", json.dumps({
            "name": f"Panda {b.capitalize()}", "command_topic": f"{base}/{b}/set", "unique_id": f"pb_v66_{b}", "device": dev
        }), retain=True)

    mqtt_client.publish(f"homeassistant/sensor/{base}_status/config", json.dumps({
        "name": "Panda Heiz Status", "state_topic": f"{base}/status", "unique_id": f"pb_v66_{PRINTER_SN}_status", "device": dev, "icon": "mdi:fire-circle"
    }), retain=True)

    mqtt_client.publish(f"homeassistant/binary_sensor/{base}_fan/config", json.dumps({
        "name": "Panda Filter Lüfter", "state_topic": f"{base}/fan", "unique_id": f"pb_v66_{PRINTER_SN}_fan", "device": dev, "payload_on": "ON", "payload_off": "OFF", "device_class": "fan"
    }), retain=True)

    mqtt_client.publish(f"homeassistant/switch/{base}_panda_power/config", json.dumps({
        "name": "Panda Power", "state_topic": f"{base}/panda_power", "command_topic": f"{base}/panda_power/set", "unique_id": f"{PRINTER_SN}_panda_power_sw", "device": dev, "payload_on": "ON", "payload_off": "OFF", "icon": "mdi:power"
    }), retain=True)

    mqtt_client.publish(f"homeassistant/switch/{base}_slicer_priority_mode/config", json.dumps({
        "name": "Slicer Priority Mode", "state_topic": f"{base}/slicer_priority_mode", "command_topic": f"{base}/slicer_priority_mode/set", "unique_id": f"{PRINTER_SN}_slicer_priority_mode_sw", "device": dev, "payload_on": "ON", "payload_off": "OFF", "icon": "mdi:priority-high"
    }), retain=True)

    mqtt_client.publish(f"homeassistant/button/{base}_heizung_stop/config", json.dumps({
        "name": "Heizung Stop", "command_topic": f"{base}/heizung_stop/set", "unique_id": f"{PRINTER_SN}_heizung_stop_btn", "device": dev, "icon": "mdi:radiator-off"
    }), retain=True)

    mqtt_client.publish(f"homeassistant/sensor/{base}_slicer_soll/config", json.dumps({
        "name": "Slicer Soll", "state_topic": f"{base}/slicer_soll", "unique_id": f"{PRINTER_SN}_slicer_soll_sns", "device": dev, "unit_of_measurement": "°C", "device_class": "temperature"
    }), retain=True)

    mqtt_client.publish(f"homeassistant/sensor/{base}_slicer_target_temp/config", json.dumps({
        "name": "Slicer Target Temp", "state_topic": f"{base}/slicer_target_temp", "unique_id": f"{PRINTER_SN}_slicer_target_temp_sns", "device": dev, "unit_of_measurement": "°C", "device_class": "temperature"
    }), retain=True)

    mqtt_client.publish(f"homeassistant/sensor/{base}_version/config", json.dumps({
        "name": "Panda Version", "state_topic": f"{base}/version", "unique_id": f"{PRINTER_SN}_panda_version", "device": dev, "icon": "mdi:information-outline"
    }), retain=True)

# ✅ NEUE ENTITÄTEN FÜR LOCK-SYSTEM
    mqtt_client.publish(f"homeassistant/sensor/{base}_lock_status/config", json.dumps({
        "name": "Panda Lock Status",
        "state_topic": f"{base}/lock_status",
        "unique_id": f"{PRINTER_SN}_lock_status",
        "device": dev,
        "icon": "mdi:lock"
    }), retain=True)

    mqtt_client.publish(f"homeassistant/button/{base}_unlock/config", json.dumps({
        "name": "Panda Unlock",
        "command_topic": f"{base}/unlock/set",
        "unique_id": f"{PRINTER_SN}_unlock_btn",
        "device": dev,
        "icon": "mdi:lock-open-variant"
    }), retain=True)
    

# --- WS LOOP (OPTIMIERT: Hält Verbindung bei WiFi-Paketen offen) ---
async def update_limits_from_ws():
    global panda_ws, bind_confirmed, bind_warning_shown
    uri = f"ws://{PANDA_IP}/ws"

    while True:

        # 🔒 LOCK HANDLING
        if global_lock:

            try:
                # Neue frische Verbindung erzwingen
                async with websockets.connect(f"ws://{PANDA_IP}/ws") as ws:

                    # 1️⃣ BIND (WICHTIG – sonst ignoriert Panda Befehle)
                    await ws.send(json.dumps({
                        "printer": {
                            "ip": HOST_IP,
                            "sn": PRINTER_SN,
                            "access_code": ACCESS_CODE
                        }
                    }))

                    await asyncio.sleep(0.3)

                    # 2️⃣ HARD POWER OFF (MASTER SWITCH!)
                    await ws.send(json.dumps({
                        "settings": {
                            "work_on": 0,
                            "work_mode": 0,
                            "set_temp": 0
                        }
                    }))

                    await asyncio.sleep(0.5)

            except Exception as e:
                log_event(f"[LOCK STOP ERROR] {e}")

            panda_ws = None
            await asyncio.sleep(2)
            continue

        # ===== NORMALER WS BETRIEB =====
        try:
            async with websockets.connect(uri, ping_interval=20) as websocket:

                log_event(f"[WS] Verbunden mit Panda {PANDA_IP}")
                panda_ws = websocket

                # Nur binden wenn NICHT power_forced_off
                if not power_forced_off:

                    await websocket.send(json.dumps({
                        "printer": {
                            "ip": HOST_IP,
                            "sn": PRINTER_SN,
                            "access_code": ACCESS_CODE
                        }
                    }))

                    await websocket.send(json.dumps({
                        "get_settings": 1
                    }))

                # ⏳ Bind Watchdog starten
                asyncio.create_task(bind_watchdog())

                while True:
                    msg = await websocket.recv()
                    data = json.loads(msg)

                    if global_lock:
                        continue

                    # Nur verarbeiten wenn settings enthalten
                    if 'settings' in data:

                        # ✅ Bind bestätigt
                        if not bind_confirmed:
                            bind_confirmed = True
                            bind_warning_shown = False

                        incoming_settings = data['settings']
                        last_ws_settings.update(incoming_settings)
                        s = last_ws_settings

                        # Ist-Temperatur
                        if 'warehouse_temper' in incoming_settings:
                            current_data["kammer_ist"] = float(
                                incoming_settings['warehouse_temper']
                            )
                            mqtt_client.publish(
                                f"{MQTT_TOPIC_PREFIX}/ist",
                                incoming_settings['warehouse_temper']
                            )

                        # ===== SET_TEMP SYNC =====
                        if 'set_temp' in incoming_settings:

                            ws_temp = float(incoming_settings['set_temp'])
                            slicer_active = current_data.get("slicer_priority_mode", False)

                            if slicer_active:
                                current_data["kammer_soll"] = ws_temp
                                mqtt_client.publish(
                                    f"{MQTT_TOPIC_PREFIX}/soll",
                                    int(ws_temp),
                                    retain=True
                                )
                            else:
                                if (time.time() - last_ha_change) > 5.0:
                                    current_data["kammer_soll"] = ws_temp
                                    mqtt_client.publish(
                                        f"{MQTT_TOPIC_PREFIX}/soll",
                                        int(ws_temp),
                                        retain=True
                                    )

                        if 'hotbedtemp' in s:
                            current_data["bett_limit"] = float(s['hotbedtemp'])

                        if 'filtertemp' in s:
                            current_data["filtertemp"] = float(s['filtertemp'])

                        if 'filament_temp' in s:
                            current_data["filament_temp"] = int(s['filament_temp'])

                        if 'filament_timer' in s:
                            current_data["filament_timer"] = int(s['filament_timer'])

                        # ===== MODUS =====
                        global last_reported_mode, mode_change_hint

                        work_mode = s.get("work_mode")
                        work_on = s.get("work_on")

                        if global_lock:
                            modus = "LOCKED"
                        else:
                            if work_on in (1, True, "1"):
                                if work_mode == 1:
                                    modus = "Automatik"
                                elif work_mode == 2:
                                    modus = "Manuell"
                                elif work_mode == 3:
                                    modus = "Dry"
                                else:
                                    modus = "Standby"
                            else:
                                modus = "Standby"

                        if modus != last_reported_mode:
                            mqtt_client.publish(
                                f"{MQTT_TOPIC_PREFIX}/panda_modus",
                                modus,
                                retain=True
                            )
                            last_reported_mode = modus

                        # ===== MQTT Sync =====
                        if (time.time() - last_ha_change) > 8.0:

                            if 'filtertemp' in s:
                                mqtt_client.publish(
                                    f"{MQTT_TOPIC_PREFIX}/filtertemp",
                                    int(s['filtertemp']),
                                    retain=True
                                )

                            if 'hotbedtemp' in s:
                                mqtt_client.publish(
                                    f"{MQTT_TOPIC_PREFIX}/limit",
                                    int(s['hotbedtemp']),
                                    retain=True
                                )

                            if 'work_on' in s:
                                global desired_power_state, power_pending_until

                                ws_is_on = s['work_on'] in (True, 1, "1")
                                now = time.time()

                                # Während Pending: nicht zurückflippen
                                if desired_power_state is not None and now < power_pending_until:
                                    p_val = "1" if desired_power_state else "0"

                                    # Sobald bestätigt → Pending löschen
                                    if ws_is_on == desired_power_state:
                                        desired_power_state = None
                                        power_pending_until = 0.0

                                else:
                                    # Normalbetrieb
                                    p_val = "0" if power_forced_off else ("1" if ws_is_on else "0")

                                mqtt_client.publish(
                                    f"{MQTT_TOPIC_PREFIX}/work_on",
                                    p_val,
                                    retain=True
                                )

                                mqtt_client.publish(
                                    f"{MQTT_TOPIC_PREFIX}/panda_power",
                                    "ON" if p_val == "1" else "OFF",
                                    retain=True
                                )

                            if 'filament_temp' in s:
                                mqtt_client.publish(
                                    f"{MQTT_TOPIC_PREFIX}/dry_temp",
                                    int(s['filament_temp']),
                                    retain=True
                                )

                            if 'filament_timer' in s:
                                mqtt_client.publish(
                                    f"{MQTT_TOPIC_PREFIX}/dry_time",
                                    int(s['filament_timer']),
                                    retain=True
                                )

                            mqtt_client.publish(
                                f"{MQTT_TOPIC_PREFIX}/slicer_priority_mode",
                                "ON" if current_data.get("slicer_priority_mode", False) else "OFF",
                                retain=True
                            )

                            mqtt_client.publish(
                                f"{MQTT_TOPIC_PREFIX}/slicer_soll",
                                int(current_data.get("slicer_soll", 0)),
                                retain=True
                            )

                            mqtt_client.publish(
                                f"{MQTT_TOPIC_PREFIX}/slicer_target_temp",
                                int(current_data.get("slicer_soll", 0)),
                                retain=True
                            )

                            mqtt_client.publish(
                                f"{MQTT_TOPIC_PREFIX}/slicer_file",
                                current_data.get("last_analyzed_file", ""),
                                retain=True
                            )

                    else:
                        continue

        except Exception as e:
            if DEBUG:
                log_event(f"WS-Error: {e}")

            panda_ws = None
            await asyncio.sleep(5)

async def bind_watchdog():
    global bind_confirmed, bind_warning_shown

    await asyncio.sleep(10)

    if not bind_confirmed and not bind_warning_shown:
        log_event("⚠️ Bitte im Panda UI → Bind drücken!", force_console=True)

        mqtt_client.publish(
            f"{MQTT_TOPIC_PREFIX}/status",
            "Bitte im Panda UI 'Bind' drücken",
            retain=True
        )

        bind_warning_shown = True
        
# --- EMULATION ---
async def handle_panda(reader, writer):

    global last_switch_time, global_heating_state, terminal_cleared, mode_change_hint, bed_sensor_error
    setup_mqtt_discovery()
    log_event("[SERVER] Panda Client verbunden")
    try:
        # Initialer Handshake
        await reader.read(1024); writer.write(b'\x20\x02\x00\x00'); await writer.drain()
        sub_data = await reader.read(1024)
        if sub_data and sub_data[0] == 0x82:
            writer.write(b'\x90\x03' + sub_data[2:4] + b'\x00'); await writer.drain()

        while not writer.is_closing():
            try:
                # ============================================================
                # ✅ OPTIMIERUNG: HA REQUEST AUSLAGERN (verhindert TLS-Timeout)
                # ------------------------------------------------------------
                # requests.get ist BLOCKIEREND. 
                # Wenn HA langsam antwortet, friert der TLS Loop ein.
                # Deshalb wird der Request in einen Thread ausgelagert.
                # ============================================================
                loop = asyncio.get_running_loop()

                def fetch_ha():
                    return requests.get(
                        HA_URL,
                        headers={"Authorization": f"Bearer {HA_TOKEN}"},
                        timeout=2
                    )

                # ============================================================
                # ✅ HA SENSOR ERROR HANDLING (MIT STATUS-FLAG)
                # ============================================================
                try:
                    h_resp = await loop.run_in_executor(None, fetch_ha)
                    bed_ist = float(h_resp.json().get("state", "0"))

                    # Wenn vorher Fehler war → jetzt wieder OK melden
                    if bed_sensor_error:
                        log_event("[BED-SENSOR] Verbindung wieder OK", force_console=True)
                        mqtt_client.publish(
                            f"{MQTT_TOPIC_PREFIX}/status",
                            "Bereit",
                            retain=True
                        )
                        bed_sensor_error = False

                except Exception as ha_err:
                    bed_ist = 0.0
                    global_heating_state = 20.0  # Sicherheit AUS

                    if not bed_sensor_error:
                        log_event(f"[BED-SENSOR-ERR] {ha_err}", force_console=True)
                        mqtt_client.publish(
                            f"{MQTT_TOPIC_PREFIX}/status",
                            "Check Bed Temperatur Sensor",
                            retain=True
                        )
                        bed_sensor_error = True

                    await asyncio.sleep(2)
                    continue
                # ============================================================
                
                # 2. Variablen laden
                target, ist, limit = current_data["kammer_soll"], current_data["kammer_ist"], current_data["bett_limit"]
                f_threshold = current_data.get("filtertemp", 30.0)
                work_mode = int(last_ws_settings.get("work_mode", 0) or 0)

                # ============================================================
                # ✅ GLOBAL LOCK LOGIK (FIXED & STABILE HYSTERESE)
                # ------------------------------------------------------------
                if global_lock:
                    target_state, info = 20.0, "LOCKED"
                    global_heating_state = 20.0

                else:
                    # Standby → alles aus
                    if work_mode == 0:
                        target_state, info = 20.0, "Standby"

                    else:
                        target_state = global_heating_state

                        # =====================================
                        # 🔥 DRY MODE (eigene Logik)
                        # =====================================
                        if work_mode == 3:

                            target = float(
                                last_ws_settings.get("custom_temp", target)
                            )

                            remaining = int(
                                last_ws_settings.get("remaining_seconds", 0)
                            )

                            if remaining <= 0:
                                target_state, info = 20.0, "Fertig"

                            elif ist < (target - HYSTERESE):
                                target_state, info = 85.0, "Heizen..."

                            elif ist >= target:
                                target_state, info = 20.0, "Ziel erreicht"

                            else:
                                info = "Hysterese"

                        # =====================================
                        # 🔥 AUTO / MANUELL
                        # =====================================
                        else:
                            if work_mode == 1 and bed_ist < limit:
                                target_state, info = 20.0, "Warte auf Bett"

                            elif ist < (target - HYSTERESE):
                                target_state, info = 85.0, "Heizen..."

                            elif ist >= target:
                                target_state, info = 20.0, "Ziel erreicht"

                            else:
                                info = "Hysterese"

                    # ========================================================
                    # ⏱ SWITCH-TIMER LOGIK
                    # ========================================================
                    time_passed = (time.time() - last_switch_time)

                    if target_state == 20.0 and global_heating_state != 20.0:
                        global_heating_state = 20.0
                        last_switch_time = time.time()

                    elif (
                        target_state != global_heating_state
                        and time_passed > MIN_SWITCH_TIME
                    ):
                        global_heating_state = target_state
                        last_switch_time = time.time()

                # ============================================================
                
                # 4. Lüfter-Logik (Filter Fan)
                fan_state = "ON" if bed_ist >= f_threshold else "OFF"
                
# 5. Anzeige & MQTT Update
                sl = int(current_data.get("slicer_soll", 0))
                sl_prio = "SL-PRIO" if current_data.get("slicer_priority_mode", False) else "NORMAL"
                lock_indicator = "⚠️ LOCKED ⚠️" if global_lock else "READY"
                line = f"\r🟢 {lock_indicator} | Bed:{bed_ist}° | Kammer:{target}/{ist}° | Heiz:{'AN' if global_heating_state > 50 else 'AUS'} | Fan:{fan_state} | {info} | {sl_prio}:{sl}°"
                
                mode_change_hint = ""
                if not terminal_cleared: os.system('clear'); terminal_cleared = True
                print(f"{line}\033[K", end="", flush=True)

                # Status-Entitäten an HA senden
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/status", info, retain=True)
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/panda_heiz_status", info, retain=True)
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/fan", fan_state, retain=True)
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/version", PANDA_VERSION, retain=True)

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

                # MQTT Variable Length Encoding für das Display-Protokoll
                pkt = b'\x30'
                X = rem
                while X > 0:
                    eb = X % 128
                    X //= 128
                    if X > 0: eb |= 128
                    pkt += eb.to_bytes(1, 'big')

                writer.write(pkt + vh + payload); await writer.drain()

            except Exception as e:
                log_event(f"[EMU-LOOP-ERR] {e}", force_console=True); break
            
            await asyncio.sleep(2)

    finally:
        writer.close()

async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()
    asyncio.create_task(update_limits_from_ws())
    asyncio.create_task(slicer_auto_parser())
    ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_ctx.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
    
    # ✅ OPTIMIERUNG: SECLEVEL=0 für Panda Touch Kompatibilität (Legacy TLS)
    ssl_ctx.set_ciphers('DEFAULT@SECLEVEL=0:ALL')
    
    server = await asyncio.start_server(handle_panda, '0.0.0.0', 8883, ssl=ssl_ctx)
    log_event(f"[SERVER] TLS Server gestartet auf 8883 (SECLEVEL=0)")
    print(f"\n🚀 Panda-Logic-Sync {PANDA_VERSION}\n")
    async with server: await server.serve_forever()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n🛑 Stopp.")
