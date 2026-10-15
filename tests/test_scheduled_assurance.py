"""Failure semantics, not simulated AWS acceptance results."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace


def test_comparison_failure_cannot_report_all_clear(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root/'profiles/ce/desk/skills/ce-aws-read/scripts'))
    spec = importlib.util.spec_from_file_location('scheduled_check', root/'modules/assurance-schedule/check.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    request = {'target':'default','service':'config','operation':'describe_configuration_recorders','max_pages':1}
    signature = module.hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
    objects = {'prefix/scheduled/latest.json':json.dumps({'checks':[{'check_id':signature,'result':{'run_id':'prior'}}]}),
               'prefix/raw/prior/aws-read.json':'{"present":true}', 'prefix/raw/current/aws-read.json':'{"present":true}'}
    class Storage:
        def put_object(self, **kw): objects[kw['Key']] = kw['Body'].decode()
        def list_objects_v2(self, **kw): return {'Contents':[{'Key':kw['Prefix']}] if kw['Prefix'] in objects else []}
        def get_object(self, **kw):
            body = objects[kw['Key']].encode()
            return {'ContentLength':len(body),'Body':io.BytesIO(body)}
    class Reader:
        def invoke(self, **kw): return {'Payload':io.BytesIO(b'{"status":"OK","run_id":"current"}')}
    monkeypatch.setattr(module.boto3,'client',lambda name,**kw: Storage() if name=='s3' else Reader())
    def broken(*args): raise ValueError('Comparison unavailable')
    monkeypatch.setattr(module,'compare_snapshots',broken)
    for key,value in {'BUCKET':'test','PREFIX':'prefix','READER':'test-reader','CHECKS':json.dumps([request]),'INTERVAL_HOURS':'24'}.items():
        monkeypatch.setenv(key,value)
    result = module.handler({'scheduled_time':'test-event'}, SimpleNamespace(aws_request_id='test-request'))
    assert result['status']=='PARTIAL'
    report=json.loads(objects['prefix/scheduled/latest.json'])
    assert report['checks'][0]['comparison']['result']=='INCOMPARABLE'
    assert report['checks'][0]['error']=='ValueError'
