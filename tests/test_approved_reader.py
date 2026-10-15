import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.fixture
def handler(monkeypatch):
    spec=importlib.util.spec_from_file_location('approved_reader',Path(__file__).parents[1]/'modules/approved-reader/handler.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    monkeypatch.setenv('RGCE_ENABLED','true')
    monkeypatch.setenv('RGCE_SOURCE',json.dumps({'source':'s3-object','role_arn':'arn:aws:iam::111122223333:role/RemediGeniusCommunityReadOnly','region':'us-east-1','location':'s3://example-bucket/input.json','hours':1,'max_calls':1}))
    monkeypatch.setenv('RGCE_EXTERNAL_ID','synthetic-only')
    monkeypatch.setenv('RGCE_OUTPUT_BUCKET','example-bucket')
    monkeypatch.setenv('RGCE_CODE_SHA256','test-code-hash')
    return mod


def test_reader_requires_consent_and_exact_plan(handler,monkeypatch):
    monkeypatch.setattr(handler,'collect',lambda *a,**k:pytest.fail('Collection must not run'))
    for event in ({},{'consent':False,'plan_hash':'wrong'},{'consent':True,'plan_hash':'wrong'}):
        with pytest.raises(PermissionError):handler.main(event,SimpleNamespace(aws_request_id='test'))
    monkeypatch.setenv('RGCE_ENABLED','false')
    with pytest.raises(PermissionError,match='paused'):handler.main({},None)


def test_receipt_has_code_runtime_and_evidence_hash(handler,monkeypatch):
    import os
    spec=json.loads(os.environ['RGCE_SOURCE']);ph=handler.plan(**spec)['plan_hash']
    payload={'coverage':'selected_source','errors':[],'facts':{'synthetic':True}}
    monkeypatch.setattr(handler,'collect',lambda *a,**kw:payload)
    captured={}
    class S3:
        def put_object(self,**kw):captured.update(kw)
    monkeypatch.setattr(handler.boto3,'client',lambda *a,**kw:S3())
    result=handler.main({'consent':True,'plan_hash':ph},SimpleNamespace(aws_request_id='synthetic-run'))
    assert result['key']=='outputs/reader/synthetic-run.json'
    receipt=json.loads(captured['Body'])
    assert receipt['code_sha256']=='test-code-hash'
    assert receipt['evidence_hash']==handler.digest(payload)
    assert receipt['python'] and receipt['boto3']


def test_reader_build_normalizes_git_line_endings(tmp_path):
    spec=importlib.util.spec_from_file_location('reader_build',Path(__file__).parents[1]/'modules/approved-reader/build.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    windows=tmp_path/'windows.py';linux=tmp_path/'linux.py'
    windows.write_bytes(b'x = 1\r\ny = 2\r\n');linux.write_bytes(b'x = 1\ny = 2\n')
    assert mod.source_bytes(windows)==mod.source_bytes(linux)
