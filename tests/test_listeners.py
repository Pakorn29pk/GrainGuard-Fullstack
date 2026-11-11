"""Listener lifecycle checks; bind isolated ephemeral localhost sockets only."""
import asyncio
import signal
import socket
from unittest.mock import patch

import pytest

from grainguard_hub import listeners
from grainguard_hub.auth import OnlineOnlyApp


def test_bind_conflict_closes_first_socket_and_starts_neither():
    occupied = socket.socket()
    occupied.bind(("127.0.0.1",0))
    occupied.listen(1)
    first = []
    original = listeners._bind
    def record(host,port):
        sock = original(host,port)
        first.append(sock)
        return sock
    try:
        with patch.object(listeners,"_bind",side_effect=record),patch.object(listeners.uvicorn.Server,"serve") as run:
            with pytest.raises(OSError):
                asyncio.run(listeners.serve(lambda:None,0,occupied.getsockname()[1]))
            run.assert_not_called()
            assert first and first[0].fileno() == -1
    finally:
        occupied.close()


def test_old_and_new_signal_handlers_disabled_and_channel_wrapper_retained():
    seen = []
    before = {sig:signal.getsignal(sig) for sig in (signal.SIGINT,signal.SIGTERM)}
    async def fake_serve(server,sockets):
        server.install_signal_handlers()
        with server.capture_signals():
            seen.append((server.config,sockets[0]))
            if len(seen) == 2:
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
            while not server.should_exit:
                await asyncio.sleep(.001)
    with patch.object(listeners.uvicorn.Server,"serve",fake_serve):
        asyncio.run(listeners.serve(lambda:None,0,0))
    assert len(seen) == 2
    assert seen[0][0].host == "127.0.0.1"
    assert isinstance(seen[1][0].app,OnlineOnlyApp)
    assert all(not config.proxy_headers and config.lifespan == "off" for config,_ in seen)
    assert all(sock.fileno() == -1 for _,sock in seen)
    assert {sig:signal.getsignal(sig) for sig in before} == before


def test_listener_failure_stops_sibling_and_propagates_nonzero_exception():
    seen=[]
    async def fake_serve(server,sockets):
        seen.append(server)
        if isinstance(server.config.app,OnlineOnlyApp):
            raise RuntimeError("test startup failure")
        while not server.should_exit:
            await asyncio.sleep(.001)
    with patch.object(listeners.uvicorn.Server,"serve",fake_serve):
        with pytest.raises(RuntimeError,match="test startup failure"):
            asyncio.run(listeners.serve(lambda:None,0,0))
    assert len(seen)==2 and all(server.should_exit for server in seen)


def test_bad_ports_and_incomplete_tls_fail_before_listening():
    for args in ((-1,8081),(8080,65536),(True,8081)):
        with pytest.raises(ValueError):
            asyncio.run(listeners.serve(lambda:None,*args))
    with pytest.raises(ValueError,match="certificate"):
        asyncio.run(listeners.serve(lambda:None,0,0,online_ssl_certfile="missing.pem"))


def test_real_dual_http_and_signal_shutdown():
    sockets=[]
    original=listeners._bind
    def record(host,port):
        sock=original(host,port)
        sockets.append(sock)
        return sock
    async def app(scope,receive,send):
        body=(scope.get("gg_channel","local")+"|"+scope["client"][0]).encode()
        await send({"type":"http.response.start","status":200,"headers":[(b"content-length",str(len(body)).encode())]})
        await send({"type":"http.response.body","body":body})
    async def request(port):
        reader,writer=await asyncio.open_connection("127.0.0.1",port)
        writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\nX-Forwarded-For: 203.0.113.7\r\nConnection: close\r\n\r\n")
        await writer.drain()
        result=await asyncio.wait_for(reader.read(),timeout=3)
        writer.close()
        await writer.wait_closed()
        return result.split(b"\r\n\r\n",1)[1]
    async def scenario():
        task=asyncio.create_task(listeners.serve(app,0,0))
        try:
            while len(sockets)<2:
                await asyncio.sleep(.01)
            ports=[sock.getsockname()[1] for sock in sockets]
            local,online=await asyncio.gather(*(request(port) for port in ports))
            assert local==b"local|127.0.0.1"
            assert online==b"online|127.0.0.1"
        finally:
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
            await asyncio.wait_for(task,timeout=5)
    with patch.object(listeners,"_bind",side_effect=record):
        asyncio.run(scenario())
    assert all(sock.fileno()==-1 for sock in sockets)
