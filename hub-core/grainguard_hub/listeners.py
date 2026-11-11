"""One Hub, two trusted channels; compatible with uvicorn 0.27 and newer.

Local administration always binds IPv4 loopback. The online listener always
wraps the application, even when its socket is reached through a local proxy.
"""
from __future__ import annotations

import asyncio
import contextlib
import signal
import socket
import threading

import uvicorn

from .auth import OnlineOnlyApp


def _bind(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(128)
        sock.setblocking(False)
        return sock
    except BaseException:
        sock.close()
        raise


async def serve(app, local_port, online_port, online_host="127.0.0.1",
                online_ssl_certfile=None, online_ssl_keyfile=None):
    """Serve until a stop signal; any startup/listener failure propagates.

    Callers own Hub startup/shutdown. A public deployment also configures the
    exact HTTPS GG_PUBLIC_ORIGIN before creating the application. This helper
    never trusts forwarded headers or exposes a local administration socket.
    """
    if not all(type(port) is int and 0 <= port <= 65535 for port in (local_port, online_port)):
        raise ValueError("Listener ports must be integers from 0 to 65535")
    if bool(online_ssl_certfile) != bool(online_ssl_keyfile):
        raise ValueError("Both online TLS certificate and key are required")
    common = dict(proxy_headers=False, access_log=False, log_level="warning", lifespan="off",
                  timeout_keep_alive=5, timeout_graceful_shutdown=5, limit_concurrency=64)
    configs = [uvicorn.Config(app,host="127.0.0.1",port=local_port,**common),
               uvicorn.Config(OnlineOnlyApp(app),host=online_host,port=online_port,
                              ssl_certfile=online_ssl_certfile,ssl_keyfile=online_ssl_keyfile,**common)]
    # Load imports/TLS synchronously: failures happen before either listener starts.
    for config in configs:
        config.load()
    servers = [uvicorn.Server(config) for config in configs]
    sockets, tasks, previous = [], [], {}
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True
        for server in servers:
            server.should_exit = True

    try:
        # Bind both before launching tasks so an occupied port cannot leave a
        # half-running process or uvicorn's internal SystemExit startup path.
        sockets.append(_bind("127.0.0.1",local_port))
        sockets.append(_bind(online_host,online_port))
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT,signal.SIGTERM):
                previous[signum] = signal.getsignal(signum)
                signal.signal(signum,stop)
        for server in servers:
            # 0.27 calls install_signal_handlers; newer releases use capture_signals.
            server.install_signal_handlers = lambda: None
            server.capture_signals = contextlib.nullcontext
        tasks = [asyncio.create_task(server.serve(sockets=[sock])) for server,sock in zip(servers,sockets)]
        done, _ = await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        if not stopping:
            raise RuntimeError("A dashboard listener stopped unexpectedly")
    finally:
        stop()
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks,return_exceptions=True),timeout=10)
            except asyncio.TimeoutError:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
        for sock in sockets:
            sock.close()
        for signum,handler in previous.items():
            signal.signal(signum,handler)
