"""Exercise the actual skill CLI through a mocked local HTTP transport."""
import http.client
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('service', [None, 'bedrock', 'iam'])
def test_service_discovery_survives_skill_socket_transport(monkeypatch, capsys, service):
    script = Path(__file__).resolve().parents[1] / 'profiles/ce/desk/skills/ce-aws-read/scripts/aws_read.py'
    original = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda p, *a, **k:
        json.dumps({'transport':'unix', 'socket':'/unit-test.sock'})
        if str(p).replace('\\','/') == '/opt/ce-reader/config.json' else original(p, *a, **k))
    captured=[]
    monkeypatch.setattr(http.client.HTTPConnection, 'request',
        lambda self, method, url, body, headers: captured.append(json.loads(body)))
    monkeypatch.setattr(http.client.HTTPConnection, 'getresponse',
        lambda self: SimpleNamespace(read=lambda n: b'{"status":"OK"}'))
    monkeypatch.setattr(http.client.HTTPConnection, 'close', lambda self: None)
    monkeypatch.setattr(sys, 'argv', [str(script),'capabilities'] + ([] if service is None else ['--service='+service]))
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(script), run_name='__main__')
    assert exit_info.value.code == 0
    assert captured == [{'action':'capabilities', **({'service':service} if service else {})}]
    assert json.loads(capsys.readouterr().out)['status'] == 'OK'
