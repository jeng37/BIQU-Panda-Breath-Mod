#!/usr/bin/env python3
import asyncio, ssl, json, time, requests, websockets
import logging

# ==========================================
# KONFIGURATION
# ==========================================
HOST_IP = "192.168.x.xxx" 
PANDA_IP = "192.168.x.xxx"
PRINTER_SN = "01P00A123456789"
ACCESS_CODE = "01P00A12"
HA_URL = "http://192.168.x.xxx:8123/api/states/sensor.your_bed_temperature_sensor"
HA_TOKEN = "Your HA Tocken"
# ==========================================

# Alles an Logging stummschalten, was neue Zeilen erzeugen könnte
logging.basicConfig(level=logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

current_limits = {"hotbedtemp": None}
panda_connected = False
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
    global current_limits
    uri = f"ws://{PANDA_IP}/ws"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=None) as websocket:
                set_printer = {"printer": {"ip": HOST_IP, "sn": PRINTER_SN, "access_code": ACCESS_CODE}}
                await websocket.send(json.dumps(set_printer))
                while True:
                    msg = await websocket.recv()
                    data = json.loads(msg)
                    if 'settings' in data and 'hotbedtemp' in data['settings']:
                        current_limits["hotbedtemp"] = float(data['settings']['hotbedtemp'])
        except: await asyncio.sleep(5)

async def handle_panda(reader, writer):
    global panda_connected
    panda_connected = True
    try:
        await reader.read(1024)
        writer.write(b'\x20\x02\x00\x00')
        await writer.drain()
        sub_data = await reader.read(1024)
        if sub_data and sub_data[0] == 0x82:
            writer.write(b'\x90\x03' + sub_data[2:4] + b'\x00')
            await writer.drain()

        last_val = 20.0
        while True:
            if current_limits["hotbedtemp"] is None:
                await asyncio.sleep(1)
                continue
            try:
                h_resp = ha_session.get(HA_URL, timeout=3)
                real_temp = float(h_resp.json()['state'])
                target = current_limits["hotbedtemp"]
                
                if real_temp < 50.0:
                    send_val, info = 20.0, "Bett < 50°C (Sicherheit)"
                elif real_temp >= target:
                    send_val, info = 85.0, f"Bett {real_temp}°C >= Soll {target}°C"
                elif real_temp <= (target - 1.0):
                    send_val, info = 20.0, f"Bett {real_temp}°C < {target-1.0}°C"
                else:
                    send_val, info = last_val, "Hysterese aktiv"

                last_val = send_val
                icon = "🔥 EIN" if send_val > 50 else "❄️ AUS"
                conn_status = f"🟢 ONLINE ({PANDA_IP})" if panda_connected else "🔴 OFFLINE"
                
                # DIE EINZIGE ZEILE: Überschreibt sich immer wieder selbst
                print(f"\r{conn_status} | HA-Bed-Sensor: {real_temp}°C | Kammer Soll: {target}°C | Relais: {icon} | {info}          ", end="", flush=True)

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
    print(f"🚀 Panda-Logic-Sync aktiv. Warte auf Verbindung...")
    async with server: await server.serve_forever()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n🛑 System gestoppt.")
