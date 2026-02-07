#!/usr/bin/env python3
import asyncio, ssl, json, time, requests, websockets, os
import logging
import paho.mqtt.client as mqtt

# ==========================================
# KONFIGURATION
# ==========================================
DEBUG = False
DEBUG_TO_FILE = True 

MQTT_BROKER = "192.168.x.xxx"
MQTT_PORT = 1883
MQTT_USER = "mqtt-user"
MQTT_PASS = "mqtt-password"
MQTT_TOPIC_PREFIX = "panda_breath"

HOST_IP = "192.168.x.xxx" 
PANDA_IP = "192.168.x.xxx"
PRINTER_SN = "01P00A123456789"
ACCESS_CODE = "01P00A12"
HA_URL = "http://192.168.x.xxx:8123/api/states/sensor.ks1c_bed_temperature"
HA_TOKEN = ""

HYSTERESE = 1.5
MIN_SWITCH_TIME = 10
# ==========================================

current_data = {"kammer_soll": 40.0, "kammer_ist": 0.0, "bett_limit": 50.0} 
global_heating_state = 20.0
last_switch_time = 0
terminal_ready = False

mqtt_client = mqtt.Client(client_id=f"PandaMod_{PRINTER_SN}")

# --- MQTT LOGIK ---
def on_mqtt_message(client, userdata, msg):
    global current_data
    try:
        payload = float(msg.payload.decode())
        if "soll/set" in msg.topic:
            current_data["kammer_soll"] = payload
        elif "limit/set" in msg.topic:
            current_data["bett_limit"] = payload
    except: pass

def setup_mqtt_discovery():
    try:
        mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
        mqtt_client.on_message = on_mqtt_message
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.subscribe(f"{MQTT_TOPIC_PREFIX}/+/set")
        mqtt_client.loop_start()

        base = MQTT_TOPIC_PREFIX
        disc = "homeassistant"
        device = {"identifiers": [f"panda_{PRINTER_SN}"], "name": "Panda Breath Mod", "manufacturer": "Biqu", "model": "V2.5"}

        for suffix, name, mini, maxi in [("soll", "Kammer Soll", 20, 75), ("limit", "Bett Limit", 30, 80)]:
            config = {
                "name": name,
                "state_topic": f"{base}/{suffix}",
                "command_topic": f"{base}/{suffix}/set",
                "unique_id": f"panda_{PRINTER_SN}_{suffix}",
                "unit_of_measurement": "°C",
                "min": mini, "max": maxi, "step": 1,
                "mode": "box", # Zeigt Slider UND Eingabefeld in HA
                "device": device
            }
            mqtt_client.publish(f"{disc}/number/panda_{suffix}/config", json.dumps(config), retain=True)
            
        mqtt_client.publish(f"{disc}/sensor/panda_ist/config", json.dumps({
            "name": "Kammer Ist", "state_topic": f"{base}/ist", "unit_of_measurement": "°C", 
            "device_class": "temperature", "unique_id": f"panda_{PRINTER_SN}_ist", "device": device
        }), retain=True)
        mqtt_client.publish(f"{disc}/sensor/panda_status/config", json.dumps({
            "name": "Heiz Status", "state_topic": f"{base}/status", "unique_id": f"panda_{PRINTER_SN}_status", "device": device
        }), retain=True)
    except: pass

def create_packet(temp):
    effective_target = 100.0 if temp > 50 else 0.0
    gcode_state = "RUNNING" if temp > 50 else "IDLE"
    data = {"print": {"command": "push_status", "msg": 1, "sequence_id": str(int(time.time())),
            "warehouse_temper": float(temp), "bed_temper": float(temp), "chamber_temper": float(temp),
            "bed_target_temper": effective_target, "gcode_state": gcode_state, "mc_percent": 50}}
    payload = json.dumps(data).encode()
    topic = f"device/{PRINTER_SN}/report".encode()
    vh = len(topic).to_bytes(2, 'big') + topic
    rem = len(vh) + len(payload)
    packet = b'\x30'
    X = rem
    while X > 0:
        eb = X % 128; X //= 128
        if X > 0: eb |= 128
        packet += eb.to_bytes(1, 'big')
    return packet + vh + payload

