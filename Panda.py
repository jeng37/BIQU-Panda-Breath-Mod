#!/usr/bin/env python3
import asyncio, ssl, json, time, requests, websockets, os
import logging
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import re # Für G-Code Analyse

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
# MQTT Präfix: Die Basis für alle Topics (z.B. panda_breath/soll).
MQTT_TOPIC_PREFIX = "panda_breath"
# Host IP: Die statische IP-Adresse des Rechners, on dem dieses Skript läuft.
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

# --- SLICER BYPASS KONFIGURATION ---
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
    "slicer_mode": False,   # Modus-Status
    "slicer_soll": 0.0,     # Gefundener Wert (wird immer angezeigt)
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
        print(f" INFO:PandaDebug:{msg}")

# --- HELPER ---
def safe_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
        
# --- MQTT LOGIK ---
def on_mqtt_message(client, userdata, msg):
    global current_data, last_ha_change, ha_memory

    # --- SLICER MODE SCHALTER ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/slicer_mode/set":
        payload = msg.payload.decode().strip().lower()
        current_data["slicer_mode"] = payload in ("on", "1", "true")
        if current_data["slicer_mode"] and current_data["slicer_soll"] > 15:
            current_data["kammer_soll"] = current_data["slicer_soll"]
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/soll", current_data["kammer_soll"], retain=True)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_mode", "ON" if current_data["slicer_mode"] else "OFF", retain=True)
        log_event(f"Modus-Wechsel: Slicer Mode ist jetzt {'AN' if current_data['slicer_mode'] else 'AUS'}", force_console=True)
        return

    # --- MANUELL MODUS (Power On) ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/manual/set":
        # Slicer Mode deaktivieren
        current_data["slicer_mode"] = False
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_mode", "OFF", retain=True)
        
        log_event("Modus-Wechsel: Manueller Mode ist jetzt AN", force_console=True)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/mode", "Manuell", retain=True)
        if panda_ws:
            asyncio.run_coroutine_threadsafe(panda_ws.send(json.dumps({"settings": {"work_mode": 2}})), main_loop)
        return

    # --- AUTO MODUS ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/auto/set":
        # Slicer Mode deaktivieren
        current_data["slicer_mode"] = False
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_mode", "OFF", retain=True)

        log_event("Modus-Wechsel: Automatik Mode ist jetzt AN", force_console=True)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/mode", "Automatik", retain=True)
        if panda_ws:
            asyncio.run_coroutine_threadsafe(panda_ws.send(json.dumps({"settings": {"work_mode": 1}})), main_loop)
        return

    # --- START / STOP (work_on) - NATIVE BOOLEAN FIX ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/work_on/set":
        try:
            payload = msg.payload.decode().strip().lower()
            is_on = payload in ("on", "1", "true")
            async def p_flow():
                if panda_ws:
                    if not is_on: # Wenn AUS (False)
                        await panda_ws.send(json.dumps({"settings": {"isrunning": 0}}))
                        await asyncio.sleep(0.2)
                        await panda_ws.send(json.dumps({"settings": {"work_mode": 0}}))
                        await asyncio.sleep(0.2)
                    await panda_ws.send(json.dumps({"settings": {"work_on": is_on}}))
            asyncio.run_coroutine_threadsafe(p_flow(), main_loop)
            log_event(f"[MQTT->PANDA] work_on -> {is_on}")
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/work_on", "1" if is_on else "0", retain=True)
        except Exception as e:
            log_event(f"[WORK-ON-ERR] {e}", force_console=True)
        return

    # --- DRYING START (FIXED HARDWARE COMMANDS) ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/drying/set":
        # Slicer Mode deaktivieren
        current_data["slicer_mode"] = False
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_mode", "OFF", retain=True)

        log_event("Modus-Wechsel: Dryer Mode ist jetzt AN", force_console=True)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/mode", "Trocknen", retain=True)
        async def d_flow():
            if panda_ws:
                t, h = int(current_data.get("filament_temp", 50)), int(current_data.get("filament_timer", 3))
                await panda_ws.send(json.dumps({"settings": {"filament_temp": t, "filament_timer": h, "filament_drying_mode": 3}, "ui_action": "custom"}))
                await asyncio.sleep(0.5)
                await panda_ws.send(json.dumps({"settings": {"work_mode": 3, "isrunning": 1}}))
        asyncio.run_coroutine_threadsafe(d_flow(), main_loop)
        return

    # --- TEMPERATUREN & FILTER ---
    try:
        val_str = msg.payload.decode().strip()
        if not re.match(r"^-?\d+(\.\d+)?$", val_str): return
        val = float(val_str)
        last_ha_change = time.time()
        
        if "/dry_temp/set" in msg.topic:
            current_data["filament_temp"] = int(val)
            mqtt_client.publish(msg.topic.replace("/set", ""), int(val), retain=True)
            return
        if "/dry_time/set" in msg.topic:
            current_data["filament_timer"] = int(val)
            mqtt_client.publish(msg.topic.replace("/set", ""), int(val), retain=True)
            return

        key = None
        if "soll/set" in msg.topic: key, data_key = "set_temp", "kammer_soll"
        elif "limit/set" in msg.topic: key, data_key = "hotbedtemp", "bett_limit"
        elif "filtertemp/set" in msg.topic: key, data_key = "filtertemp", "filtertemp" 
        
        if key:
            current_data[data_key] = val
            if panda_ws: 
                asyncio.run_coroutine_threadsafe(panda_ws.send(json.dumps({"settings": {key: int(val)}})), main_loop)
            client.publish(msg.topic.replace("/set", ""), val, retain=True)
    except Exception as e:
        if DEBUG: log_event(f"[TEMP-SET-ERR] {e}", force_console=True)

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
    mqtt_client.publish(f"homeassistant/switch/{PRINTER_SN}_slicer/config", json.dumps({"name": "Slicer Mode Priority", "state_topic": f"{base}/slicer_mode", "command_topic": f"{base}/slicer_mode/set", "unique_id": f"{PRINTER_SN}_slicer", "device": dev, "icon": "mdi:layers-triple"}), retain=True)

