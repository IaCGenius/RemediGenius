"""Constructed safety/budget tests; actual tool acceptance is recorded separately."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


validator=load('validator','deploy/validator/server.py')
runtime=load('validator_runtime','profiles/ce/desk/plugins/ce-runtime/__init__.py')


@pytest.mark.parametrize('payload',[
    {'format':'terraform','files':{'../escape.tf':'x'}},
    {'format':'terraform','files':{'credentials':'x'}},
    {'format':'aws-cli','argv':['configure','set','region','us-east-1']},
    {'format':'aws-cli','argv':['s3','cp','file','s3://target']},
    {'format':'aws-cli','argv':['ec2','run-instances','--cli-input-json','file:///etc/passwd']},
    {'format':'aws-cli','argv':['ec2','run-instances','--generate-cli-skeleton=input']},
    {'format':'aws-cli','argv':['ec2','run-instances','--endpoint-url=http://example.invalid']},
])
def test_unsafe_requests_never_start_a_process(monkeypatch,payload):
    def forbidden(*_,**__): raise AssertionError('No process should run')
    monkeypatch.setattr(validator.subprocess,'run',forbidden)
    with pytest.raises(ValueError):validator.validate(payload)


def test_cli_cannot_remove_forced_non_execution_mode(monkeypatch):
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs));return SimpleNamespace(returncode=0,stdout='{}')
    monkeypatch.setattr(validator.subprocess,'run',run)
    result=validator.validate({'format':'aws-cli','argv':['ec2','run-instances','--image-id','validation-only-placeholder']})
    args,kwargs=calls[0]
    assert args[-3:]==['--generate-cli-skeleton','output','--no-cli-pager']
    assert kwargs['shell'] is False and result['status']=='PASS'


def test_fourth_validation_attempt_never_contacts_worker(monkeypatch):
    calls=[]
    def request(*args,**kwargs):
        calls.append(args);return io.BytesIO(json.dumps({'status':'FAIL','checks':[]}).encode())
    monkeypatch.setattr(runtime.urllib.request,'urlopen',request)
    subject=runtime.Runtime(SimpleNamespace());state={}
    for count in range(1,4):
        result=subject.validate(state,{'action':'validate','format':'terraform','files':{'main.tf':'bad'}})
        assert result['attempt']==count and result['status']=='FAIL'
    with pytest.raises(ValueError,match='attempt limit'):
        subject.validate(state,{'action':'validate','format':'terraform','files':{'main.tf':'different'}})
    assert len(calls)==3
    subject.turns[('s','t')]=state
    heading=subject.label('Looks good',session_id='s',turn_id='t').split('**AI interpretation',1)[0]
    assert "FAIL" in heading and "attempt 3/3" in heading
