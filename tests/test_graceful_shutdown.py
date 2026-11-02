"""Shutdown must finish Minecraft's own save, without a second in-tick flush."""
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest
from mcj import job_control


def shutdown(monkeypatch,events,*,disconnect=False,count=0,status='running',failure=None):
    monkeypatch.setattr(job_control,'may_disconnect_players',lambda:disconnect)
    function=next(node for node in ast.parse((Path(__file__).parents[1]/'mcj/controller.py').read_text(encoding='utf-8')).body
                  if isinstance(node,ast.FunctionDef) and node.name=='graceful_stop')
    container=SimpleNamespace(status=status,reload=lambda:events.append('reload'))
    def rcon(command):
        if command=='save-all flush':raise ConnectionError('watchdog closed RCON during a slow synchronous flush')
        events.append(('rcon',command))
    def stop(value):
        assert value is container
        if failure:raise failure
        events.append('shutdown_saved_worlds');container.status='exited'
    scope={'__name__':'mcj.controller','__package__':'mcj','ROOT':Path('/fixture'),'server_shutdown':SimpleNamespace(stop_legacy=lambda *args:False),'rcon':rcon,'player_count':lambda:count,'stop_container':stop,'time':SimpleNamespace(sleep=lambda seconds:events.append(('wait',seconds)))}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'<controller shutdown>','exec'),scope)
    return lambda:scope['graceful_stop'](container),container


def test_slow_disk_flush_is_not_requested_before_the_clean_shutdown(monkeypatch):
    events=[];run,container=shutdown(monkeypatch,events)
    run()
    assert events==['reload','shutdown_saved_worlds'] and container.status=='exited'


def test_authorized_disconnect_keeps_the_warning_before_shutdown(monkeypatch):
    events=[];run,_=shutdown(monkeypatch,events,disconnect=True,count=1)
    run()
    assert events[0]=='reload' and events[1][0]=='rcon' and '10' in events[1][1]
    assert events[2:]==[('wait',10),'shutdown_saved_worlds']


def test_unknown_presence_does_not_stop_the_server(monkeypatch):
    events=[];run,_=shutdown(monkeypatch,events,disconnect=True,count=None)
    with pytest.raises(RuntimeError,match='player_count_unknown'):run()
    assert events==['reload']


def test_already_stopped_server_needs_no_commands(monkeypatch):
    events=[];run,_=shutdown(monkeypatch,events,status='exited')
    run();assert events==['reload']


def test_incomplete_shutdown_still_blocks_the_caller(monkeypatch):
    events=[];run,container=shutdown(monkeypatch,events,failure=RuntimeError('shutdown_pending_no_forced_kill'))
    with pytest.raises(RuntimeError,match='shutdown_pending_no_forced_kill'):run()
    assert container.status=='running' and events==['reload']