# --- AUTOMATISCHER SLICER-PARSER ---
async def slicer_auto_parser():
    while True:
        try:
            status_url = f"http://{PRINTER_IP}/printer/objects/query?print_stats"
            r = requests.get(status_url, timeout=2).json()
            filename = r['result']['status']['print_stats']['filename']
            if filename and filename != current_data["last_analyzed_file"]:
                file_url = f"http://{PRINTER_IP}/server/files/gcodes/{filename}"
                resp = requests.get(file_url, headers={'Range': 'bytes=0-50000'}, timeout=5)
                match = re.search(r'(?:M191|M141)\s+S(\d+)', resp.text)
                if match:
                    new_target = float(match.group(1))
                    current_data["slicer_soll"] = new_target
                    current_data["last_analyzed_file"] = filename
                    if current_data["slicer_mode"]:
                        current_data["kammer_soll"] = new_target
                        if panda_ws: await panda_ws.send(json.dumps({"settings": {"set_temp": int(new_target)}}))
                        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/soll", new_target, retain=True)
                    mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_target", new_target, retain=True)
        except: pass
        await asyncio.sleep(5)

# --- WS LOOP ---
async def update_limits_from_ws():
    global current_data, panda_ws
    uri = f"ws://{PANDA_IP}/ws"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as websocket:
                panda_ws = websocket
                await websocket.send(json.dumps({"printer": {"ip": HOST_IP, "sn": PRINTER_SN, "access_code": ACCESS_CODE}}))
                await websocket.send(json.dumps({"get_settings": 1}))
                while True:
                    msg = await websocket.recv()
                    data = json.loads(msg)
                    if 'settings' in data:
                        s = data['settings']
                        if 'warehouse_temper' in s: 
                            current_data["kammer_ist"] = float(s['warehouse_temper'])
                            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/ist", s['warehouse_temper'])
                        if 'set_temp' in s and (time.time() - last_ha_change) > 8.0 and not current_data["slicer_mode"]:
                             current_data["kammer_soll"] = float(s['set_temp'])
                        if 'work_mode' in s:
                            m_val, m_txt = int(s['work_mode']), "Aus"
                            if m_val == 1: m_txt = "Automatik"
                            elif m_val == 2: m_txt = "Manuell"
                            elif m_val == 3: m_txt = "Trocknen"
                            if (time.time() - last_ha_change) > 8.0:
                                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/mode", m_txt, retain=True)
        except:
            panda_ws = None
            await asyncio.sleep(5)

