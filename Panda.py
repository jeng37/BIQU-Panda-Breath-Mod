#!/usr/bin/env python3
import asyncio, ssl, json, time, requests, websockets, os
import logging
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

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
MQTT_USER = "mqtt-user"
# MQTT Passwort: Das zugehörige Passwort für den MQTT-Benutzer.
MQTT_PASS = "mqtt-password"
# MQTT Präfix: Die Basis für alle Topics (z.B. panda_breath/soll).
MQTT_TOPIC_PREFIX = "panda_breath"
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
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ey............"
# ==========================================


# current_data nutzt jetzt die exakten Namen aus der Hardware (filament_temp/timer)
current_data = {
    "kammer_soll": 0.0, 
    "kammer_ist": 0.0, 
    "bett_limit": 50.0, 
    "filtertemp": 30.0, 
    "filament_temp": 45, 
    "filament_timer": 3
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

# --- MQTT LOGIK ---
# --- MQTT LOGIK ---
def on_mqtt_message(client, userdata, msg):
    global current_data, last_ha_change, ha_memory

    # --- MANUELL MODUS (Power On) ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/manual/set":
        log_event("[MQTT->PANDA] work_mode -> 2 (FORCE ON)")
        if panda_ws:
            asyncio.run_coroutine_threadsafe(panda_ws.send(json.dumps({"settings": {"work_mode": 2}})), main_loop)
        return

    # --- AUTO MODUS ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/auto/set":
        log_event("[MQTT->PANDA] work_mode -> 1 (AUTO)")
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
                    
                    # Sendet echtes JSON-true/false an die Hardware
                    await panda_ws.send(json.dumps({"settings": {"work_on": is_on}}))
            
            asyncio.run_coroutine_threadsafe(p_flow(), main_loop)
            log_event(f"[MQTT->PANDA] work_on -> {is_on}")
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/work_on", "1" if is_on else "0", retain=True)
        except Exception as e:
            log_event(f"[WORK-ON-ERR] {e}", force_console=True)
        return

    # --- DRYING START (FIXED HARDWARE COMMANDS) ---
    if msg.topic == f"{MQTT_TOPIC_PREFIX}/drying/set":
        log_event("[MQTT->PANDA] DRYER START (NATIVE CMD)")
        async def d_flow():
            if panda_ws:
                t = int(current_data.get("filament_temp", 50))
                h = int(current_data.get("filament_timer", 3))
                await panda_ws.send(json.dumps({
                    "settings": {
                        "filament_temp": t, 
                        "filament_timer": h,
                        "filament_drying_mode": 3 # 3 = Custom
                    }, 
                    "ui_action": "custom"
                }))
                await asyncio.sleep(0.5)
                await panda_ws.send(json.dumps({"settings": {"work_mode": 3, "isrunning": 1}}))
        asyncio.run_coroutine_threadsafe(d_flow(), main_loop)
        return

    # --- TEMPERATUREN & FILTER ---
    try:
        val_str = msg.payload.decode()
        val = float(val_str)
        last_ha_change = time.time()
        
        # 1. Spezialfall Dryer-Einstellungen (nur intern speichern & Bestätigen)
        if "/dry_temp/set" in msg.topic:
            current_data["filament_temp"] = int(val)
            log_event(f"[MQTT->PANDA] dry_temp -> {int(val)}")
            mqtt_client.publish(msg.topic.replace("/set", ""), int(val), retain=True)
            return
        if "/dry_time/set" in msg.topic:
            current_data["filament_timer"] = int(val)
            log_event(f"[MQTT->PANDA] dry_time -> {int(val)}")
            mqtt_client.publish(msg.topic.replace("/set", ""), int(val), retain=True)
            return

        # 2. Hardware-Settings (Soll-Temp, Bett-Limit, Filter-Schwelle)
        key = None
        if "soll/set" in msg.topic: key, data_key = "set_temp", "kammer_soll"
        elif "limit/set" in msg.topic: key, data_key = "hotbedtemp", "bett_limit"
        elif "filtertemp/set" in msg.topic: key, data_key = "filtertemp", "filtertemp" 
        
        if key:
            current_data[data_key] = val
            log_event(f"[MQTT->PANDA] Setze {key} auf {int(val)}")
            if panda_ws: 
                asyncio.run_coroutine_threadsafe(
                    panda_ws.send(json.dumps({"settings": {key: int(val)}})), 
                    main_loop
                )
            client.publish(msg.topic.replace("/set", ""), val, retain=True)
            
    except Exception as e:
        log_event(f"[TEMP-SET-ERR] {e}", force_console=True)

def setup_mqtt():
    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id=f"PandaNative_{PRINTER_SN}")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_message = on_mqtt_message
    client.connect(MQTT_BROKER, 1883, 60)
    client.subscribe(f"{MQTT_TOPIC_PREFIX}/+/set")
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

# --- WS LOOP ---
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
                            
                            # NEU: Filter-Schwelle an Home Assistant senden
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
                            
                        # Debug-Log für dich im Terminal
                        if DEBUG:
                            print(f"DEBUG: WS-Sync -> Soll: {current_data['kammer_soll']} | Ist: {current_data['kammer_ist']} | Filter: {current_data.get('filtertemp')}")

        except Exception as e:
            if DEBUG: print(f"DEBUG: WS-Error: {e}")
            panda_ws = None
            await asyncio.sleep(5)

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
                f_threshold = current_data.get("filtertemp", 30.0) # Schwelle für Lüfter
                
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
                line = f"\r🟢 ONLINE | Bed:{bed_ist}° | Kammer:{target}/{ist}° | Heiz:{'AN' if global_heating_state > 50 else 'AUS'} | Fan:{fan_state} | {info}"
                if not terminal_cleared: os.system('clear'); terminal_cleared = True
                print(f"{line}\033[K", end="", flush=True)
                
                # Status-Entitäten an HA senden
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/status", info, retain=True)
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/fan", fan_state, retain=True)
                
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
    asyncio.create_task(update_limits_from_ws())
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
