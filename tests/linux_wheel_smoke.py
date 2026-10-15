"""Run inside a disposable Linux container with dist mounted read-only at /artifacts."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

wheel=Path('/artifacts/remedigenius_community-0.1.0rc6-py3-none-any.whl')
subprocess.run([sys.executable,'-m','pip','install',str(wheel)+'[aws,test]'],check=True)
from fastapi.testclient import TestClient
from rgce import core
from rgce.app import create_app
from rgce.store import Store
from rgce.workspace import export_workspace,verify_workspace

with tempfile.TemporaryDirectory() as home:
    store=Store(home);demo=core.demo(store)
    workspace=export_workspace(store,[demo['before']['id']])
    assert verify_workspace(workspace['folder'])['status']=='verified'
    assert core.compare(store,demo['before']['id'],demo['after']['id'])['comparable']
    client=TestClient(create_app(home))
    assert client.get('/').status_code==200
    assert client.get('/static/remedigenius-investigate.SKILL.md').status_code==200
    token=client.get('/api/session').json()['token']
    response=client.post('/api/workspace/export',json={'record_ids':[demo['before']['id']]},headers={'x-rgce-token':token})
    assert response.status_code==200
    print(json.dumps({'linux_fresh_wheel':True,'demo_and_reassessment':True,'file_export_verify':True,'console_api':True,'packaged_skill':True,'aws_or_model_calls':False}))
