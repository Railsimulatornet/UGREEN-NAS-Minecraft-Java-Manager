"""A real delayed RCON peer reproduces slow world saves without a game server."""
import ast
from pathlib import Path
import socket
import struct
import threading
import time
from types import SimpleNamespace

import pytest


def controller_rcon(port):
    source=Path(__file__).parents[1]/'mcj/controller.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in {'read_exact','receive','rcon'}]
    original=socket.create_connection
    def connect(address,timeout):
        assert address==('minecraft',25575) and timeout==4
        return original(('127.0.0.1',port),timeout=timeout)
    scope={'socket':SimpleNamespace(create_connection=connect),'struct':struct,'RCON':'fixture-secret'}
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),scope)
    return scope['rcon']


def delayed_peer(delay):
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
    port=listener.getsockname()[1];observed=[];errors=[]
    def exact(connection,count):
        raw=b''
        while len(raw)<count:
            chunk=connection.recv(count-len(raw))
            if not chunk:raise EOFError()
            raw+=chunk
        return raw
    def receive(connection):
        length=struct.unpack('<i',exact(connection,4))[0]
        raw=exact(connection,length)
        return *struct.unpack('<ii',raw[:8]),raw[8:-2].decode()
    def send(connection,identifier,kind,text):
        raw=struct.pack('<ii',identifier,kind)+text.encode()+b'\0\0'
        connection.sendall(struct.pack('<i',len(raw))+raw)
    def run():
        try:
            listener.settimeout(10)
            with listener.accept()[0] as connection:
                connection.settimeout(10)
                identifier,kind,text=receive(connection)
                assert (identifier,kind,text)==(11,3,'fixture-secret')
                send(connection,11,2,'')
                identifier,kind,text=receive(connection);observed.append(text)
                assert (identifier,kind)==(12,2)
                time.sleep(delay)
                try:send(connection,12,0,'Saved the game fixture-secret')
                except (BrokenPipeError,ConnectionResetError):pass
        except Exception as error:errors.append(error)
        finally:listener.close()
    thread=threading.Thread(target=run,daemon=True);thread.start()
    return port,thread,observed,errors


def test_world_flush_waits_for_a_real_response_after_four_seconds():
    port,thread,observed,errors=delayed_peer(4.3)
    try:assert controller_rcon(port)('save-all flush')=='Saved the game [REDACTED]'
    finally:thread.join(12)
    assert observed==['save-all flush'] and not errors and not thread.is_alive()


def test_normal_rcon_queries_keep_the_short_response_deadline():
    port,thread,observed,errors=delayed_peer(4.3)
    try:
        with pytest.raises(TimeoutError):controller_rcon(port)('list')
    finally:thread.join(12)
    assert observed==['list'] and not errors and not thread.is_alive()
