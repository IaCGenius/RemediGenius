"""Bounded scheduled collection and comparison. No model calls or customer writes."""
import hashlib
import json
import os
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from evidence_compare import compare_snapshots

CONFIG = Config(retries={'total_max_attempts': 1}, connect_timeout=5, read_timeout=100)


def handler(event, context):
    s3 = boto3.client('s3', config=CONFIG)
    lam = boto3.client('lambda', config=CONFIG)
    bucket, prefix = os.environ['BUCKET'], os.environ['PREFIX']
    checks = json.loads(os.environ['CHECKS'])
    if not 1 <= len(checks) <= 4:
        raise ValueError('Select one to four bounded checks')
    event_id = str(event.get('scheduled_time') or event.get('id') or context.aws_request_id)
    key = hashlib.sha256(event_id.encode()).hexdigest()
    def save(path, value, **extra):
        s3.put_object(Bucket=bucket, Key=prefix+'/'+path,
                      Body=json.dumps(value).encode(), ContentType='application/json', **extra)
    def load(path):
        try:
            exact = prefix+'/'+path
            listing = s3.list_objects_v2(Bucket=bucket, Prefix=exact, MaxKeys=1)
            if not any(item['Key'] == exact for item in listing.get('Contents', [])):
                return None
            response = s3.get_object(Bucket=bucket, Key=prefix+'/'+path)
            if response['ContentLength'] > 8000000:
                raise ValueError('Evidence exceeds scheduled comparison limit')
            return json.loads(response['Body'].read())
        except ClientError as exc:
            if exc.response['Error']['Code'] in ('NoSuchKey', '404'):
                return None
            raise
    try:
        save('scheduled/claims/'+key+'.json', {'event': event_id}, IfNoneMatch='*')
    except ClientError as exc:
        if exc.response['Error']['Code'] in ('PreconditionFailed', 'ConditionalRequestConflict'):
            return {'status': 'DUPLICATE', 'event': event_id}
        raise
    prior = load('scheduled/latest.json') or {}
    previous = {r['check_id']: r for r in prior.get('checks', [])}
    report = {'schema': 'ce-scheduled-check/1', 'event': event_id,
              'observed_at': datetime.now(timezone.utc).isoformat(), 'checks': [],
              'interval_hours': int(os.environ['INTERVAL_HOURS']),
              'origin': 'deterministic-no-model',
              'notice': 'Bounded snapshots, not a security verdict or verified remediation. No automatic closure.'}
    # Publish RUNNING first so an interrupted invocation cannot look successful.
    save('scheduled/latest.json', report | {'status': 'RUNNING'})
    for request in checks:
        signature = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        row = {'check_id': signature, 'request': request}
        try:
            response = lam.invoke(FunctionName=os.environ['READER'],
                                  Payload=json.dumps({'action': 'read', **request}).encode())
            value = json.loads(response['Payload'].read())
            if response.get('FunctionError'):
                raise RuntimeError('Read executor failed')
            row.update(result=value, comparison={'result': 'BASELINE', 'notice': 'No prior comparable run'})
            old_run = previous.get(signature, {}).get('result', {}).get('run_id')
            if old_run and value.get('run_id'):
                old = load('raw/'+old_run+'/aws-read.json')
                new = load('raw/'+value['run_id']+'/aws-read.json')
                row['comparison'] = compare_snapshots(old, new) if old and new else {'result': 'INCOMPARABLE'}
        except Exception as exc:
            row.update(error=type(exc).__name__, comparison={'result': 'INCOMPARABLE'})
        report['checks'].append(row)
    report['status'] = 'OK' if all(not r.get('error') and r.get('result', {}).get('status') == 'OK' for r in report['checks']) else 'PARTIAL'
    save('scheduled/runs/'+key+'.json', report, IfNoneMatch='*')
    save('scheduled/latest.json', report)
    return {'status': report['status'], 'path': 'scheduled/runs/'+key+'.json', 'checks': len(checks)}
