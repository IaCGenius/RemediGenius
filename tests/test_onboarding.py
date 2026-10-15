import gzip
import io
import json
import pytest
from fastapi.testclient import TestClient
from rgce import core
from rgce.app import create_app
from rgce.onboarding import plan, collect
from rgce.store import Store

ROLE = 'arn:aws:iam::111122223333:role/RemediGeniusCommunityReadOnly'


def spec(source='cloudwatch-logs', location='/app/payments', max_calls=5):
    return dict(source=source, role_arn=ROLE, region='us-east-1', location=location, hours=1, max_calls=max_calls)


def mock_cloud(monkeypatch, pages=None, raw=None, fail=False, total=None):
    import boto3
    calls=[]
    class Client:
        def assume_role(self, **kw):
            calls.append(('assume',kw))
            return {'Credentials': {'AccessKeyId':'test','SecretAccessKey':'test','SessionToken':'test'}}
        def filter_log_events(self, **kw):
            calls.append(('logs',kw.copy()))
            if fail: raise RuntimeError('secret-not-for-display')
            return pages.pop(0)
        def lookup_events(self, **kw):
            calls.append(('trail',kw.copy()))
            return pages.pop(0)
        def get_object(self, **kw):
            calls.append(('s3',kw))
            return {'Body': io.BytesIO(raw), 'ContentRange': 'bytes 0-9/'+str(total or len(raw))}
    class Session:
        def __init__(self, **kw): self.kw=kw
        def client(self, service, **kw):
            if service != 'sts': assert self.kw['aws_session_token']=='test'
            return Client()
    monkeypatch.setattr(boto3, 'Session', Session)
    monkeypatch.setattr('rgce.onboarding.time.sleep', lambda _:None)
    return calls


def test_consent_before_network(monkeypatch):
    calls=mock_cloud(monkeypatch)
    with pytest.raises(ValueError,match='consent'): collect(spec())
    assert not calls


def test_empty_pages_continue_and_policy_scoped(monkeypatch,tmp_path):
    calls=mock_cloud(monkeypatch,pages=[{'events': [], 'nextToken':'next'}, {'events':[{'message':'example'}]}])
    data=collect(spec(),consent=True)
    assert len(data['facts']['records'])==1 and data['coverage']=='selected_source'
    assert calls[2][1]['nextToken']=='next'
    policy=json.loads(calls[0][1]['Policy'])['Statement'][0]
    assert policy['Action']==['logs:FilterLogEvents']
    assert policy['Resource'].endswith('log-group:/app/payments:*')
    store=Store(tmp_path); record=core.ingest(store,data,authority='collector')
    with pytest.raises(ValueError,match='no deterministic'): core.assess(store,record['id'])


def test_one_page_check_records_partial(monkeypatch):
    mock_cloud(monkeypatch,pages=[{'Events':[], 'NextToken':'next'}])
    data=collect(spec('cloudtrail-events',''),consent=True,check=True)
    assert data['coverage']=='partial' and data['facts']['access_check']
    assert data['errors'][0]['code']=='CALL_LIMIT'


def test_errors_do_not_leak(monkeypatch):
    mock_cloud(monkeypatch,fail=True)
    data=collect(spec(),consent=True)
    assert data['coverage']=='partial' and 'secret-not' not in json.dumps(data)


@pytest.mark.parametrize('oversize', [False,True])
def test_s3_gzip_and_decoded_bound(monkeypatch,oversize):
    raw=gzip.compress(json.dumps({'Records':['a'*(2_000_001 if oversize else 10)]}).encode())
    calls=mock_cloud(monkeypatch,raw=raw)
    data=collect(spec('s3-object','s3://example-bucket/a.json.gz'),consent=True)
    assert calls[1][1]['ExpectedBucketOwner']=='111122223333'
    assert (data['coverage']=='partial')==oversize
    assert bool(data['facts']['records']) != oversize


def test_oversize_s3_not_silently_parsed(monkeypatch):
    mock_cloud(monkeypatch,raw=b'{}',total=3_000_000)
    data=collect(spec('s3-object','s3://example-bucket/a.json'),consent=True)
    assert data['errors'][0]['code']=='OBJECT_TOO_LARGE'


def test_repeated_token_terminates(monkeypatch):
    calls=mock_cloud(monkeypatch,pages=[{'events':[],'nextToken':'a'},{'events':[],'nextToken':'a'}])
    data=collect(spec(),consent=True)
    assert len(calls)==3 and data['errors'][0]['code']=='REPEATED_PAGE_TOKEN'


