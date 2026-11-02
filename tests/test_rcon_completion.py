"""Wire-level peers distinguish empty output, complete replies and failures."""
from contextlib import contextmanager
import socket
import struct
import threading
import time

import pytest

from test_rcon_flush_deadline import controller_rcon


def packet(identifier,kind,text):
    body=struct.pack('<ii',identifier,kind)+text.encode()+b'\0\0'
    return struct.pack('<i',len(body))+body


def exact(connection,count):
    result=b''
    while len(result)<count:
        part=connection.recv(count-len(result))
        if not part:raise EOFError()
        result+=part
    return result


def request(connection):
    body=exact(connection,struct.unpack('<i',exact(connection,4))[0])
    assert body[-2:]==b'\0\0'
    return *struct.unpack('<ii',body[:8]),body[8:-2].decode()


@contextmanager
def peer(handler,auth=True):
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
    errors=[];commands=[]
    def run():
        try:
            listener.settimeout(3)
            with listener.accept()[0] as connection:
                connection.settimeout(3)
                assert request(connection)==(11,3,'fixture-secret')
                connection.sendall(packet(11 if auth else -1,2,''))
                if auth:
                    identifier,kind,command=request(connection)
                    assert (identifier,kind)==(12,2)
                    commands.append(command)
                    handler(connection)
        except (EOFError,BrokenPipeError,ConnectionResetError):pass
        except Exception as error:errors.append(error)
        finally:listener.close()
    thread=threading.Thread(target=run,daemon=True);thread.start()
    try:yield controller_rcon(listener.getsockname()[1],.15),commands
    finally:
        thread.join(4)
        assert not thread.is_alive() and not errors,errors


def complete(connection):
    assert request(connection)==(13,0,'')
    connection.sendall(packet(13,0,'Unknown request 0'))


def test_missing_empty_command_packet_requires_completion_acknowledgement():
    with peer(complete) as (rcon,commands):
        assert rcon('execute if block 0 0 0 air run say matched')==''
    assert commands==['execute if block 0 0 0 air run say matched']


def test_explicit_empty_command_packet_is_also_completed():
    def handler(connection):
        connection.sendall(packet(12,0,''));complete(connection)
    with peer(handler) as (rcon,_):assert rcon('fixture')==''


def test_all_response_frames_are_collected_before_returning():
    def handler(connection):
        connection.sendall(packet(12,0,'a'*4096)+packet(12,0,'b'*4096)+packet(12,0,'end'))
        complete(connection)
    with peer(handler) as (rcon,_):assert rcon('help')=='a'*4096+'b'*4096+'end'


def test_secret_is_redacted_even_when_it_crosses_a_frame_boundary():
    def handler(connection):
        connection.sendall(packet(12,0,'value fixture-')+packet(12,0,'secret done'))
        complete(connection)
    with peer(handler) as (rcon,_):assert rcon('fixture')=='value [REDACTED] done'


def test_fragmented_tcp_packets_do_not_truncate_the_response():
    def handler(connection):
        raw=packet(12,0,'complete response')
        for part in [raw[:2],raw[2:7],raw[7:]]:connection.sendall(part)
        complete(connection)
    with peer(handler) as (rcon,_):assert rcon('fixture')=='complete response'


def test_late_nonempty_reply_is_not_misreported_as_empty_success():
    def handler(connection):
        time.sleep(.22)
        connection.sendall(packet(12,0,'late response'));complete(connection)
    with peer(handler) as (rcon,_):
        with pytest.raises(TimeoutError):rcon('list')


def test_a_missing_completion_acknowledgement_is_an_error():
    def handler(connection):
        assert request(connection)==(13,0,'');time.sleep(.3)
    with peer(handler) as (rcon,_):
        with pytest.raises(TimeoutError):rcon('fixture')


@pytest.mark.parametrize('identifier,kind,text',[(14,0,'Unknown request 0'),(13,2,'Unknown request 0'),(13,0,'unexpected')])
def test_completion_must_have_the_exact_expected_identity(identifier,kind,text):
    def handler(connection):
        assert request(connection)==(13,0,'')
        connection.sendall(packet(identifier,kind,text))
    with peer(handler) as (rcon,_):
        with pytest.raises(RuntimeError,match='response invalid'):rcon('fixture')


def test_disconnection_is_not_empty_success():
    with peer(lambda connection:None) as (rcon,_):
        with pytest.raises(ConnectionError):rcon('fixture')


def test_authentication_failure_does_not_send_a_command():
    with peer(lambda connection:None,auth=False) as (rcon,commands):
        with pytest.raises(RuntimeError,match='authentication rejected'):rcon('fixture')
    assert commands==[]


def test_textual_command_errors_are_preserved():
    def handler(connection):
        connection.sendall(packet(12,0,'Unknown or incomplete command'));complete(connection)
    with peer(handler) as (rcon,_):assert rcon('invalid-fixture')=='Unknown or incomplete command'


def test_response_size_is_bounded():
    def handler(connection):
        connection.sendall(packet(12,0,'start'))
        assert request(connection)==(13,0,'')
        for _ in range(18):connection.sendall(packet(12,0,'x'*65500))
    with peer(handler) as (rcon,_):
        with pytest.raises(RuntimeError,match='response limit'):rcon('fixture')