# --- EMULATION ---
async def handle_panda(reader, writer):
    global last_switch_time, global_heating_state, terminal_cleared
    setup_mqtt_discovery()
    try:
        await reader.read(1024); writer.write(b'\x20\x02\x00\x00'); await writer.drain()
        sub_data = await reader.read(1024)
        if sub_data and sub_data[0] == 0x82: 
            writer.write(b'\x90\x03' + sub_data[2:4] + b'\x00'); await writer.drain()
        while not writer.is_closing():
            try:
                h_resp = requests.get(HA_URL, headers={"Authorization": f"Bearer {HA_TOKEN}"}, timeout=2)
                bed_ist = safe_float(h_resp.json().get('state', 0.0))
                target, ist, limit = current_data["kammer_soll"], current_data["kammer_ist"], current_data["bett_limit"]
                if target > 15:
                    target_state = global_heating_state
                    if bed_ist < limit: target_state, info = 20.0, "Bett-Stop"
                    elif ist >= target: 
                        target_state, info = 20.0, "Ziel erreicht"
                        if current_data["slicer_mode"]:
                            current_data["slicer_mode"] = False
                            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/slicer_mode", "OFF", retain=True)
                    elif ist <= (target - HYSTERESE): target_state, info = 85.0, "Heizen..."
                    else: info = "Heizen..." if global_heating_state > 50 else "Hysterese"
                    if target_state != global_heating_state and (time.time() - last_switch_time) > MIN_SWITCH_TIME:
                        global_heating_state, last_switch_time = target_state, time.time()
                else: info, global_heating_state = "Standby", 20.0
                sl_info = f"SL:{current_data['slicer_soll']}°"
                line = f"\r🟢 ONLINE | Mode: {'SLICER' if current_data['slicer_mode'] else 'AUTO'} ({sl_info}) | Bed:{bed_ist}° | Kammer:{target}/{ist}° | {info}"
                if not terminal_cleared: os.system('clear'); terminal_cleared = True
                print(f"{line}\033[K", end="", flush=True)
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/status", info, retain=True)
                data = {"print": {"command": "push_status", "msg": 1, "warehouse_temper": float(ist), "bed_temper": float(bed_ist), "chamber_temper": float(ist), "bed_target_temper": 100.0 if global_heating_state > 50 else 0.0, "gcode_state": "RUNNING"}}
                payload = json.dumps(data).encode(); topic = f"device/{PRINTER_SN}/report".encode()
                vh = len(topic).to_bytes(2, 'big') + topic; rem = len(vh) + len(payload)
                pkt = b'\x30'; X = rem
                while X > 0:
                    eb = X % 128; X //= 128
                    if X > 0: eb |= 128
                    pkt += eb.to_bytes(1, 'big')
                writer.write(pkt + vh + payload); await writer.drain()
            except: break
            await asyncio.sleep(2)
    finally: writer.close()

async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()
    asyncio.create_task(update_limits_from_ws())
    asyncio.create_task(slicer_auto_parser())
    ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_ctx.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
    ssl_ctx.set_ciphers('DEFAULT@SECLEVEL=1') 
    server = await asyncio.start_server(handle_panda, '0.0.0.0', 8883, ssl=ssl_ctx)
    os.system('clear')
    print(f"\n🚀 Panda-Logic-Sync V1.5")
    async with server: await server.serve_forever()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n🛑 Stopp.")
