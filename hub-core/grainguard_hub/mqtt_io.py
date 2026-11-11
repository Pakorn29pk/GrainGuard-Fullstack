"""MQTT bridge: subscribes gg/+/status|tele|evt, feeds the engine, relays cmd to nodes."""
from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt

from .config import Config
from .engine import Engine

log = logging.getLogger("gg.mqtt")
ID_RE = re.compile(r"^[a-z0-9_-]{1,40}$")


class MqttBridge:
    def __init__(self, cfg: Config, engine: Engine):
        self.cfg, self.engine = cfg, engine
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="grainguard-hub-" + cfg.hub_id,
                                  clean_session=True)
        if cfg.mqtt_user:
            self.client.username_pw_set(cfg.mqtt_user, cfg.mqtt_pass)
        self.client.will_set("gg/hub/status", "offline", qos=1, retain=True)
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.connected = False
        self._started = False

    def start(self) -> None:
        self.client.connect_async(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=15)
        self.client.loop_start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        try:
            if self.connected:
                self.client.publish("gg/hub/status", "offline", qos=1, retain=True).wait_for_publish(2)
            self.client.disconnect()
        except Exception:
            pass
        self.client.loop_stop()
        self._started = False

    # ---------------------------------------------------------- callbacks
    def _on_connect(self, client, userdata, flags, rc, props=None):
        ok = not rc.is_failure if hasattr(rc, "is_failure") else rc == 0
        if not ok:
            log.error("MQTT connect refused: %s", rc)
            return
        log.info("MQTT connected to %s:%s", self.cfg.mqtt_host, self.cfg.mqtt_port)
        client.subscribe([("gg/+/status", 1), ("gg/+/tele", 0), ("gg/+/evt", 1)])
        client.publish("gg/hub/status", "online", qos=1, retain=True)
        self.connected = True
        self.engine.set_mqtt(True)

    def _on_disconnect(self, client, userdata, flags, rc, props=None):
        if self.connected:
            log.warning("MQTT disconnected: %s", rc)
        self.connected = False
        self.engine.set_mqtt(False)

    def _on_message(self, client, userdata, msg):
        try:
            parts = msg.topic.split("/")
            if len(parts) != 3 or parts[0] != "gg":
                return
            mac = parts[1].lower().replace(":", "")
            if mac == "hub" or not ID_RE.match(mac):
                return
            kind = parts[2]
            if kind == "status":
                self.engine.on_status(mac, msg.payload.decode("utf-8", "replace"))
                return
            if kind not in ("tele", "evt"):
                return
            d = json.loads(msg.payload)
            if not isinstance(d, dict):
                raise ValueError("payload is not an object")
            if kind == "tele":
                self.engine.on_tele(mac, d)
            else:
                self.engine.on_evt(mac, d)
        except (ValueError, UnicodeDecodeError):
            self.engine.counters["bad"] += 1
            log.debug("bad payload on %s", msg.topic)
        except Exception:
            log.exception("error handling %s", msg.topic)

    # ------------------------------------------------------------ publish
    def send_cmd(self, mac: str, payload: Dict[str, Any]) -> bool:
        if not self.connected:
            return False
        info = self.client.publish("gg/%s/cmd" % mac, json.dumps(payload, separators=(",", ":")), qos=1)
        try:
            info.wait_for_publish(3)
        except Exception:
            return False
        return info.is_published()
