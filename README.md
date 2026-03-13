<!-- REPO_VIEWS_BADGE_START -->
![Repository Views](https://img.shields.io/badge/Repository%20Views-968-blue?style=flat-square)
<!-- REPO_VIEWS_BADGE_END -->

# BIQU Panda Breath Mod 🚀
### Panda Logic Sync v1.9.2

Intelligent control for the **BIQU Panda Breath** chamber heater.

This project emulates a **Bambu Lab-compatible printer** on a host system and enables synchronized chamber heating control for the Panda ecosystem. It currently integrates with **Home Assistant** for parts of the state handling and automation flow, but the long-term goal is to make the project work with **MQTT only**.

<img width="1839" height="912" alt="Screenshot from 2026-03-01 10-36-31" src="https://github.com/user-attachments/assets/50aab4bf-ccf9-4eea-8567-7ef40c84fd36" />

<img width="1329" height="897" alt="Screenshot from 2026-03-01 10-37-42" src="https://github.com/user-attachments/assets/89309991-4a4c-4611-bd0c-f5e7c97c90c9" />
<img width="1329" height="897" alt="Screenshot from 2026-03-01 10-37-47" src="https://github.com/user-attachments/assets/e15c096e-c885-4e7c-b7a1-fb6e755795f8" />

<img width="526" height="780" alt="Screenshot from 2026-03-01 10-35-56" src="https://github.com/user-attachments/assets/cb2ca112-8e07-41d9-a7cc-d286a7d684fa" />

## Features

- Immediate chamber heating in all supported modes
- Lock / unlock safety logic
- Stable MQTT synchronization
- Slicer priority mode support
- Dry mode support
- Live terminal monitoring
- TLS-based Panda connection support
- Optional desktop GUI for monitoring and control

---

## How It Works

The project simulates a printer that the Panda device can talk to using the expected protocol.

Typical data flow in the current setup:

**Moonraker → Home Assistant → Panda Logic Sync → Panda device / Panda Touch**

This allows the Panda hardware to behave as if it were connected to a supported printer while the host system handles the control logic.

---

## Current Status

### Home Assistant is still required at the moment

Although the project already uses **MQTT** for communication, the current implementation is still **partly dependent on Home Assistant**.

That means:

- Some states and automation logic still come from the Home Assistant environment
- The system is not yet fully structured as a standalone MQTT-only solution
- Home Assistant still provides parts of the integration layer

### Planned change

This will change in a later version.

The goal is to refactor the project so that it no longer depends on Home Assistant and only requires:

- **MQTT**
- the Panda hardware
- the host application / scripts

Target outcome:

- no Home Assistant dependency
- direct MQTT-based communication
- easier integration into other environments
- simpler deployment and maintenance

---

## Heating Logic

### Immediate Heating

In all active modes, chamber heating can start immediately when the measured chamber temperature is below the configured target minus hysteresis.

Supported modes include:

- Auto
- Manual
- Slicer Priority
- Dry

Bed temperature is no longer used as a startup blocker.

### Bed Temperature Handling

Bed temperature is currently used for:

- safety limiting
- filter fan activation

If the configured bed limit is reached, the system can report that state, but chamber control logic remains active unless another safety condition stops it.

---

## Lock System

The **Heizung Stop** action activates a global lock state.

Typical lock behavior:

- heating output disabled
- work state reset
- mode reset
- set temperature reset
- selected MQTT commands ignored until unlocked

Unlocking is performed through the dedicated **Unlock** command.

---

## Slicer Integration

The project can read chamber-related values from slicer-generated G-code, for example via Moonraker.

Typical commands:

```gcode
M191 S42
M141 S42
```

When **Slicer Priority Mode** is enabled, the detected slicer value can be used as the chamber target.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/jeng37/BIQU-Panda-Breath-Mod.git
cd BIQU-Panda-Breath-Mod
```

### 2. Install system packages

```bash
sudo apt update
sudo apt install python3 python3-pip openssl policykit-1 -y
```

### 3. Install Python dependencies

For the main logic:

```bash
pip install asyncio websockets requests paho-mqtt
```

For the desktop GUI:

```bash
pip install PySide6 paho-mqtt
```

Or install everything together:

```bash
pip install websockets requests paho-mqtt PySide6
```

Notes:

- `asyncio` is part of the Python standard library in modern Python versions, so it usually does **not** need to be installed separately
- `pkexec` is **not** a pip package; it is provided by the operating system

### 4. Generate certificates

TLS certificates are required for the Panda connection.

```bash
chmod +x cert_gen.sh
./cert_gen.sh
```

Or generate them manually:

```bash
openssl req -x509 -newkey rsa:4096 \
  -keyout key.pem \
  -out cert.pem \
  -sha256 -days 3650 -nodes \
  -subj "/C=DE/ST=Panda/L=Panda/O=Bambu/OU=Printer/CN=bambulab.local"
```

---

## Configuration

Edit the main script and adjust the configuration to your own environment.

Example:

```bash
nano Panda.py
```

Configure values such as:

- MQTT broker settings
- MQTT username / password
- Panda device settings
- printer serial number
- access code
- host address
- Home Assistant token and related endpoints if you use the current HA-based setup

Do **not** publish private IP addresses, usernames, passwords, access tokens, serial numbers, or access codes in your public repository.

---

## Start the Main Script

```bash
sudo python3 Panda.py
```

Root privileges may be required depending on your runtime setup and port usage.

---

## Binding Process

Open the Panda web interface on your device and enter your local values for:

- printer serial number
- access code
- host IP / hostname

Do not use automatic scan if your setup expects manual binding.

Once the interface switches to **Unbind**, the connection is active.

---

## Live Terminal Output

Example status line:

```text
🟢 READY | Bed:61° | Kammer:50/43° | Heiz:AN | Fan:ON | Heating... | NORMAL:0°
```

Field overview:

| Field | Meaning |
|---|---|
| Bed | Bed temperature |
| Kammer | Target / current chamber temperature |
| Heiz | Heater relay state |
| Fan | Filter fan state |
| NORMAL / SL-PRIO | Active operating mode |

---

## Home Assistant Entities

The current version can expose or use entities such as the following through Home Assistant integration.

### Numbers

- Chamber target
- Bed limit
- Filter temperature
- Dry temperature
- Dry time

### Switches

- Panda power
- Slicer priority mode

### Buttons

- Auto
- Manual
- Drying
- Heater stop
- Unlock

### Sensors

- Chamber actual temperature
- Slicer target
- Panda status
- Panda mode
- Lock status
- Version

---

## Panda Control GUI

A desktop GUI for controlling and monitoring the **Panda Breath Mod** over **MQTT**.

It is written in **Python** using **PySide6** and provides a direct interface for status display, mode switching, and sending setpoints.

<img width="1258" height="962" alt="Screenshot from 2026-03-12 11-20-16" src="https://github.com/user-attachments/assets/b7ac4fcc-2a2f-4dbd-beac-c5f8c6ad25ff" />
<img width="1258" height="962" alt="Screenshot from 2026-03-12 11-21-00" src="https://github.com/user-attachments/assets/2d905b8f-01ef-41b2-9095-e95e2735425c" />

### GUI Features

- Start and stop the main script from the GUI
- Live status display for:
  - current state
  - bed temperature
  - chamber target / actual temperature
  - heater state
  - fan state
  - lock state
  - Panda power
  - version
  - slicer target temperature
- MQTT-based control for:
  - Auto mode
  - Manual mode
  - Dry mode
  - Heater stop
  - Unlock
  - Slicer mode on / off
  - Panda power on / off
- Send values for:
  - bed limit
  - chamber target
  - filter fan start temperature
  - dryer temperature
  - dryer time
- Live log output from the started Python script
- Visible MQTT connection status in the GUI

### GUI Start

```bash
python3 PandaGui.py
```

By default, the GUI is set up to launch a local Panda script, but this path can be changed through the **Select Script** action in the interface.

### GUI Notes

- The GUI already communicates through MQTT
- The larger project logic is still partially Home Assistant dependent at this time
- The long-term goal is to make the full stack work with MQTT only
- Private broker addresses, credentials, and local network details should not be committed to GitHub

---

## Safety Behavior

| Situation | Result |
|---|---|
| Home Assistant sensor failure | Heating off |
| Lock active | Everything off |
| Work mode = 0 | Standby |
| Panda power off | Forced shutdown |

---

## Roadmap

- Remove the remaining Home Assistant dependency
- Move to a pure MQTT-only architecture
- Move MQTT settings into a config file
- Improve error handling and logging
- Clean separation between GUI, MQTT client, and core logic
- Package the application more cleanly for Linux deployment

---

## License

No license has been defined yet.