async def update_limits_from_ws():
    global current_data
    uri = f"ws://{PANDA_IP}/ws"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=None) as websocket:
                set_printer = {"printer": {"ip": HOST_IP, "sn": PRINTER_SN, "access_code": ACCESS_CODE}}
                await websocket.send(json.dumps(set_printer))
                while True:
                    msg = await websocket.recv()
                    data = json.loads(msg)
                    if 'settings' in data:
                        s = data['settings']
                        if 'set_temp' in s: current_data["kammer_soll"] = float(s['set_temp'])
                        if 'hotbedtemp' in s: current_data["bett_limit"] = float(s['hotbedtemp'])
                        if 'warehouse_temper' in s: current_data["kammer_ist"] = float(s['warehouse_temper'])
        except: await asyncio.sleep(5)

async def handle_panda(reader, writer):
    global last_switch_time, global_heating_state, terminal_ready
    setup_mqtt_discovery()
    
    try:
        await reader.read(1024)
        writer.write(b'\x20\x02\x00\x00')
        await writer.drain()
        sub_data = await reader.read(1024)
        if sub_data and sub_data[0] == 0x82:
            writer.write(b'\x90\x03' + sub_data[2:4] + b'\x00')
            await writer.drain()

        while not writer.is_closing():
            try:
                h_resp = requests.get(HA_URL, headers={"Authorization": f"Bearer {HA_TOKEN}"}, timeout=3)
                real_bed_temp = float(h_resp.json()['state'])
                target, ist, limit = current_data["kammer_soll"], current_data["kammer_ist"], current_data["bett_limit"]
                
                now = time.time()
                can_switch = (now - last_switch_time) > MIN_SWITCH_TIME
                target_state = global_heating_state
                
                # --- LOGIK ---
                if real_bed_temp < limit:
                    target_state, info = 20.0, "Bett-Stop"
                elif ist >= target and ist > 0:
                    target_state, info = 20.0, "Ziel erreicht"
                elif ist <= (target - HYSTERESE) and ist > 0:
                    target_state, info = 85.0, "Heizen aktiv..."
                else:
                    info = "Hysterese aktiv" if ist > 0 else "Warten auf Sensor..."

                if target_state != global_heating_state:
                    if can_switch or (target_state == 20.0 and real_bed_temp < limit):
                        global_heating_state, last_switch_time = target_state, now
                    else:
                        info += " (Sperrzeit)"

                # MQTT
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/ist", ist)
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/soll", target)
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/limit", limit)
                mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/status", info)

                # TERMINAL OUTPUT
                icon = "🔥 EIN" if global_heating_state > 50 else "❄️ AUS"
                ist_str = f"{ist}°" if ist > 0 else "??.?"
                line = f"\r🟢 ONLINE | Bed:{real_bed_temp}° | Kammer:{target}/{ist_str} | {icon} | {info}"
                
                if not DEBUG:
                    print(f"{line[:115].ljust(115)}", end="", flush=True)

                writer.write(create_packet(global_heating_state))
                await writer.drain()
            except: break
            await asyncio.sleep(2)
    finally:
        writer.close()

async def main():
    # Terminal einmalig beim Start löschen
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"🚀 Panda-Logic-Sync V2.5 (Broker: {MQTT_BROKER})")
    print(f"👉 Warte auf Verbindung vom Panda Touch...")
    
    asyncio.create_task(update_limits_from_ws())
    ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_ctx.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
    ssl_ctx.set_ciphers('DEFAULT@SECLEVEL=1') 
    server = await asyncio.start_server(handle_panda, '0.0.0.0', 8883, ssl=ssl_ctx)
    async with server: await server.serve_forever()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n🛑 Stopp.")
