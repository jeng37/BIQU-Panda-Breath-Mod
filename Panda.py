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

current_data = {"kammer_soll": 0.0, "kammer_ist": 0.0, "bett_limit": 0.0, "filtertemp": 0.0} 
ha_memory = {"kammer_soll": 0.0, "bett_limit": 0.0, "filtertemp": 0.0}

global_heating_state = 20.0  
last_switch_time = 0
last_ha_change = 0           
panda_ws = None              
main_loop = None
terminal_cleared = False

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.CRITICAL)
file_logger = logging.getLogger("PandaFullLog")
file_logger.propagate = False
file_logger.setLevel(logging.INFO)

if DEBUG_TO_FILE:
    f_handler = logging.FileHandler('panda_debug.log')
    f_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    file_logger.addHandler(f_handler)

def log_event(msg, force_console=False):
    if DEBUG_TO_FILE:
        file_logger.info(msg)
    if force_console or (DEBUG and "[MQTT->PANDA]" in msg):
        print(f"\nINFO:PandaDebug:{msg}")

# --- MQTT LOGIK ---
def on_mqtt_message(client, userdata, msg):
    global current_data, last_ha_change, ha_memory
    try:
        val = float(msg.payload.decode())
        last_ha_change = time.time()
        
        key = None
        if "soll/set" in msg.topic: key, data_key = "set_temp", "kammer_soll"
        elif "limit/set" in msg.topic: key, data_key = "hotbedtemp", "bett_limit"
        elif "filter/set" in msg.topic: key, data_key = "filtertemp", "filtertemp"
        
        if key:
            current_data[data_key] = val
            ha_memory[data_key] = val
            log_event(f"[MQTT->PANDA] {key} -> {val}")
            
            if panda_ws is not None:
                try:
                    asyncio.run_coroutine_threadsafe(
                        panda_ws.send(json.dumps({"settings": {key: int(val)}})), 
                        main_loop
                    )
                    client.publish(msg.topic.replace("/set", ""), val, retain=True)
                except Exception: pass
    except Exception as e:
        log_event(f"[MQTT-ERR] {e}", force_console=True)

def setup_mqtt():
    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id=f"PandaMod_{PRINTER_SN}")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_message = on_mqtt_message
    client.connect(MQTT_BROKER, 1883, 60)
    client.subscribe(f"{MQTT_TOPIC_PREFIX}/+/set")
    client.loop_start()
    return client

mqtt_client = setup_mqtt()

def setup_mqtt_discovery():
    base = MQTT_TOPIC_PREFIX
    dev = {"identifiers": [PRINTER_SN], "name": "Panda Breath Mod", "model": "V5.1 Final", "manufacturer": "Biqu"}
    
    # Steuerungseinheiten (Numbers)
    for sfx, name in [("soll", "Kammer Soll"), ("limit", "Bett Limit"), ("filter", "Filter Fan")]:
        u_id = f"pb_v51_{PRINTER_SN}_{sfx}"
        cfg = {"name": name, "state_topic": f"{base}/{sfx}", "command_topic": f"{base}/{sfx}/set", 
               "unique_id": u_id, "device": dev, "min": 20, "max": 80, "step": 1, "unit_of_measurement": "°C", "mode": "box"}
        mqtt_client.publish(f"homeassistant/number/{u_id}/config", json.dumps(cfg), retain=True)
    
    # Sensoren (Ist-Temperatur & Heiz-Status)
    mqtt_client.publish(f"homeassistant/sensor/pb_v51_{PRINTER_SN}_ist/config", json.dumps({
        "name": "Kammer Ist", "state_topic": f"{base}/ist", "unique_id": f"pb_v51_{PRINTER_SN}_ist", 
        "device": dev, "unit_of_measurement": "°C", "device_class": "temperature"
    }), retain=True)
    
    # FIX: Heiz Status Entity registrieren
    mqtt_client.publish(f"homeassistant/sensor/pb_v51_{PRINTER_SN}_status/config", json.dumps({
        "name": "Heiz Status", "state_topic": f"{base}/status", "unique_id": f"pb_v51_{PRINTER_SN}_status", 
        "device": dev, "icon": "mdi:radiator"
    }), retain=True)

