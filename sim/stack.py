"""Helpers to bring up a complete local stack (broker + hub + mock cloud + virtual fleet).
Used by the end-to-end tests and by screens.py."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Optional


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_port(port: int, timeout: float = 10.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), 0.3).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


class Broker:
    def __init__(self, kind: str, port: int, proc: subprocess.Popen):
        self.kind, self.port, self.proc = kind, port, proc

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except Exception:
            self.proc.kill()


def start_broker(workdir: str, port: Optional[int] = None, prefer: Optional[str] = None) -> Broker:
    """Start a local anonymous MQTT broker: real Mosquitto if installed, else pure-python amqtt.
    prefer / $GG_BROKER may force 'mosquitto' or 'amqtt'."""
    port = port or free_port()
    want = prefer or os.environ.get("GG_BROKER", "")
    mos = shutil.which("mosquitto") or ("/usr/sbin/mosquitto" if os.path.exists("/usr/sbin/mosquitto") else None)
    os.makedirs(workdir, exist_ok=True)
    if want != "amqtt" and mos:
        conf = os.path.join(workdir, "mosq%d.conf" % port)
        with open(conf, "w") as f:
            f.write("listener %d 127.0.0.1\nallow_anonymous true\npersistence false\nlog_type error\n" % port)
        proc = subprocess.Popen([mos, "-c", conf], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        kind = "mosquitto"
    else:
        amqtt = shutil.which("amqtt")
        if not amqtt:
            raise RuntimeError("no MQTT broker available (apt-get install mosquitto  or  pip install amqtt)")
        conf = os.path.join(workdir, "amqtt%d.yaml" % port)
        with open(conf, "w") as f:
            f.write("listeners:\n  default:\n    type: tcp\n    bind: 127.0.0.1:%d\n"
                    "plugins:\n  amqtt.plugins.authentication.AnonymousAuthPlugin:\n    allow_anonymous: true\n" % port)
        proc = subprocess.Popen([amqtt, "-c", conf], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        kind = "amqtt"
    if not wait_port(port, 15):
        proc.kill()
        raise RuntimeError("broker did not start (%s)" % kind)
    return Broker(kind, port, proc)


# fast thresholds so that every rule can be exercised in seconds instead of minutes
FAST = dict(stale_s=3.0, boot_grace_s=8.0, offline_event_s=6.0, flatline_s=6.0, flatline_clear_s=2.0, sat_window_s=10.0,
            sat_count=5, sat_clear_count=1, vin_s=4.0, vin_clear_s=2.0, temp_s=3.0, temp_clear_s=3.0,
            heartbeat_s=5.0, plant_window_s=2.0)
