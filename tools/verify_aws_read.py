"""Exercise a deployed CE read executor with real AWS data, without model calls.

Requires boto3 and an operator AWS identity allowed to invoke the function and
read the CE evidence prefix. Reports are private; do not commit account records.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import boto3
from botocore.config import Config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('function', 'bucket', 'prefix', 'region', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--target', default='default')
    args = parser.parse_args()
    config = Config(retries={'total_max_attempts': 1}, read_timeout=100)
    session = boto3.Session(region_name=args.region)
    executor, s3 = session.client('lambda', config=config), session.client('s3', config=config)

    def invoke(payload):
        response = executor.invoke(FunctionName=args.function, Payload=json.dumps(payload).encode())
        result = json.loads(response['Payload'].read())
        if response.get('FunctionError'):
            raise RuntimeError('Executor failed: ' + result.get('errorType', 'unknown'))
        return result

    capabilities = invoke({'action': 'capabilities'})
    if args.target not in capabilities['targets']:
        raise SystemExit('Target is not configured')
    now = datetime.now(timezone.utc)
    cases = [
        ('ec2', 'describe_instances', {'MaxResults': 20}),
        ('cloudtrail', 'lookup_events', {'StartTime': (now-timedelta(days=5)).isoformat(),
            'EndTime': now.isoformat(), 'LookupAttributes': [
                {'AttributeKey': 'EventSource', 'AttributeValue': 'ec2.amazonaws.com'}], 'MaxResults': 50}),
        ('securityhub', 'get_findings', {'Filters': {'RecordState': [
            {'Value': 'ACTIVE', 'Comparison': 'EQUALS'}]}, 'MaxResults': 30}),
    ]
    report = {'checked_at': now.isoformat(), 'target': args.target, 'checks': []}
    for service, operation, parameters in cases:
        result = invoke({'action': 'read', 'target': args.target, 'region': args.region,
            'service': service, 'operation': operation, 'parameters': parameters, 'max_pages': 3})
        checked = 0
        for record in result['files']:
            response = s3.get_object(Bucket=args.bucket, Key=args.prefix.rstrip('/')+'/'+record['path'])
            if response['ContentLength'] > 8_000_000:
                raise RuntimeError('Unexpected evidence object size')
            body = response['Body'].read()
            if hashlib.sha256(body).hexdigest() != record['sha256']:
                raise RuntimeError('Evidence hash mismatch')
            checked += 1
        check = {'service': service, 'operation': operation, 'status': result['status'],
            'run_id': result['run_id'], 'observed_at': result['observed_at'],
            'pages': result['pages_returned'], 'has_more': result['has_more'],
            'errors': result['errors'], 'verified_objects': checked}
        report['checks'].append(check)
        print(json.dumps(check), flush=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    # An ERROR is not a successful source check, even if its failure receipt is valid.
    return 1 if any(c['status'] == 'ERROR' for c in report['checks']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