# --- HARDWARE LOGIK ---
def create_packet(temp):
    data = {"print": {"command": "push_status", "msg": 1, "sequence_id": str(int(time.time())),
            "warehouse_temper": float(temp), "bed_temper": float(temp), "chamber_temper": float(temp),
            "bed_target_temper": 100.0 if temp > 50 else 0.0, "gcode_state": "RUNNING" if temp > 50 else "IDLE", "mc_percent": 50}}
    payload = json.dumps(data).encode(); topic = f"device/{PRINTER_SN}/report".encode()
    vh = len(topic).to_bytes(2, 'big') + topic; rem = len(vh) + len(payload)
    packet = b'\x30'; X = rem
    while X > 0:
        eb = X % 128; X //= 128
        if X > 0: eb |= 128
        packet += eb.to_bytes(1, 'big')
    return packet + vh + payload

async def update_limits_from_ws():
    global current_data, panda_ws, ha_memory
    uri = f"ws://{PANDA_IP}/ws"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as websocket:
                panda_ws = websocket
                log_event("[WS] Verbindung hergestellt")
                await websocket.send(json.dumps({"printer": {"ip": HOST_IP, "sn": PRINTER_SN, "access_code": ACCESS_CODE}}))
                await websocket.send(json.dumps({"get_settings": 1}))
                
                await asyncio.sleep(1)
                if ha_memory["kammer_soll"] > 0:
                    await websocket.send(json.dumps({"settings": {"set_temp": int(ha_memory["kammer_soll"])}}))
                    log_event(f"[RECONNECT-FIX] Erzwinge HA-Sollwert: {ha_memory['kammer_soll']}")

                while True:
                    msg = await websocket.recv()
                    data = json.loads(msg)
                    if 'settings' in data:
                        s = data['settings']
                        if 'warehouse_temper' in s: 
                            current_data["kammer_ist"] = float(s['warehouse_temper'])
                            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/ist", s['warehouse_temper'])
                        
                        if (time.time() - last_ha_change) > 5.0:
                            if 'set_temp' in s: 
                                val = float(s['set_temp'])
                                if ha_memory["kammer_soll"] == 0 or abs(val - ha_memory["kammer_soll"]) < 1.0:
                                    current_data["kammer_soll"] = val
                                    mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/soll", int(val), retain=True)
                            if 'hotbedtemp' in s: 
                                current_data["bett_limit"] = float(s['hotbedtemp'])
                                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/limit", int(s['hotbedtemp']), retain=True)
        except Exception as e: 
            log_event(f"[WS-DISCONNECT] {e}")
            panda_ws = None
            await asyncio.sleep(5)

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
                bed_ist = float(h_resp.json()['state'])
                target, ist, limit = current_data["kammer_soll"], current_data["kammer_ist"], current_data["bett_limit"]
                
                if target > 0:
                    now = time.time(); can_switch = (now - last_switch_time) > MIN_SWITCH_TIME
                    target_state = global_heating_state
                    if bed_ist < limit: target_state, info = 20.0, "SICHERHEIT: Bett-Stop"
                    elif ist >= target: target_state, info = 20.0, "Ziel erreicht"
                    elif ist <= (target - HYSTERESE): target_state, info = 85.0, "Heizen aktiv..."
                    else: info = "Hysterese aktiv"
                    if target_state != global_heating_state and can_switch:
                        global_heating_state = target_state
                        last_switch_time = now
                else: info = "Warte auf Panda-Werte..."

                icon = "🔥 EIN" if global_heating_state > 50 else "❄️ AUS"
                line = f"\r🟢 ONLINE | Bed:{bed_ist}° | Kammer:{target}/{ist}° | {icon} | {info}"
                
                if not terminal_cleared: os.system('clear'); terminal_cleared = True
                print(f"{line}\033[K", end="", flush=True)
                log_event(line.strip()) 
                
                # Status an MQTT senden
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/status", info, retain=True)
                
                writer.write(create_packet(global_heating_state)); await writer.drain()
            except Exception: break
            await asyncio.sleep(2)
    finally: writer.close()

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