def test_plan_quotes_and_template_policy():
    p=plan(**spec('s3-object',"s3://example-bucket/a'$(echo test).json"))
    assert "a''$(echo test).json'" in p['command_powershell']
    props=p['cloudformation']['Resources']['ReadRole']['Properties']
    assert props['Policies'][0]['PolicyDocument']==p['session_policy']
    assert 'ExternalId' in props['AssumeRolePolicyDocument']['Statement'][0]['Condition']['StringEquals']['sts:ExternalId']['Ref']
    with pytest.raises(ValueError): plan(**spec('s3-object','s3://example-bucket/*'))
    bad=spec(); bad['role_arn']=ROLE.replace('RemediGeniusCommunityReadOnly','Admin')
    with pytest.raises(ValueError): plan(**bad)


def test_api_plan_does_not_collect(monkeypatch,tmp_path):
    calls=mock_cloud(monkeypatch)
    client=TestClient(create_app(tmp_path))
    token=client.get('/api/session').json()['token']
    assert client.post('/api/onboarding/plan',json=spec()).status_code==403
    response=client.post('/api/onboarding/plan',json=spec(),headers={'x-rgce-token':token})
    assert response.status_code==200 and not calls


def test_workspace_command_targets_same_store(tmp_path):
    from rgce.onboarding import workspace_plan
    p=workspace_plan(spec(),tmp_path)
    assert p['command_argv'][3:5]==['--home',str(tmp_path)]
    assert p['command_argv'][5]=='collect-source'


def test_requests_match_aws_sdk_shapes(monkeypatch):
    import botocore.session
    from botocore.validate import validate_parameters
    session=botocore.session.get_session()
    for source,location,pages,raw in [
        ('cloudtrail-events','',[{'Events':[]}],None),
        ('cloudwatch-logs','/app',[{'events':[]}],None),
        ('s3-object','s3://example-bucket/a.json',None,b'{}')]:
        calls=mock_cloud(monkeypatch,pages=pages,raw=raw)
        collect(spec(source,location),consent=True)
        for kind,params in calls:
            service,operation={'assume':('sts','AssumeRole'),'trail':('cloudtrail','LookupEvents'),'logs':('logs','FilterLogEvents'),'s3':('s3','GetObject')}[kind]
            validate_parameters(params,session.get_service_model(service).operation_model(operation).input_shape)


def test_role_path_preserved_in_template():
    options=spec(); options['role_arn']=ROLE.replace('role/','role/team/')
    p=plan(**options)
    assert p['cloudformation']['Resources']['ReadRole']['Properties']['Path']=='/team/'


@pytest.mark.parametrize('container,s3', [(True,False),(False,True)])
def test_remote_console_plan_uses_portable_file(monkeypatch, tmp_path, container, s3):
    from rgce.onboarding import workspace_plan
    monkeypatch.setenv('RGCE_CONTAINER','1' if container else '0')
    p=workspace_plan(spec('s3-object',"s3://example-bucket/a'$(touch nope).json"),tmp_path,'s3' if s3 else 'local')
    assert p['execution']=='workstation-import'
    assert p['command_argv'][0]=='python'
    assert '--home' not in p['command_argv']
    assert p['command_argv'][-2:]==['--output','ce-evidence.json']
    import shlex
    assert shlex.split(p['command_posix'])==p['command_argv']
    assert str(tmp_path) not in p['command_powershell']


def test_portable_collection_bypasses_storage_and_requires_consent(monkeypatch,tmp_path,capsys):
    import sys
    from rgce.cli import main
    monkeypatch.setenv('RGCE_STORAGE_BUCKET','unreachable-storage-must-not-open')
    calls=mock_cloud(monkeypatch,raw=b'{"synthetic":"selected fixture"}')
    target=tmp_path/'captured.json'
    args=['rgce','collect-source','s3-object','--role-arn',ROLE,'--region','us-east-1',
          '--location','s3://example-bucket/a.json','--output',str(target)]
    monkeypatch.setattr(sys,'argv',args)
    with pytest.raises(SystemExit): main()
    assert not calls and not target.exists()
    monkeypatch.setattr(sys,'argv',args+['--consent'])
    main()
    payload=json.loads(target.read_text())
    assert payload['facts']['records']==[{'synthetic':'selected fixture'}]
    assert len(calls)==2
    output=capsys.readouterr().out
    assert 'selected fixture' not in output and 'SecretAccessKey' not in output
    # Retry must refuse overwrite before another AWS call.
    with pytest.raises(SystemExit): main()
    assert len(calls)==2
    monkeypatch.delenv('RGCE_STORAGE_BUCKET')
    record=core.ingest(Store(tmp_path/'destination'),payload)
    assert record['body']['coverage']=='unknown'
    assert record['body']['authority']=='user_import'
