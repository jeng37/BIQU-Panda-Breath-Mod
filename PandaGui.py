#!/usr/bin/env python3
import sys
import os
import re
import time
import json
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from PySide6.QtCore import QProcess, Qt, Signal
from PySide6.QtGui import QAction, QTextCursor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)

STATUS_RE = re.compile(
    r"(?P<icon>[🟢🟡🔴⚠️])\s*(?P<state>[A-Z ]+)\s*\|\s*"
    r"Bed:(?P<bed>[\d.]+)°\s*\|\s*"
    r"Kammer:(?P<kammer_soll>[\d.]+)/(?P<kammer_ist>[\d.]+)°\s*\|\s*"
    r"Heiz:(?P<heiz>AN|AUS)\s*\|\s*"
    r"Fan:(?P<fan>ON|OFF)\s*\|\s*"
    r"(?P<info>.*?)\s*\|\s*"
    r"(?P<mode>NORMAL|SL-PRIO):(?P<mode_temp>[\d.]+)°"
)
ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

CONFIG_FILE_NAME = "panda_config.json"

DEFAULT_CONFIG = {
    "DEBUG": False,
    "DEBUG_TO_FILE": True,
    "HYSTERESE": 1.5,
    "MIN_SWITCH_TIME": 10,
    "MQTT_BROKER": "192.168.x.xxx",
    "MQTT_USER": "xxxxxx",
    "MQTT_PASS": "xxxxxx",
    "MQTT_TOPIC_PREFIX": "panda_breath_mod",
    "HOST_IP": "192.168.x.xxx",
    "PANDA_IP": "192.168.x.xxx",
    "PRINTER_SN": "01P00A123456789",
    "ACCESS_CODE": "01P00A12",
    "HA_BED_TEMPERATURE_ENTITY": "sensor.ks1c_bed_temperature",
    "HA_BASE_URL": "http://192.168.x.xxx:8123",
    "HA_TOKEN": "",
    "PRINTER_IP": "192.168.x.xxx"
}

CONFIG_SCHEMA = [
    ("DEBUG", "bool", "Debug-Ausgabe im Terminal aktivieren"),
    ("DEBUG_TO_FILE", "bool", "Zusätzliches Logging in panda_debug.log schreiben"),
    ("HYSTERESE", "float", "Temperatur-Hysterese"),
    ("MIN_SWITCH_TIME", "int", "Mindestpause zwischen Schaltvorgängen in Sekunden"),
    ("MQTT_BROKER", "str", "MQTT Broker IP oder Hostname"),
    ("MQTT_USER", "str", "MQTT Benutzername"),
    ("MQTT_PASS", "str", "MQTT Passwort"),
    ("MQTT_TOPIC_PREFIX", "str", "MQTT Topic Prefix"),
    ("HOST_IP", "str", "IP dieses PCs. Diese IP muss auch in der Panda UI bei Printer IP eingetragen sein."),
    ("PANDA_IP", "str", "IP vom Panda Touch"),
    ("PRINTER_SN", "str", "Drucker Seriennummer"),
    ("ACCESS_CODE", "str", "Drucker Access Code"),
    ("HA_BED_TEMPERATURE_ENTITY", "str", "Home Assistant Bett-Temperatur Entity"),
    ("HA_BASE_URL", "str", "Home Assistant Basis-URL"),
    ("HA_TOKEN", "str", "Home Assistant Long-Lived Token"),
    ("PRINTER_IP", "str", "IP vom Drucker bzw. Moonraker"),
]

CONFIG_COMMENTS = {
    "DEBUG": "True zeigt detaillierte MQTT-Befehle im Terminal, False hält die Ausgabe sauber.",
    "DEBUG_TO_FILE": "True speichert Verbindungen, Fehler und Sync-Ereignisse in panda_debug.log.",
    "HYSTERESE": "Temperatur muss um diesen Wert unter Soll fallen, bevor erneut geheizt wird.",
    "MIN_SWITCH_TIME": "Mindestpause in Sekunden zwischen zwei Schaltvorgängen zum Schutz der Hardware.",
    "MQTT_BROKER": "IP-Adresse oder Hostname deines MQTT-Brokers.",
    "MQTT_USER": "MQTT-Benutzername.",
    "MQTT_PASS": "MQTT-Passwort.",
    "MQTT_TOPIC_PREFIX": "Basis-Präfix für alle MQTT-Topics, z. B. panda_breath_mod.",
    "HOST_IP": "IP-Adresse dieses PCs. Diese IP muss in der Panda UI als Printer IP eingetragen sein.",
    "PANDA_IP": "IP-Adresse des Panda Touch im Netzwerk.",
    "PRINTER_SN": "Seriennummer des Druckers.",
    "ACCESS_CODE": "Access Code des Druckers für die Verbindung.",
    "HA_BED_TEMPERATURE_ENTITY": "Home Assistant Entity-ID für die Bett-Temperatur.",
    "HA_BASE_URL": "Basis-URL deiner Home Assistant Instanz, z. B. http://homeassistant.local:8123.",
    "HA_TOKEN": "Home Assistant Long-Lived Access Token.",
    "PRINTER_IP": "IP-Adresse des Druckers bzw. Moonraker-Hosts.",
}


