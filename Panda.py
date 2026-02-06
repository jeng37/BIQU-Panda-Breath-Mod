#!/usr/bin/env python3
import asyncio, ssl, json, time, requests, websockets, os
import logging

# ==========================================
# KONFIGURATION
# ==========================================
HOST_IP = "192.168.8.174" 
PANDA_IP = "192.168.8.142"
PRINTER_SN = "01P00A123456789"
ACCESS_CODE = "01P00A12"
HA_URL = "http://192.168.8.195:8123/api/states/sensor.ks1c_bed_temperature"
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJmZjg4NzFjOTRiMTc0OTJlYTE4MWVhNDY1YmI5M2JjNiIsImlhdCI6MTc3MDI5OTE1OSwiZXhwIjoyMDg1NjU5MTU5fQ.Biu6Ood1bH-xMBHQnfRFE6h2yiFMWWywTfCnFmji61o"
# ==========================================

logging.basicConfig(level=logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

current_data = {"kammer_soll": 40.0, "kammer_ist": 0.0, "bett_limit": 50.0} 
panda_connected = False
terminal_cleared = False # Merker für das Aufräumen
ha_session = requests.Session()
ha_session.headers.update({"Authorization": f"Bearer {HA_TOKEN}"})

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
    global panda_connected, terminal_cleared
    panda_connected = True
    
    # Sobald die Verbindung steht: Terminal säubern
    if not terminal_cleared:
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"✅ Verbindung hergestellt! Panda Breath wird gesteuert...\n")
        terminal_cleared = True

    last_val = 20.0
    try:
        await reader.read(1024)
        writer.write(b'\x20\x02\x00\x00')
        await writer.drain()
        sub_data = await reader.read(1024)
        if sub_data and sub_data[0] == 0x82:
            writer.write(b'\x90\x03' + sub_data[2:4] + b'\x00')
            await writer.drain()

        while True:
            try:
                h_resp = ha_session.get(HA_URL, timeout=3)
                real_bed_temp = float(h_resp.json()['state'])
                target = current_data["kammer_soll"]
                ist_temp = current_data["kammer_ist"]
                safety_limit = current_data["bett_limit"]
                
                if real_bed_temp < safety_limit:
                    send_val, info = 20.0, f"Bett < {safety_limit}°C"
                elif ist_temp >= target:
                    send_val, info = 85.0, f"Ziel {target}°C erreicht"
                elif ist_temp <= (target - 1.0):
                    send_val, info = 20.0, f"Heize auf {target}°C"
                else:
                    send_val, info = last_val, "Hysterese aktiv"

                last_val = send_val
                icon = "🔥 EIN" if send_val > 50 else "❄️ AUS"
                conn = "🟢 ONLINE"
                
                line = f"\r{conn} | Bed:{real_bed_temp}° | Kammer Soll/Ist:{target}/{ist_temp}° | Limit:{safety_limit}° | {icon} | {info}"
                print(f"{line[:100].ljust(100)}", end="", flush=True)

                writer.write(create_packet(send_val))
                await writer.drain()
            except: pass
            await asyncio.sleep(2)
    except: pass
    finally:
        panda_connected = False
        writer.close()

async def main():
    asyncio.create_task(update_limits_from_ws())
    ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_ctx.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
    ssl_ctx.set_ciphers('DEFAULT@SECLEVEL=1') 
    server = await asyncio.start_server(handle_panda, '0.0.0.0', 8883, ssl=ssl_ctx)
    
    # Startanzeige
    print(f"\n🚀 Panda-Logic-Sync aktiv auf {HOST_IP}")
    print(f"👉 BITTE 'BIND' IN DER PANDA WEB-UI DRÜCKEN...\n")
    
    async with server: await server.serve_forever()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n🛑 System gestoppt.")
