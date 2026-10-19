"""Local deterministic boundary tests; not live AWS acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'deploy/collector'))
import server as collector_server
import state_store


def test_unknown_action_and_path_fail_closed():
    with pytest.raises(ValueError):collector_server.dispatch({'action':'shell','command':'aws s3 ls'})
    with pytest.raises(ValueError):collector_server.stored('../state/latest.json')
    with pytest.raises(ValueError):collector_server.dispatch({'action':'compare','before':'not-a-run','after':'bad'})


def test_schema_uses_installed_sdk_without_cloud():
    r=collector_server.dispatch({'action':'schema','service':'s3','operation':'put_bucket_versioning','field':'VersioningConfiguration'})
    assert r['schema']['fields']['MFADelete']['constraints']['enum']==['Enabled','Disabled']


class MemoryS3:
    def __init__(self):self.objects={}
    def upload_file(self,path,bucket,key):self.objects[key]=Path(path).read_bytes()
    def put_object(self,**kw):self.objects[kw['Key']]=kw['Body']
    def get_object(self,**kw):
        import io
        return {'Body':io.BytesIO(self.objects[kw['Key']])}
    def download_file(self,bucket,key,path):Path(path).write_bytes(self.objects[key])


def test_s3_checkpoint_sqlite_and_corrupt_restore(tmp_path,monkeypatch):
    monkeypatch.setenv('BUCKET','test-bucket');monkeypatch.setenv('PREFIX','ce')
    home=tmp_path/'home';home.mkdir()
    (home/'SOUL.md').write_text('retained instructions')
    with sqlite3.connect(home/'state.db') as c:
        c.execute('create table sessions(id text)');c.execute("insert into sessions values ('retained')")
    memory=MemoryS3()
    with patch.object(state_store.boto3,'client',return_value=memory):
        assert state_store.backup(home)['status']=='OK'
        restored=tmp_path/'restored'
        assert state_store.restore(restored)['status']=='RESTORED'
        with sqlite3.connect(restored/'state.db') as c:assert c.execute('select id from sessions').fetchone()[0]=='retained'
        with pytest.raises(ValueError):state_store.restore(restored)
        manifest=json.loads(memory.objects['ce/state/latest.json'])
        memory.objects[manifest['key']]=b'corrupt'
        with pytest.raises(ValueError,match='hash mismatch'):state_store.restore(tmp_path/'corrupt')
        assert not (tmp_path/'corrupt').exists()