def _build_commented_config(config: dict) -> dict:
    commented = {}
    for key, _field_type, _description in CONFIG_SCHEMA:
        comment = CONFIG_COMMENTS.get(key)
        if comment:
            commented[f"_comment_{key.lower()}"] = comment
        commented[key] = config.get(key, DEFAULT_CONFIG.get(key))
    return commented


def get_default_config_path(script_path: str | None = None) -> Path:
    if script_path:
        return Path(script_path).resolve().parent / CONFIG_FILE_NAME
    return Path.home() / "Panda" / CONFIG_FILE_NAME


def ensure_config(config_path: Path) -> dict:
    config = dict(DEFAULT_CONFIG)
    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config.update(loaded)
        except Exception:
            pass
    else:
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return config


def save_config_file(config_path: Path, config: dict):
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()



class ValueLabel(QLabel):
    def __init__(self, title: str, value: str = "-"):
        super().__init__()
        self.title = title
        self.setTextFormat(Qt.RichText)
        self.setAlignment(Qt.AlignCenter)
        self.set_value(value)
        self.setStyleSheet(
            """
            QLabel {
                border: 1px solid #555;
                border-radius: 10px;
                padding: 12px;
                font-size: 16px;
                background: #202020;
                color: #f0f0f0;
            }
            """
        )

    def set_value(self, value: str):
        self.setText(
            f"<div style='font-size:12px;color:#bbbbbb'>{self.title}</div>"
            f"<div style='font-size:22px;font-weight:700'>{value}</div>"
        )


