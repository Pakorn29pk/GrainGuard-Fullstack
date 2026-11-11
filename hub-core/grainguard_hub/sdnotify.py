"""Minimal systemd sd_notify (READY / WATCHDOG / STOPPING) - no dependency."""
from __future__ import annotations

import os
import socket


def notify(msg: str) -> bool:
    path = os.environ.get("NOTIFY_SOCKET")
    if not path:
        return False
    if path.startswith("@"):
        path = "\0" + path[1:]
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            s.connect(path)
            s.sendall(msg.encode())
        finally:
            s.close()
        return True
    except OSError:
        return False


def watchdog_interval() -> float:
    """Seconds between WATCHDOG=1 pings (half of WatchdogSec), or 0 if not enabled."""
    try:
        usec = int(os.environ.get("WATCHDOG_USEC", "0"))
    except ValueError:
        return 0.0
    return usec / 2e6 if usec > 0 else 0.0
