"""Constructed SDK boundary tests; these are not live AWS acceptance evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError


def load_executor():
    path = Path(__file__).resolve().parents[1] / 'deploy/collector/executor.py'
    spec = importlib.util.spec_from_file_location('read_executor_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('outcome', ['running', 'empty', 'denied'])
def test_config_status_preserves_source_and_durable_receipt(monkeypatch, outcome):
    module = load_executor()
    objects, calls = {}, []
    expected = {'ConfigurationRecordersStatus': [] if outcome == 'empty' else [
        {'name': 'unit-test-recorder', 'recording': True, 'lastStatus': 'SUCCESS'}]}

    class Config:
        def can_paginate(self, operation):
            assert operation == 'describe_configuration_recorder_status'
            return False

        def describe_configuration_recorder_status(self, **parameters):
            calls.append(parameters)
            if outcome == 'denied':
                raise ClientError({'Error': {'Code': 'AccessDeniedException'}},
                                  'DescribeConfigurationRecorderStatus')
            return expected

    class Storage:
        def put_object(self, **kwargs):
            objects[kwargs['Key']] = kwargs['Body']

    monkeypatch.setattr(module.boto3, 'Session', lambda: SimpleNamespace(client=lambda *a, **kw: Config()))
    monkeypatch.setattr(module.boto3, 'client', lambda *a, **kw: Storage())
    for key, value in {'TARGETS': json.dumps({'default': {'regions': ['us-east-1'], 'account_id': 'unit-test'}}),
                       'ACCOUNT_ID': 'unit-test', 'BUCKET': 'unit-test', 'PREFIX': 'evidence'}.items():
        monkeypatch.setenv(key, value)
    request = {'action': 'read', 'target': 'default', 'region': 'us-east-1',
               'service': 'config', 'operation': 'describe_configuration_recorder_status',
               'parameters': {}, 'max_pages': 1}
    result = module.handler(request, None)
    assert calls == [{}]
    assert result['status'] == ('ERROR' if outcome == 'denied' else 'OK')
    raw_bytes = objects['evidence/' + result['raw_path']]
    raw = json.loads(raw_bytes)
    assert raw['pages'] == ([] if outcome == 'denied' else [expected])
    assert raw['scope']['operation'] == request['operation']
    assert raw['scope']['region'] == 'us-east-1'
    assert raw['observed_at']
    assert [e['code'] for e in raw['errors']] == (['AccessDeniedException'] if outcome == 'denied' else [])
    receipt = json.loads(objects['evidence/' + result['receipt_path']])
    assert receipt['files'][0]['sha256'] == hashlib.sha256(raw_bytes).hexdigest()
    assert result['summary']['collection_counts'] == (
        {} if outcome == 'denied' else {'ConfigurationRecordersStatus':len(expected['ConfigurationRecordersStatus'])})
    assert 'verdict' not in result['summary']


def test_config_status_does_not_admit_recording_mutations(monkeypatch):
    module = load_executor()
    monkeypatch.setenv('TARGETS', json.dumps({'default': {'regions': ['us-east-1'], 'account_id': 'unit-test'}}))
    monkeypatch.setattr(module.boto3, 'Session', lambda: pytest.fail('Rejected request reached AWS'))
    for operation in ('start_configuration_recorder', 'stop_configuration_recorder', 'delete_configuration_recorder'):
        result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                                 'service': 'config', 'operation': operation}, None)
        assert result['status'] == 'ERROR' and result['pages_returned'] == 0
        assert result['errors'][0]['code'] == 'WRITE_OPERATION'
        assert result['stop_reason'] == 'WRITE_OPERATION'


@pytest.mark.parametrize('budget,expected', [(None, 1), (2, 2)])
def test_default_and_explicit_page_budgets_stop_sdk_iteration(monkeypatch, budget, expected):
    module = load_executor()
    fetched = []
    class Paginator:
        def paginate(self, **parameters):
            for n in range(5):
                fetched.append(n)
                yield {'Findings': [], 'NextToken': str(n + 1)}
    sdk = SimpleNamespace(can_paginate=lambda operation: True,
                          get_paginator=lambda operation: Paginator())
    monkeypatch.setattr(module.boto3, 'Session', lambda: SimpleNamespace(client=lambda *a, **kw: sdk))
    monkeypatch.setattr(module.boto3, 'client', lambda *a, **kw: SimpleNamespace(put_object=lambda **kw: None))
    for key, value in {'TARGETS': json.dumps({'default': {'regions': ['us-east-1'], 'account_id': 'unit-test'}}),
                       'ACCOUNT_ID': 'unit-test', 'BUCKET': 'unit-test', 'PREFIX': 'evidence'}.items():
        monkeypatch.setenv(key, value)
    request = {'action': 'read', 'target': 'default', 'region': 'us-east-1',
               'service': 'securityhub', 'operation': 'get_findings', 'parameters': {'MaxResults': 2}}
    if budget is not None:
        request['max_pages'] = budget
    result = module.handler(request, None)
    assert len(fetched) == expected == result['pages_returned'] == result['scope']['max_pages']
    assert result['status'] == 'PARTIAL' and result['has_more'] is True


def test_cloudcontrol_cannot_choose_other_role_or_private_handler(monkeypatch):
    module=load_executor()
    monkeypatch.setenv('TARGETS',json.dumps({'default':{'regions':['us-east-1'],'account_id':'unit-test'}}))
    monkeypatch.setattr(module.boto3,'Session',lambda:pytest.fail('Rejected request reached AWS'))
    for params in ({'TypeName':'Private::Handler::Resource'},
                   {'TypeName':'AWS::EC2::Instance','RoleArn':'arn:aws:iam::123456789012:role/Admin'}):
        with pytest.raises(ValueError,match='configured read identity'):
            module.handler({'action':'read','target':'default','region':'us-east-1','service':'cloudcontrol',
                            'operation':'list_resources','parameters':params},None)


def test_continuation_is_last_retained_page_not_omitted_page(monkeypatch):
    module=load_executor()
    class Paginator:
        _pagination_cfg={'input_token':'NextToken','output_token':'NextToken'}
        def paginate(self,**kwargs):
            yield {'Resources':[{'id':'first'}],'NextToken':'after-first'}
            yield {'Resources':[{'id':'x'*4000000}],'NextToken':'after-omitted'}
    sdk=SimpleNamespace(can_paginate=lambda op:True,get_paginator=lambda op:Paginator())
    monkeypatch.setattr(module.boto3,'Session',lambda:SimpleNamespace(client=lambda *a,**k:sdk))
    monkeypatch.setattr(module.boto3,'client',lambda *a,**k:SimpleNamespace(put_object=lambda **kw:None))
    for k,v in {'TARGETS':json.dumps({'default':{'regions':['us-east-1'],'account_id':'unit-test'}}),
                'ACCOUNT_ID':'unit-test','BUCKET':'unit-test','PREFIX':'evidence'}.items():monkeypatch.setenv(k,v)
    result=module.handler({'action':'read','target':'default','region':'us-east-1','service':'cloudcontrol',
        'operation':'list_resources','parameters':{'TypeName':'AWS::EC2::Instance'},'max_pages':10},None)
    assert result['pages_returned']==1 and result['has_more']
    assert result['stop_reason']=='BYTE_LIMIT'
    assert result['continuation_parameters']['NextToken']=='after-first'
