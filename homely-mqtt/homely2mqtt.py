#!/usr/bin/env python3
"""Homely to MQTT - Home Assistant Addon.

Bridges the Homely alarm system to MQTT with Home Assistant auto-discovery.
Supports real-time updates via WebSocket (Socket.IO) with periodic polling fallback.
"""

import json
import logging
import os
import sys
import threading
import time
from typing import Optional

import paho.mqtt.client as mqtt
import requests
import socketio

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_LEVELS = {
    "trace": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}


def setup_logging(level_str: str) -> logging.Logger:
    level = _LOG_LEVELS.get(level_str.lower(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    return logging.getLogger("homely2mqtt")


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load addon config from /data/options.json (HA addon standard)."""
    options_path = "/data/options.json"
    if os.path.exists(options_path):
        with open(options_path) as f:
            return json.load(f)
    return {}


def get_cfg(cfg: dict, key: str, env_key: str, default):
    """Return config value with fallback to env var then default."""
    if key in cfg and cfg[key] not in ("", None):
        return cfg[key]
    env_val = os.getenv(env_key)
    if env_val not in (None, ""):
        return env_val
    return default


# ---------------------------------------------------------------------------
# Homely API
# ---------------------------------------------------------------------------

_API_BASE = "https://sdk.iotiliti.cloud/homely"
_LOGIN_URL = f"{_API_BASE}/oauth/token"
_REFRESH_URL = f"{_API_BASE}/oauth/refresh-token"
_LOCATIONS_URL = f"{_API_BASE}/locations"
_HOME_URL = f"{_API_BASE}/home/"
_WS_HOST = "sdk.iotiliti.cloud"


class HomelyError(Exception):
    pass


class HomelyAPI:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.session = requests.Session()
        self.auth: Optional[dict] = None
        self.token_exp: int = 0
        self.location_id: Optional[str] = None
        self._sio: Optional[socketio.Client] = None
        self._sio_exit_code: int = 0

    # --- HTTP helpers ---

    def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            resp = self.session.request(method, url, timeout=30, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise HomelyError(f"Network error: {exc}") from exc
        self.logger.debug("%s %s -> %d", method.upper(), url, resp.status_code)
        if resp.status_code not in (200, 201):
            raise HomelyError(
                f"HTTP {resp.status_code} from {url}: {resp.text[:200]}"
            )
        return resp.json()

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.auth['access_token']}"}

    # --- Auth ---

    def login(self, username: str, password: str) -> None:
        self.auth = self._request(
            "POST", _LOGIN_URL, json={"username": username, "password": password}
        )
        self.token_exp = int(time.time()) + self.auth["expires_in"]
        self.logger.info("Logged in to Homely API")

    def refresh_token(self) -> None:
        now = int(time.time())
        if now + 300 >= self.token_exp:
            self.logger.info("Refreshing Homely access token")
            self.auth = self._request(
                "POST",
                _REFRESH_URL,
                json={"refresh_token": self.auth["refresh_token"]},
            )
            self.token_exp = now + self.auth["expires_in"]
        self.logger.debug(
            "Access token valid for another %ds", self.token_exp - now
        )

    # --- Locations / status ---

    def find_home(self, home_name: str = "") -> dict:
        locations = self._request(
            "GET", _LOCATIONS_URL, headers=self._auth_headers()
        )
        if not locations:
            raise HomelyError("No locations returned from Homely API")
        if home_name:
            loc = next((l for l in locations if l["name"] == home_name), None)
            if loc is None:
                names = [l["name"] for l in locations]
                raise HomelyError(
                    f"Home '{home_name}' not found. Available: {names}"
                )
        else:
            loc = locations[0]
        self.location_id = loc["locationId"]
        self.logger.info("Using home: %s (ID: %s)", loc["name"], self.location_id)
        return loc

    def home_status(self) -> dict:
        if not self.location_id:
            raise HomelyError("No location ID — call find_home() first")
        return self._request(
            "GET", _HOME_URL + self.location_id, headers=self._auth_headers()
        )

    # --- WebSocket ---

    def start_websocket(self, on_message) -> None:
        token = self.auth["access_token"]
        url = (
            f"https://{_WS_HOST}"
            f"?locationId={self.location_id}&token=Bearer%20{token}"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "locationId": self.location_id,
        }

        self._sio = socketio.Client(logger=False, engineio_logger=False)
        self._sio_exit_code = 0

        @self._sio.event
        def connect():
            self.logger.info("WebSocket connected")

        @self._sio.event
        def disconnect():
            self.logger.error("WebSocket disconnected")
            self._sio_exit_code = 2

        @self._sio.on("event")
        def on_event(data):
            on_message(data)

        def _run():
            self.logger.debug("Connecting WebSocket to %s", _WS_HOST)
            try:
                self._sio.connect(url, headers=headers)
                self._sio.wait()
            except Exception as exc:
                self.logger.error("WebSocket error: %s", exc)
                self._sio_exit_code = 2

        threading.Thread(target=_run, daemon=True).start()

    def ws_exit_code(self) -> int:
        return self._sio_exit_code


# ---------------------------------------------------------------------------
# MQTT device helpers
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    """Normalize names for use in MQTT topics and HA entity IDs."""
    table = str.maketrans(
        " .-æøåÆØÅ",
        "___aoaAOA",
    )
    return name.translate(table)


def _device_subtype(model_name: str, feature: str) -> Optional[str]:
    """Map a Homely feature + model name to a HA device subtype."""
    if feature == "temperature":
        return "temperature"
    if feature != "alarm":
        return None
    lower = model_name.lower()
    if "motion" in lower:
        return "motion"
    if "smoke" in lower:
        return "smoke"
    if "water" in lower or "flood" in lower or "moisture" in lower:
        return "moisture"
    if "glass" in lower:
        return "vibration"
    # door / window sensors both get "door" — most Homely window sensors are
    # door-mounted in practice
    return "door"


_COMPONENT_MAP = {
    "alarm_state": "sensor",
    "linkpercent": "sensor",
    "temperature": "sensor",
    "connectivity": "binary_sensor",
    "battery": "binary_sensor",
    "tamper": "binary_sensor",
    "motion": "binary_sensor",
    "door": "binary_sensor",
    "window": "binary_sensor",
    "smoke": "binary_sensor",
    "moisture": "binary_sensor",
    "vibration": "binary_sensor",
}

_DEVICE_CLASS_MAP = {
    "temperature": "temperature",
    "connectivity": "connectivity",
    "battery": "battery",
    "tamper": "tamper",
    "motion": "motion",
    "door": "door",
    "window": "window",
    "smoke": "smoke",
    "moisture": "moisture",
    "vibration": "vibration",
}

_ICON_MAP = {
    "alarm_state": "mdi:shield-home",
    "linkpercent": "mdi:signal",
    "motion": "mdi:motion-sensor",
    "door": "mdi:door",
    "window": "mdi:window-open-variant",
    "smoke": "mdi:smoke-detector",
    "moisture": "mdi:water",
    "vibration": "mdi:vibrate",
}

_UNIT_MAP = {
    "temperature": "°C",
    "linkpercent": "%",
}

_VALUE_TEMPLATE_MAP = {
    "temperature": "{{ value_json.temperature }}",
    "linkpercent": "{{ value_json.linkquality }}",
}


class MQTTDevice:
    """Represents a single HA MQTT auto-discovery entity."""

    def __init__(
        self,
        client: mqtt.Client,
        site: str,
        dev_name: str,
        model_name: str,
        object_name: str,
        subtype: str,
        discovery_prefix: str,
        state_prefix: str,
        model_attr: str,
        logger: logging.Logger,
        send_interval: int = 1200,
    ):
        self.logger = logger
        self.client = client
        self.send_interval = send_interval
        self.last_update: int = 0
        self.last_timestamp: Optional[str] = None
        self.last_state: Optional[str] = None

        ha_component = _COMPONENT_MAP.get(subtype, "sensor")
        full_id = _normalize(f"{site}_{dev_name}_{model_name}")
        topic_base = f"{state_prefix}/{full_id}/{object_name}"
        self.state_topic = f"{topic_base}/state"
        self.discovery_topic = (
            f"{discovery_prefix}/{ha_component}/{full_id}/{object_name}/config"
        )
        self.friendly_name = f"{site} {dev_name} {object_name}"

        config: dict = {
            "name": self.friendly_name,
            "unique_id": f"{full_id}_{object_name}",
            "state_topic": self.state_topic,
            "device": {
                "identifiers": [full_id],
                "name": f"{dev_name} ({model_name})",
                "model": model_attr or model_name,
                "manufacturer": "Homely",
            },
        }

        dc = _DEVICE_CLASS_MAP.get(subtype)
        if dc:
            config["device_class"] = dc

        icon = _ICON_MAP.get(subtype)
        if icon:
            config["icon"] = icon

        unit = _UNIT_MAP.get(subtype)
        if unit:
            config["unit_of_measurement"] = unit

        vt = _VALUE_TEMPLATE_MAP.get(subtype)
        if vt:
            config["value_template"] = vt

        self._config = config

    def update_config(self, extra: dict) -> None:
        self._config.update(extra)

    def publish_discovery(self) -> None:
        payload = json.dumps(self._config)
        self.logger.debug(
            "Discovery publish: %s", self.discovery_topic
        )
        self.client.publish(
            self.discovery_topic, payload=payload, qos=0, retain=True
        )

    def publish(self, message: str, timestamp: Optional[str] = None) -> bool:
        """Publish a state update, deduplicating by timestamp or value+interval."""
        now = int(time.time())

        if timestamp is not None:
            if timestamp == self.last_timestamp:
                self.logger.debug(
                    "%s: same timestamp, skipping", self.friendly_name
                )
                return False
            self.client.publish(self.state_topic, message)
            self.last_timestamp = timestamp
            self.last_update = now
            self.logger.info("%s => %s", self.friendly_name, message)
            return True

        if (
            self.last_state != message
            or now > self.last_update + self.send_interval
        ):
            self.client.publish(self.state_topic, message)
            self.last_state = message
            self.last_update = now
            self.logger.info("%s => %s", self.friendly_name, message)
            return True

        self.logger.debug("%s: unchanged, skipping", self.friendly_name)
        return False

    def publish_json(
        self, values: dict, timestamp: Optional[str] = None
    ) -> bool:
        return self.publish(json.dumps(values), timestamp)


# ---------------------------------------------------------------------------
# Alarm state mapping
# ---------------------------------------------------------------------------

_ALARM_STATES = {
    "DISARMED": "Disarmed",
    "ARM_PENDING": "Arming",
    "ARM_STAY_PENDING": "Arming stay",
    "ARMED_STAY": "Armed stay",
    "ARM_NIGHT_PENDING": "Arming night",
    "ARMED_NIGHT": "Armed night",
    "ARM_AWAY_PENDING": "Arming away",
    "ARMED_AWAY": "Armed away",
    "BREACHED": "Alarmed",
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    cfg = load_config()

    homely_username = get_cfg(cfg, "homely_username", "HOMELY_USER", "")
    homely_password = get_cfg(cfg, "homely_password", "HOMELY_PASSWORD", "")
    homely_home = get_cfg(cfg, "homely_home", "HOMELY_HOME", "")
    mqtt_host = get_cfg(cfg, "mqtt_host", "MQTT_SERVER", "core-mosquitto")
    mqtt_port = int(get_cfg(cfg, "mqtt_port", "MQTT_PORT", 1883))
    mqtt_username = get_cfg(cfg, "mqtt_username", "MQTT_USERNAME", "")
    mqtt_password = get_cfg(cfg, "mqtt_password", "MQTT_PASSWORD", "")
    discovery_prefix = get_cfg(
        cfg, "mqtt_discovery_prefix", "MQTT_DISCOVERY", "homeassistant"
    )
    state_prefix = get_cfg(cfg, "mqtt_state_prefix", "MQTT_STATE", "homely")
    poll_interval = int(get_cfg(cfg, "poll_interval", "POLL_INTERVAL", 120))
    log_level = get_cfg(cfg, "log_level", "LOG_LEVEL", "info")

    logger = setup_logging(log_level)

    if not homely_username or not homely_password:
        logger.error(
            "homely_username and homely_password must be set in addon config"
        )
        sys.exit(1)

    # --- MQTT ---
    mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "homely2mqtt")
    if mqtt_username:
        mq.username_pw_set(mqtt_username, mqtt_password)

    def _on_connect(client, userdata, flags, reason_code, props):
        if reason_code == 0:
            logger.info("MQTT connected to %s:%d", mqtt_host, mqtt_port)
        else:
            logger.error("MQTT connection failed: %s", reason_code)

    mq.on_connect = _on_connect

    mq.connect(mqtt_host, port=mqtt_port, keepalive=600)
    mq.loop_start()

    # --- Homely API ---
    api = HomelyAPI(logger)
    api.login(homely_username, homely_password)
    api.refresh_token()
    home = api.find_home(homely_home)
    site = _normalize(home.get("name", "Homely"))
    hs = api.home_status()

    # --- Device factory ---
    def make_device(
        dev_name: str,
        model_name: str,
        object_name: str,
        subtype: str,
        model_attr: str = "",
    ) -> MQTTDevice:
        return MQTTDevice(
            client=mq,
            site=site,
            dev_name=dev_name,
            model_name=model_name,
            object_name=object_name,
            subtype=subtype,
            discovery_prefix=discovery_prefix,
            state_prefix=state_prefix,
            model_attr=model_attr,
            logger=logger,
        )

    # --- Gateway-level aggregate entities ---
    alarm_dev = make_device("Gateway", "Alarm", "alarmstate", "alarm_state")
    lqi_dev = make_device("Gateway", "Network", "linkquality", "linkpercent")
    tamper_dev = make_device("Gateway", "Devices", "tamper", "tamper")
    online_dev = make_device("Gateway", "Devices", "connectivity", "connectivity")
    battery_dev = make_device("Gateway", "Devices", "battery", "battery")

    for gw_dev in (alarm_dev, lqi_dev, tamper_dev, online_dev, battery_dev):
        gw_dev.publish_discovery()

    # --- Per-device entity registry ---
    per_device: dict[str, MQTTDevice] = {}

    def ensure_devices(home_state: dict) -> None:
        """Register MQTT discovery for any new devices found in home state."""
        for d in home_state.get("devices", []):
            dev_id = d["id"]
            dev_name = d["name"]
            model_name = d.get("modelName", "Unknown")
            model_attr = d.get("modelName", "")
            for feature in d.get("features", {}):
                subtype = _device_subtype(model_name, feature)
                if subtype is None:
                    continue
                key = f"{dev_id}_{subtype}"
                if key not in per_device:
                    dev = make_device(
                        dev_name, model_name, feature, subtype, model_attr
                    )
                    dev.publish_discovery()
                    per_device[key] = dev
                    logger.info(
                        "Registered: %s [%s] as %s",
                        dev_name, model_name, subtype,
                    )

    ensure_devices(hs)

    # --- Alarm state publisher ---
    def publish_alarm(state_str: str) -> None:
        friendly = _ALARM_STATES.get(state_str, f"Unknown ({state_str})")
        alarm_dev.publish(friendly)

    publish_alarm(hs.get("alarmState", "DISARMED"))

    # --- WebSocket message handler (runs in daemon thread) ---
    def on_ws_message(msg: dict) -> None:
        msg_type = msg.get("type")
        data = msg.get("data", {})
        logger.debug("WS event: %s", msg_type)

        if msg_type == "device-state-changed":
            dev_id = data.get("deviceId")
            for change in data.get("changes", []):
                state_name = change.get("stateName")
                value = change.get("value")
                ts = change.get("lastUpdated")

                if state_name == "temperature":
                    key = f"{dev_id}_temperature"
                    if key in per_device:
                        per_device[key].publish_json(
                            {"temperature": value}, timestamp=ts
                        )

                elif state_name == "alarm":
                    onoff = "ON" if value else "OFF"
                    for subtype in (
                        "motion", "door", "window",
                        "smoke", "moisture", "vibration",
                    ):
                        key = f"{dev_id}_{subtype}"
                        if key in per_device:
                            per_device[key].publish(onoff, timestamp=ts)
                            break

        elif msg_type == "alarm-state-changed":
            publish_alarm(data.get("state", ""))

    api.start_websocket(on_ws_message)

    # --- Main polling loop ---
    logger.info(
        "Running. Poll interval: %ds, WebSocket active.", poll_interval
    )
    sleep_for = 15  # short first sleep so we refresh quickly after startup

    while True:
        # Sleep in 5s chunks so WebSocket disconnects are caught promptly
        elapsed = 0
        while elapsed < sleep_for:
            time.sleep(5)
            elapsed += 5
            if api.ws_exit_code() != 0:
                logger.error("WebSocket lost — exiting for supervisor restart")
                sys.exit(api.ws_exit_code())

        sleep_for = poll_interval

        logger.info("Polling Homely for status update")
        try:
            api.refresh_token()
            hs = api.home_status()
        except HomelyError as exc:
            logger.error("Status poll failed: %s", exc)
            continue

        ensure_devices(hs)
        publish_alarm(hs.get("alarmState", "DISARMED"))

        devs_online = "ON"
        devs_lowbat = "OFF"
        devs_tamper = "OFF"
        devs_lqi = 100

        for d in hs.get("devices", []):
            dev_id = d["id"]
            model_name = d.get("modelName", "Unknown")

            if not d.get("online", True):
                devs_online = "OFF"

            for feature, feat_data in d.get("features", {}).items():
                for state_name, state_data in feat_data.get("states", {}).items():
                    if not isinstance(state_data, dict):
                        continue
                    value = state_data.get("value")
                    ts = state_data.get("lastUpdated")
                    if value is None or ts is None:
                        continue

                    if feature == "temperature" and state_name == "temperature":
                        key = f"{dev_id}_temperature"
                        if key in per_device:
                            per_device[key].publish_json(
                                {"temperature": value}, timestamp=ts
                            )

                    elif state_name == "alarm":
                        onoff = "ON" if value else "OFF"
                        for subtype in (
                            "motion", "door", "window",
                            "smoke", "moisture", "vibration",
                        ):
                            key = f"{dev_id}_{subtype}"
                            if key in per_device:
                                per_device[key].publish(onoff, timestamp=ts)
                                break

                    elif state_name == "networklinkstrength":
                        try:
                            devs_lqi = min(devs_lqi, int(value))
                        except (TypeError, ValueError):
                            pass

                    elif state_name == "low" and value:
                        devs_lowbat = "ON"

                    elif state_name == "tamper" and value:
                        devs_tamper = "ON"

        lqi_dev.publish_json({"linkquality": devs_lqi})
        online_dev.publish(devs_online)
        tamper_dev.publish(devs_tamper)
        battery_dev.publish(devs_lowbat)


if __name__ == "__main__":
    main()
