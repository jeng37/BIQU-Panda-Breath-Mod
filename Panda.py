#!/usr/bin/env python3
import asyncio, ssl, json, time, requests, websockets, os
import logging

# ==========================================
# KONFIGURATION
# ==========================================
DEBUG = False
DEBUG_TO_FILE = True 
HYSTERESE = 1.5         # Erst wieder ein, wenn 1.5 Grad unter Soll gefallen
MIN_SWITCH_TIME = 10    # Mindestpause für das Relais in Sekunden

HOST_IP = "192.168.8.174" 
PANDA_IP = "192.168.8.142"
PRINTER_SN = "01P00A123456789"
ACCESS_CODE = "01P00A12"
HA_URL = "http://192.168.8.195:8123/api/states/sensor.ks1c_bed_temperature"
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJmZjg4NzFjOTRiMTc0OTJlYTE4MWVhNDY1YmI5M2JjNiIsImlhdCI6MTc3MDI5OTE1OSwiZXhwIjoyMDg1NjU5MTU5fQ.Biu6Ood1bH-xMBHQnfRFE6h2yiFMWWywTfCnFmji61o"
# ==========================================

# Globale Zustandsvariablen (überleben Reconnects)
current_data = {"kammer_soll": 40.0, "kammer_ist": 0.0, "bett_limit": 50.0} 
global_heating_state = 20.0  # 20.0 = AUS, 85.0 = EIN
last_switch_time = 0
panda_connected = False
terminal_cleared = False

# Logging Setup
logging.basicConfig(level=logging.CRITICAL)
logger = logging.getLogger("PandaDebug")
if DEBUG_TO_FILE:
    file_handler = logging.FileHandler('panda_debug.log')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

def log_debug(msg):
    if DEBUG: print(f"{msg}")
    if DEBUG_TO_FILE: logger.info(msg)

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
    global panda_connected, terminal_cleared, last_switch_time, global_heating_state
    panda_connected = True
    
    try:
        await reader.read(1024)
        writer.write(b'\x20\x02\x00\x00')
        await writer.drain()
        sub_data = await reader.read(1024)
        if sub_data and sub_data[0] == 0x82:
            writer.write(b'\x90\x03' + sub_data[2:4] + b'\x00')
            await writer.drain()

        # Beim ersten BIND entscheiden: Wenn wir deutlich unter Soll sind, heizen wir sofort los
        if current_data["kammer_ist"] < (current_data["kammer_soll"] - 0.2):
            global_heating_state = 85.0

        while not writer.is_closing():
            try:
                h_resp = requests.get(HA_URL, headers={"Authorization": f"Bearer {HA_TOKEN}"}, timeout=3)
                real_bed_temp = float(h_resp.json()['state'])
                target = current_data["kammer_soll"]
                ist = current_data["kammer_ist"]
                limit = current_data["bett_limit"]
                
                now = time.time()
                can_switch = (now - last_switch_time) > MIN_SWITCH_TIME
                
                # --- STRRENGERE TARGET-LOGIK ---
                target_state = global_heating_state
                
                if real_bed_temp < limit:
                    target_state, info = 20.0, "SICHERHEIT: Bett-Stop"
                elif ist >= target:
                    # Schaltet ERST aus, wenn Ziel wirklich erreicht
                    target_state, info = 20.0, "Ziel erreicht (100%)"
                elif ist <= (target - HYSTERESE):
                    # Schaltet wieder ein, wenn zu weit abgekühlt
                    target_state, info = 85.0, "Heizen aktiv..."
                else:
                    # Bleibt im aktuellen Modus (heizt also weiter bis Ziel erreicht ist)
                    info = "Hysterese aktiv"

                # --- SCHALTPRÜFUNG ---
                if target_state != global_heating_state:
                    if can_switch or (target_state == 20.0 and real_bed_temp < limit):
                        global_heating_state = target_state
                        last_switch_time = now
                    else:
                        info += " (Sperrzeit-Schutz)"

                icon = "🔥 EIN" if global_heating_state > 50 else "❄️ AUS"
                line = f"\r🟢 ONLINE | Bed:{real_bed_temp}° | Kammer:{target}/{ist}° | {icon} | {info}"
                
                if not DEBUG:
                    if not terminal_cleared:
                        os.system('cls' if os.name == 'nt' else 'clear')
                        terminal_cleared = True
                    print(f"{line[:110].ljust(110)}", end="", flush=True)
                else:
                    log_debug(line.strip())

                writer.write(create_packet(global_heating_state))
                await writer.drain()
            except (ConnectionResetError, BrokenPipeError): break
            except Exception as e: log_debug(f"[LOOP-ERR] {e}")
            await asyncio.sleep(2)
    finally:
        panda_connected = False
        writer.close()

async def main():
    asyncio.create_task(update_limits_from_ws())
    ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_ctx.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
    ssl_ctx.set_ciphers('DEFAULT@SECLEVEL=1') 
    server = await asyncio.start_server(handle_panda, '0.0.0.0', 8883, ssl=ssl_ctx)
    print(f"\n🚀 Panda-Logic-Sync V1.11 (Persistent Mode)")
    print(f"👉 BITTE 'BIND' DRÜCKEN FÜR START...\n")
    async with server: await server.serve_forever()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n🛑 Stopp.")