class ConfigDialog(QDialog):
    def __init__(self, config_path: str, parent=None):
        super().__init__(parent)
        self.config_path = Path(config_path)
        self.setWindowTitle("Panda Konfiguration")
        self.resize(900, 760)

        self.widgets = {}
        self.config = ensure_config(self.config_path)

        root = QVBoxLayout(self)

        info = QLabel(
            "Backend und GUI verwenden dieselbe JSON-Konfiguration. "
            "Wichtig: HOST_IP ist die IP dieses PCs und muss in der Panda UI bei Printer IP eingetragen sein."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#ddd;")
        root.addWidget(info)

        self.path_label = QLabel(str(self.config_path))
        self.path_label.setStyleSheet("color:#9ecbff;")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.path_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background:#202020;")
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setSpacing(12)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save_config)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.build_form()

    def build_form(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.widgets.clear()

        for key, field_type, description in CONFIG_SCHEMA:
            box = QGroupBox(key)
            box.setStyleSheet(
                "QGroupBox {color:#f0f0f0; font-weight:700; border:1px solid #555; border-radius:8px; margin-top:8px;}"
                "QGroupBox::title {subcontrol-origin: margin; left: 10px; padding: 0 4px 0 4px;}"
            )
            vbox = QVBoxLayout(box)

            desc = QLabel(description)
            desc.setWordWrap(True)
            desc.setStyleSheet("color:#bbbbbb; font-size:12px;")
            vbox.addWidget(desc)

            widget = self._make_editor(field_type, self.config.get(key, DEFAULT_CONFIG.get(key)))
            vbox.addWidget(widget)
            self.widgets[key] = (field_type, widget)

            current = QLabel(f"Aktueller Wert: {self.config.get(key)!r}")
            current.setStyleSheet("color:#8cc6ff; font-size:12px;")
            vbox.addWidget(current)

            self.content_layout.addWidget(box)

        self.content_layout.addStretch(1)

    def _make_editor(self, field_type, value):
        if field_type == "bool":
            widget = QCheckBox("Aktiviert")
            widget.setChecked(bool(value))
            widget.setStyleSheet("color:#f0f0f0;")
            return widget
        if field_type == "int":
            widget = NoWheelSpinBox()
            widget.setRange(-999999999, 999999999)
            widget.setValue(int(value))
            return widget
        if field_type == "float":
            widget = NoWheelDoubleSpinBox()
            widget.setRange(-999999999, 999999999)
            widget.setDecimals(3)
            widget.setSingleStep(0.1)
            widget.setValue(float(value))
            return widget

        widget = QLineEdit(str(value))
        return widget

    def _widget_value(self, field_type, widget):
        if field_type == "bool":
            return widget.isChecked()
        if field_type == "int":
            return int(widget.value())
        if field_type == "float":
            return float(widget.value())
        return widget.text()

    def save_config(self):
        try:
            new_config = dict(self.config)
            for key, field_type, _description in CONFIG_SCHEMA:
                widget_type, widget = self.widgets[key]
                new_config[key] = self._widget_value(widget_type, widget)
            save_config_file(self.config_path, _build_commented_config(new_config))
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Konfiguration konnte nicht gespeichert werden:\n{e}")
            return

        QMessageBox.information(
            self,
            "Gespeichert",
            "Die Konfiguration wurde in der JSON-Datei gespeichert.\n"
            "Backend und GUI verwenden jetzt dieselbe Konfiguration.\n"
            "Wichtig: In der Panda UI muss Printer IP = HOST_IP sein."
        )
        self.accept()


class PandaControlWindow(QMainWindow):
    mqtt_message_signal = Signal(str, str)
    mqtt_connect_signal = Signal()
    mqtt_disconnect_signal = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Panda Control GUI")
        self.resize(1250, 900)
        icon_set = False
        for icon_path in [
            str(Path.home() / "Panda" / "panda_gui.png"),
            str(Path.home() / "Panda" / "panda_gui.ico"),
            str(Path.home() / "Panda" / "icon.png"),
            str(Path.home() / "Panda" / "icon.ico"),
        ]:
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                icon_set = True
                break
        if not icon_set:
            theme_icon = QIcon.fromTheme("applications-engineering")
            if not theme_icon.isNull():
                self.setWindowIcon(theme_icon)

        self.process = None
        self.script_path = str(Path.home() / "Panda" / "Panda-1.py")
        self.working_dir = str(Path(self.script_path).parent)
        self.config_path = str(get_default_config_path(self.script_path))
        self.runtime_config = ensure_config(Path(self.config_path))
        self.state_cache = {}
        self.mqtt_connected = False
        self._updating_from_mqtt = False
        self.pending_updates = {}
        self.pending_timeout = 8.0
        self.display_cache = {}

        self._build_ui()
        self._connect_actions()

        self.mqtt_message_signal.connect(self._sync_from_mqtt)
        self.mqtt_connect_signal.connect(self._handle_mqtt_connected)
        self.mqtt_disconnect_signal.connect(self._handle_mqtt_disconnected)

        self._setup_mqtt()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top_bar = QHBoxLayout()
        self.script_edit = QLineEdit(self.script_path)
        self.script_edit.setPlaceholderText("Pfad zu deinem Hauptskript")
        self.browse_btn = QPushButton("Skript wählen")
        self.config_btn = QPushButton("Config")
        top_bar.addWidget(QLabel("Skript:"))
        top_bar.addWidget(self.script_edit, 1)
        top_bar.addWidget(self.config_btn)
        top_bar.addWidget(self.browse_btn)
        root.addLayout(top_bar)

        controls = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.clear_btn = QPushButton("Log leeren")

        self.status_badge = QLabel("Gestoppt")
        self.status_badge.setAlignment(Qt.AlignCenter)
        self.status_badge.setStyleSheet(
            "background:#5a1f1f;color:white;padding:8px 14px;border-radius:12px;font-weight:700;"
        )

        self.mqtt_badge = QLabel("MQTT getrennt")
        self.mqtt_badge.setAlignment(Qt.AlignCenter)
        self.mqtt_badge.setStyleSheet(
            "background:#5a1f1f;color:white;padding:8px 14px;border-radius:12px;font-weight:700;"
        )

        controls.addWidget(self.start_btn)
        controls.addWidget(self.stop_btn)
        controls.addWidget(self.clear_btn)
        controls.addStretch(1)
        controls.addWidget(self.mqtt_badge)
        controls.addWidget(self.status_badge)
        root.addLayout(controls)

        status_box = QGroupBox("Live-Status")
        status_grid = QGridLayout(status_box)
        self.lbl_state = ValueLabel("Status", "-")
        self.lbl_bed = ValueLabel("Bed", "-")
        self.lbl_kammer = ValueLabel("Kammer", "-")
        self.lbl_heiz = ValueLabel("Heizung", "-")
        self.lbl_fan = ValueLabel("Fan", "-")
        self.lbl_info = ValueLabel("Info", "-")
        self.lbl_mode = ValueLabel("Modus", "-")
        self.lbl_last = ValueLabel("Aktiver Modus", "-")
        self.lbl_lock = ValueLabel("Lock Status", "-")
        self.lbl_power = ValueLabel("Panda Power", "-")
        self.lbl_version = ValueLabel("Version", "-")
        self.lbl_slicer_target = ValueLabel("Slicer Target Temp", "-")

        status_grid.addWidget(self.lbl_state, 0, 0)
        status_grid.addWidget(self.lbl_bed, 0, 1)
        status_grid.addWidget(self.lbl_kammer, 0, 2)
        status_grid.addWidget(self.lbl_heiz, 0, 3)
        status_grid.addWidget(self.lbl_fan, 1, 0)
        status_grid.addWidget(self.lbl_info, 1, 1)
        status_grid.addWidget(self.lbl_mode, 1, 2)
        status_grid.addWidget(self.lbl_power, 1, 3)
        status_grid.addWidget(self.lbl_lock, 2, 0)
        status_grid.addWidget(self.lbl_version, 2, 1)
        status_grid.addWidget(self.lbl_slicer_target, 2, 2)
        status_grid.addWidget(self.lbl_last, 3, 0, 1, 4)
        root.addWidget(status_box)

        action_box = QGroupBox("Steuerung")
        action_grid = QGridLayout(action_box)

        self.btn_auto = QPushButton("Auto")
        self.btn_manual = QPushButton("Manuell")
        self.btn_dry = QPushButton("Dry")
        self.mode_buttons = {
            "Automatik": self.btn_auto,
            "Manuell": self.btn_manual,
            "Dry": self.btn_dry,
        }

        self.btn_stop_heizen = QPushButton("Stop Heizen")
        self.btn_unlock = QPushButton("Unlock")
        self.btn_slicer = QPushButton("Slicer")
        self.btn_power = QPushButton("Panda Power: AUS")

        self.spin_bett_limit = QDoubleSpinBox()
        self.spin_bett_limit.setRange(1, 120)
        self.spin_bett_limit.setSuffix(" °C")
        self.spin_bett_limit.setDecimals(1)

        self.spin_kammer_soll = QDoubleSpinBox()
        self.spin_kammer_soll.setRange(1, 120)
        self.spin_kammer_soll.setSuffix(" °C")
        self.spin_kammer_soll.setDecimals(1)

        self.spin_filter = QDoubleSpinBox()
        self.spin_filter.setRange(1, 120)
        self.spin_filter.setSuffix(" °C")
        self.spin_filter.setDecimals(1)

        self.spin_dry_temp = QSpinBox()
        self.spin_dry_temp.setRange(1, 120)
        self.spin_dry_temp.setSuffix(" °C")

        self.spin_dry_time = QSpinBox()
        self.spin_dry_time.setRange(1, 240)
        self.spin_dry_time.setSuffix(" h")

        self.btn_set_bett_limit = QPushButton("Bett Limit senden")
        self.btn_set_kammer_soll = QPushButton("Kammer Soll senden")
        self.btn_set_filter = QPushButton("Filter Fan Start senden")
        self.btn_set_dry_temp = QPushButton("Dryer Temp senden")
        self.btn_set_dry_time = QPushButton("Dryer Time senden")

        action_grid.addWidget(self.btn_auto, 0, 0)
        action_grid.addWidget(self.btn_manual, 0, 1)
        action_grid.addWidget(self.btn_slicer, 0, 2)
        action_grid.addWidget(self.btn_dry, 0, 3)

        action_grid.addWidget(self.btn_stop_heizen, 1, 0, 1, 2)
        action_grid.addWidget(self.btn_unlock, 1, 2)
        action_grid.addWidget(self.btn_power, 1, 3)

        action_grid.addWidget(QLabel("Bett Limit"), 2, 0)
        action_grid.addWidget(self.spin_bett_limit, 2, 1)
        action_grid.addWidget(self.btn_set_bett_limit, 2, 2, 1, 2)

        action_grid.addWidget(QLabel("Kammer Soll"), 3, 0)
        action_grid.addWidget(self.spin_kammer_soll, 3, 1)
        action_grid.addWidget(self.btn_set_kammer_soll, 3, 2, 1, 2)

        action_grid.addWidget(QLabel("Filter Fan Start"), 4, 0)
        action_grid.addWidget(self.spin_filter, 4, 1)
        action_grid.addWidget(self.btn_set_filter, 4, 2, 1, 2)

        action_grid.addWidget(QLabel("Dryer Temp"), 5, 0)
        action_grid.addWidget(self.spin_dry_temp, 5, 1)
        action_grid.addWidget(self.btn_set_dry_temp, 5, 2, 1, 2)

        action_grid.addWidget(QLabel("Dryer Time"), 6, 0)
        action_grid.addWidget(self.spin_dry_time, 6, 1)
        action_grid.addWidget(self.btn_set_dry_time, 6, 2, 1, 2)

        root.addWidget(action_box)
        self._set_mode_button_styles()
        self._set_toggle_button(self.btn_slicer, False, "Slicer: EIN", "Slicer: AUS")
        self._set_toggle_button(self.btn_power, False, "Panda Power: EIN", "Panda Power: AUS")

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.log_output.setStyleSheet(
            "background:#111;color:#ddd;font-family:monospace;font-size:13px;border-radius:10px;padding:8px;"
        )
        root.addWidget(self.log_output, 1)

        menu = self.menuBar().addMenu("Datei")
        choose_action = QAction("Skript wählen", self)
        choose_action.triggered.connect(self.choose_script)
        menu.addAction(choose_action)

    def _connect_actions(self):
        self.browse_btn.clicked.connect(self.choose_script)
        self.config_btn.clicked.connect(self.open_config_dialog)
        self.start_btn.clicked.connect(self.start_process)
        self.stop_btn.clicked.connect(self.stop_process)
        self.clear_btn.clicked.connect(self.log_output.clear)

        self.btn_auto.clicked.connect(lambda: self.publish("auto/set", "1"))
        self.btn_manual.clicked.connect(lambda: self.publish("manual/set", "PRESS"))
        self.btn_dry.clicked.connect(lambda: self.publish("drying/set", "1"))
        self.btn_stop_heizen.clicked.connect(lambda: self.publish("heizung_stop/set", "PRESS"))
        self.btn_unlock.clicked.connect(lambda: self.publish("unlock/set", "PRESS"))
        self.btn_slicer.clicked.connect(self.toggle_slicer_button)
        self.btn_power.clicked.connect(self.toggle_power_button)

        self.btn_set_bett_limit.clicked.connect(lambda: self.send_numeric("limit", self.spin_bett_limit.value()))
        self.btn_set_kammer_soll.clicked.connect(lambda: self.send_numeric("soll", self.spin_kammer_soll.value()))
        self.btn_set_filter.clicked.connect(lambda: self.send_numeric("filtertemp", self.spin_filter.value()))
        self.btn_set_dry_temp.clicked.connect(lambda: self.send_numeric("dry_temp", self.spin_dry_temp.value()))
        self.btn_set_dry_time.clicked.connect(lambda: self.send_numeric("dry_time", self.spin_dry_time.value()))

    def open_config_dialog(self):
        script = self.script_edit.text().strip()
        if not script or not os.path.exists(script):
            QMessageBox.warning(self, "Fehler", "Bitte zuerst ein gültiges Panda-Skript auswählen.")
            return

        self.config_path = str(get_default_config_path(script))
        dlg = ConfigDialog(self.config_path, self)
        if dlg.exec():
            self.runtime_config = ensure_config(Path(self.config_path))
            self.append_log(f"[GUI] Konfiguration gespeichert in: {self.config_path}\n")
            self._reload_mqtt_from_config()

    def _set_mode_button_styles(self, active_mode=None):
        active_style = (
            "QPushButton {"
            "background:#1f6b3a;"
            "color:white;"
            "font-weight:700;"
            "border:1px solid #2f8b4a;"
            "border-radius:8px;"
            "padding:8px 12px;"
            "min-height:42px;"
            "text-align:center;"
            "}"
        )
        normal_style = (
            "QPushButton {"
            "background:#2b2b2b;"
            "color:#f0f0f0;"
            "border:1px solid #555;"
            "border-radius:8px;"
            "padding:8px 12px;"
            "min-height:42px;"
            "text-align:center;"
            "}"
        )
        for mode_name, button in self.mode_buttons.items():
            button.setStyleSheet(active_style if mode_name == active_mode else normal_style)

    def _set_toggle_button(self, button: QPushButton, is_on: bool, on_text: str, off_text: str):
        if is_on:
            button.setText(on_text)
            button.setStyleSheet(
                "QPushButton {background:#1f6b3a;color:white;font-weight:700;"
                "border:1px solid #2f8b4a;border-radius:8px;padding:8px 12px;}"
            )
        else:
            button.setText(off_text)
            button.setStyleSheet(
                "QPushButton {background:#7a1f1f;color:white;font-weight:700;"
                "border:1px solid #a33;border-radius:8px;padding:8px 12px;}"
            )

    def _setup_mqtt(self):
        cfg = ensure_config(Path(self.config_path))
        self.runtime_config = cfg
        self.topic_prefix = str(cfg.get("MQTT_TOPIC_PREFIX", DEFAULT_CONFIG["MQTT_TOPIC_PREFIX"]))
        self.mqtt_broker = str(cfg.get("MQTT_BROKER", DEFAULT_CONFIG["MQTT_BROKER"]))
        self.mqtt_port = int(cfg.get("MQTT_PORT", 1883))
        self.mqtt_user = str(cfg.get("MQTT_USER", DEFAULT_CONFIG["MQTT_USER"]))
        self.mqtt_pass = str(cfg.get("MQTT_PASS", DEFAULT_CONFIG["MQTT_PASS"]))

        self.mqtt_client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id="PandaControlGUI"
        )
        self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_pass)
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        try:
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
        except Exception as e:
            self.append_log(f"[GUI] MQTT Fehler beim Verbinden: {e}\n")

    def _reload_mqtt_from_config(self):
        try:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        except Exception:
            pass
        self._setup_mqtt()

    def on_mqtt_connect(self, client, userdata, flags, reason_code, properties=None):
        client.subscribe(f"{self.topic_prefix}/#")
        self.mqtt_connect_signal.emit()

    def on_mqtt_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.mqtt_disconnect_signal.emit()

    def on_mqtt_message(self, client, userdata, msg):
        value = msg.payload.decode(errors="replace").strip()
        topic = msg.topic
        self.state_cache[topic] = value
        self.mqtt_message_signal.emit(topic, value)

    def _handle_mqtt_connected(self):
        self.mqtt_connected = True
        self.mqtt_badge.setText("MQTT verbunden")
        self.mqtt_badge.setStyleSheet(
            "background:#1f6b3a;color:white;padding:8px 14px;border-radius:12px;font-weight:700;"
        )
        self.append_log("[GUI] MQTT verbunden\n")

    def _handle_mqtt_disconnected(self):
        self.mqtt_connected = False
        self.mqtt_badge.setText("MQTT getrennt")
        self.mqtt_badge.setStyleSheet(
            "background:#5a1f1f;color:white;padding:8px 14px;border-radius:12px;font-weight:700;"
        )
        self.append_log("[GUI] MQTT getrennt\n")

    def _topic(self, suffix: str) -> str:
        return f"{self.topic_prefix}/{suffix}"

    def _now(self) -> float:
        return time.time()

    def _set_pending(self, field_name: str, value):
        self.pending_updates[field_name] = {
            "value": float(value),
            "until": self._now() + self.pending_timeout,
        }

    def _pending_active(self, field_name: str) -> bool:
        item = self.pending_updates.get(field_name)
        return bool(item and self._now() < item["until"])

    def _clear_pending_if_match(self, field_name: str, value):
        item = self.pending_updates.get(field_name)
        if not item:
            return
        try:
            if abs(float(value) - float(item["value"])) < 0.11:
                self.pending_updates.pop(field_name, None)
        except Exception:
            pass

    def _can_apply_to_widget(self, field_name: str, widget, incoming_value) -> bool:
        if widget.hasFocus():
            return False
        if self._pending_active(field_name):
            try:
                pending_val = float(self.pending_updates[field_name]["value"])
                if abs(float(incoming_value) - pending_val) < 0.11:
                    self.pending_updates.pop(field_name, None)
                    return True
            except Exception:
                pass
            return False
        return True

    def _fmt_temp_text(self, value) -> str:
        try:
            f = float(str(value).replace("°C", "").replace("°", "").strip())
            if abs(f - round(f)) < 0.01:
                return f"{int(round(f))}°C"
            return f"{f:.1f}°C"
        except Exception:
            s = str(value).strip()
            return s if s.endswith("°C") else f"{s}°C"

    def _fmt_temp_plain(self, value) -> str:
        try:
            f = float(str(value).replace("°C", "").replace("°", "").strip())
            if abs(f - round(f)) < 0.01:
                return str(int(round(f)))
            return f"{f:.1f}"
        except Exception:
            return str(value).replace("°C", "").replace("°", "").strip()

    def _set_value_label(self, label: ValueLabel, cache_key: str, value: str):
        value = str(value)
        if self.display_cache.get(cache_key) == value:
            return
        self.display_cache[cache_key] = value
        label.set_value(value)

    def _set_spin_value_if_changed(self, widget, value):
        try:
            current = float(widget.value())
            incoming = float(value)
            if abs(current - incoming) < 0.01:
                return
        except Exception:
            pass
        old = widget.blockSignals(True)
        try:
            widget.setValue(value)
        finally:
            widget.blockSignals(old)

    def _update_kammer_label(self, soll=None, ist=None):
        if soll is None:
            soll = self.state_cache.get(self._topic("soll"), "0")
        if ist is None:
            ist = self.state_cache.get(self._topic("ist"), "0")
        left = self._fmt_temp_text(soll)
        right = self._fmt_temp_text(ist)
        self._set_value_label(self.lbl_kammer, "lbl_kammer", f"{left} / {right}")

    def send_numeric(self, name: str, value):
        if name == "limit":
            self._set_pending("limit", value)
            self.state_cache[self._topic("limit")] = self._fmt_temp_plain(value)
        elif name == "soll":
            self._set_pending("soll", value)
            self.state_cache[self._topic("soll")] = self._fmt_temp_plain(value)
            self._update_kammer_label(soll=self._fmt_temp_plain(value))
        elif name == "filtertemp":
            self._set_pending("filtertemp", value)
            self.state_cache[self._topic("filtertemp")] = self._fmt_temp_plain(value)
        elif name == "dry_temp":
            self._set_pending("dry_temp", value)
            self.state_cache[self._topic("dry_temp")] = f"{int(value)}"
        elif name == "dry_time":
            self._set_pending("dry_time", value)
            self.state_cache[self._topic("dry_time")] = f"{int(value)}"

        self.publish(f"{name}/set", value)

    def _sync_from_mqtt(self, topic: str, value: str):
        self._updating_from_mqtt = True
        try:
            if topic.endswith("/status"):
                self._set_value_label(self.lbl_info, "lbl_info", value)

            elif topic.endswith("/panda_modus"):
                self._set_value_label(self.lbl_mode, "lbl_mode", value)
                self._set_mode_button_styles(value)
                active_mode = "Dryer" if value == "Dry" else value
                self._set_value_label(self.lbl_last, "lbl_last", f"READY  Aktiver Modus: {active_mode}")

            elif topic.endswith("/lock_status"):
                self._set_value_label(self.lbl_lock, "lbl_lock", value)

            elif topic.endswith("/panda_power"):
                self._set_value_label(self.lbl_power, "lbl_power", value)
                self._set_toggle_button(self.btn_power, value.upper() == "ON", "Panda Power: EIN", "Panda Power: AUS")

            elif topic.endswith("/version"):
                self._set_value_label(self.lbl_version, "lbl_version", value)

            elif topic.endswith("/slicer_target_temp"):
                self._set_value_label(self.lbl_slicer_target, "lbl_slicer_target", f"{self._fmt_temp_text(value)}")

            elif topic.endswith("/slicer_priority_mode"):
                self._set_toggle_button(self.btn_slicer, value.upper() == "ON", "Slicer: EIN", "Slicer: AUS")

            elif topic.endswith("/limit"):
                self._clear_pending_if_match("limit", value)
                if self._can_apply_to_widget("limit", self.spin_bett_limit, value):
                    self._set_spin_value_if_changed(self.spin_bett_limit, float(value or 0))

            elif topic.endswith("/soll"):
                self._clear_pending_if_match("soll", value)
                if self._can_apply_to_widget("soll", self.spin_kammer_soll, value):
                    self._set_spin_value_if_changed(self.spin_kammer_soll, float(value or 0))
                self._update_kammer_label(soll=value)

            elif topic.endswith("/ist"):
                self._update_kammer_label(ist=value)

            elif topic.endswith("/filtertemp"):
                self._clear_pending_if_match("filtertemp", value)
                if self._can_apply_to_widget("filtertemp", self.spin_filter, value):
                    self._set_spin_value_if_changed(self.spin_filter, float(value or 0))

            elif topic.endswith("/dry_temp"):
                self._clear_pending_if_match("dry_temp", value)
                if self._can_apply_to_widget("dry_temp", self.spin_dry_temp, value):
                    self._set_spin_value_if_changed(self.spin_dry_temp, int(float(value or 0)))

            elif topic.endswith("/dry_time"):
                self._clear_pending_if_match("dry_time", value)
                if self._can_apply_to_widget("dry_time", self.spin_dry_time, value):
                    self._set_spin_value_if_changed(self.spin_dry_time, int(float(value or 0)))

            elif topic.endswith("/fan"):
                self._set_value_label(self.lbl_fan, "lbl_fan", value)

        except Exception as e:
            self.append_log(f"[GUI] MQTT-Sync-Fehler: {e}\n")
        finally:
            self._updating_from_mqtt = False

    def publish(self, suffix: str, payload):
        if not self.mqtt_connected:
            QMessageBox.warning(self, "MQTT", "MQTT ist nicht verbunden.")
            return

        topic = self._topic(suffix)
        if isinstance(payload, float):
            value = str(int(payload)) if payload.is_integer() else f"{payload:.1f}"
        else:
            value = str(payload)

        self.mqtt_client.publish(topic, value, retain=False)
        self.append_log(f"[GUI->MQTT] {topic} = {value}\n")

    def toggle_slicer_button(self):
        current = self.state_cache.get(self._topic("slicer_priority_mode"), "OFF").upper() == "ON"
        self.publish("slicer_priority_mode/set", "OFF" if current else "ON")

    def toggle_power_button(self):
        current = self.state_cache.get(self._topic("panda_power"), "OFF").upper() == "ON"
        self.publish("panda_power/set", "OFF" if current else "ON")

    def choose_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Python-Skript wählen",
            str(Path.home()),
            "Python (*.py);;Alle Dateien (*)",
        )
        if path:
            self.script_path = path
            self.working_dir = str(Path(path).parent)
            self.config_path = str(get_default_config_path(path))
            self.runtime_config = ensure_config(Path(self.config_path))
            self.script_edit.setText(path)

    def append_log(self, text: str):
        if not text:
            return

        self.log_output.moveCursor(QTextCursor.End)
        self.log_output.insertPlainText(text)
        self.log_output.moveCursor(QTextCursor.End)

        for raw_line in text.replace("\r", "\n").splitlines():
            line = ANSI_RE.sub("", raw_line).strip()
            if line:
                self._parse_line(line)

    def _parse_line(self, line: str):

        if "Connection lost" in line or "ERR" in line:
            self.status_badge.setText("Fehler")
            self.status_badge.setStyleSheet(
                "background:#7a1f1f;color:white;padding:8px 14px;border-radius:12px;font-weight:700;"
            )

        if "SLICER MODE ENTERED" in line:
            self._set_value_label(self.lbl_info, "lbl_info", "Slicer Mode Entered")
            self._set_value_label(self.lbl_mode, "lbl_mode", "SL-PRIO")

        match = STATUS_RE.search(line)
        if not match:
            return

        data = match.groupdict()
        state = data["state"].strip()

        self._set_value_label(self.lbl_state, "lbl_state", f"{data['icon']} {state}")
        self._set_value_label(self.lbl_bed, "lbl_bed", self._fmt_temp_text(data['bed']))
        self._set_value_label(self.lbl_heiz, "lbl_heiz", data["heiz"])
        self._set_value_label(self.lbl_fan, "lbl_fan", data["fan"])
        self._set_value_label(self.lbl_info, "lbl_info", data["info"])
        self._set_value_label(self.lbl_mode, "lbl_mode", f"{data['mode']} {data['mode_temp']}°")

        active_mode = "Slicer" if data["mode"] == "SL-PRIO" else (
            "Automatik" if self.state_cache.get(self._topic("panda_modus"), "") == "Automatik" else
            "Manuell" if self.state_cache.get(self._topic("panda_modus"), "") == "Manuell" else
            "Dryer" if self.state_cache.get(self._topic("panda_modus"), "") == "Dry" else
            self.state_cache.get(self._topic("panda_modus"), "Unbekannt")
        )
        self._set_value_label(self.lbl_last, "lbl_last", f"READY  Aktiver Modus: {active_mode}")

        self.state_cache[self._topic("soll")] = self._fmt_temp_plain(data["kammer_soll"])
        self.state_cache[self._topic("ist")] = self._fmt_temp_plain(data["kammer_ist"])
        self._update_kammer_label(soll=data["kammer_soll"], ist=data["kammer_ist"])

        if self._can_apply_to_widget("soll", self.spin_kammer_soll, data["kammer_soll"]):
            self._set_spin_value_if_changed(self.spin_kammer_soll, float(data["kammer_soll"]))

        if "LOCKED" in state:
            badge_style = "background:#8b0000;color:white;padding:8px 14px;border-radius:12px;font-weight:700;"
        elif data["heiz"] == "AN":
            badge_style = "background:#8a5a00;color:white;padding:8px 14px;border-radius:12px;font-weight:700;"
        else:
            badge_style = "background:#1f6b3a;color:white;padding:8px 14px;border-radius:12px;font-weight:700;"

        self.status_badge.setText(state)
        self.status_badge.setStyleSheet(badge_style)

    def start_process(self):
        script = self.script_edit.text().strip()
        if not script:
            QMessageBox.warning(self, "Fehler", "Bitte ein Python-Skript auswählen.")
            return
        if not os.path.exists(script):
            QMessageBox.warning(self, "Fehler", f"Skript nicht gefunden:\n{script}")
            return
        if self.process and self.process.state() != QProcess.NotRunning:
            QMessageBox.information(self, "Läuft bereits", "Das Skript läuft schon.")
            return

        self.script_path = script
        self.working_dir = str(Path(script).parent)
        self.config_path = str(get_default_config_path(script))
        self.runtime_config = ensure_config(Path(self.config_path))

        host_ip = self.runtime_config.get("HOST_IP", "")
        QMessageBox.information(
            self,
            "Wichtig vor dem Start",
            f"In der Panda UI muss bei Printer IP die Host-IP dieses PCs eingetragen sein:\n\n{host_ip}\n\nErst danach Bind ausführen."
        )

        self.process = QProcess(self)
        self.process.setProgram("pkexec")
        self.process.setArguments(["/usr/bin/python3", "-u", self.script_path])
        self.process.setWorkingDirectory(self.working_dir)
        self.process.setProcessChannelMode(QProcess.MergedChannels)

        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        self.process.start()

        self.append_log(f"\n[GUI] Starte mit Root-Rechten: {self.script_path}\n")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_badge.setText("Startet...")
        self.status_badge.setStyleSheet(
            "background:#1f4f8b;color:white;padding:8px 14px;border-radius:12px;font-weight:700;"
        )

    def stop_process(self):
        if not self.process:
            return

        self.append_log("\n[GUI] Stop angefordert...\n")

        try:
            kill_cmd = (
                f"pkill -TERM -f '/usr/bin/python3 -u {self.script_path}' || "
                f"pkill -TERM -f '{Path(self.script_path).name}'"
            )
            killer = QProcess(self)
            killer.start("pkexec", ["bash", "-lc", kill_cmd])
            killer.waitForFinished(5000)
        except Exception as e:
            self.append_log(f"[GUI] Stop-Fehler: {e}\n")

        if self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.append_log("[GUI] Prozess reagiert nicht, wird hart beendet.\n")
                self.process.kill()
                self.process.waitForFinished(2000)

    def _read_output(self):
        if not self.process:
            return
        data = self.process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        data = data.replace("\x1b[K", "")
        data = data.replace("\r", "\n")
        self.append_log(data)

    def _process_finished(self, exit_code, exit_status):
        self.append_log(f"\n[GUI] Prozess beendet. Exit-Code: {exit_code}\n")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_badge.setText("Gestoppt")
        self.status_badge.setStyleSheet(
            "background:#5a1f1f;color:white;padding:8px 14px;border-radius:12px;font-weight:700;"
        )
        self.process = None

    def _process_error(self, err):
        self.append_log(f"\n[GUI] Prozessfehler: {err}\n")

    def closeEvent(self, event):
        try:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        except Exception:
            pass

        if self.process and self.process.state() != QProcess.NotRunning:
            self.stop_process()

        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Panda Control GUI")
    app.setApplicationDisplayName("Panda-Gui")
    app.setDesktopFileName("panda-gui")
    icon_candidates = [
        str(Path.home() / "Panda" / "panda_gui.png"),
        str(Path.home() / "Panda" / "panda_gui.ico"),
        str(Path.home() / "Panda" / "icon.png"),
        str(Path.home() / "Panda" / "icon.ico"),
    ]
    icon_set = False
    for icon_path in icon_candidates:
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            app.setWindowIcon(icon)
            icon_set = True
            break
    if not icon_set:
        theme_icon = QIcon.fromTheme("applications-engineering")
        if not theme_icon.isNull():
            app.setWindowIcon(theme_icon)
    win = PandaControlWindow()
    if not win.windowIcon().isNull():
        app.setWindowIcon(win.windowIcon())
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
