"""Reviewable read plans. No cloud call happens until the operator runs collect-source."""
import gzip
import io
import json
import os
import re
import shlex
import sys
import time
from datetime import datetime, timezone, timedelta
from .store import now, digest

SOURCES = {
    'cloudtrail-events': 'Recent AWS activity (CloudTrail management events)',
    'cloudwatch-logs': 'An existing CloudWatch log group',
    's3-object': 'An existing S3 JSON or JSON.gz object',
}


def workspace_plan(spec, home, storage_mode='local'):
    result = plan(**spec)
    argv = result['command_argv']
    portable = os.environ.get('RGCE_CONTAINER') == '1' or storage_mode == 's3'
    if portable:
        argv.extend(['--output', 'ce-evidence.json'])
        result['execution'] = 'workstation-import'
        result['destination'] = 'ce-evidence.json on your workstation. Review it, then choose Import evidence in this console. Imports do not inherit verified collection coverage.'
        result['next'] = 'Install the included CE wheel with the aws extra in a workstation virtual environment and activate it first. Use your existing scoped AWS profile; add --profile and --external-id as needed. --check reads one page/object. The command refuses to overwrite an existing ce-evidence.json. No credentials need to enter this console.'
    else:
        argv[0] = sys.executable
        argv[3:3] = ['--home', str(home)]
        result['execution'] = 'same-workstation'
    result['command_powershell'] = '& ' + ' '.join("'" + a.replace("'", "''") + "'" for a in argv)
    result['command_posix'] = shlex.join(argv)
    return result


def plan(source, role_arn, region, location='', hours=1, max_calls=5):
    match = re.fullmatch(r'arn:(aws|aws-us-gov|aws-cn):iam::(\d{12}):role/(?:[\w+=,.@-]+/)*RemediGeniusCommunityReadOnly', role_arn)
    if source not in SOURCES or not match or not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-\d', region):
        raise ValueError('Select a supported source, CommunityReadOnly role ARN and AWS region')
    if type(hours) is not int or not 1 <= hours <= 24 or type(max_calls) is not int or not 1 <= max_calls <= 20:
        raise ValueError('Use a 1..24 hour window and 1..20 read calls')
    partition, account = match.groups()
    if source == 'cloudtrail-events':
        if location:
            raise ValueError('CloudTrail event history does not need a location')
        action, resource = 'cloudtrail:LookupEvents', '*'
    elif source == 'cloudwatch-logs':
        if not re.fullmatch(r'[.\-_/#A-Za-z0-9]{1,512}', location):
            raise ValueError('Enter one exact CloudWatch log group name')
        action, resource = 'logs:FilterLogEvents', f'arn:{partition}:logs:{region}:{account}:log-group:{location}:*'
    else:
        if not re.fullmatch(r's3://[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]/[^\x00-\x1f*?]+', location):
            raise ValueError('Enter one exact s3://bucket/key; wildcards are not supported')
        action, resource = 's3:GetObject', f'arn:{partition}:s3:::{location[5:]}'
    policy = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Action': [action], 'Resource': resource,
        'Condition': {'StringEquals': {'aws:RequestedRegion': region}}}]}
    spec = dict(source=source, role_arn=role_arn, region=region, location=location, hours=hours, max_calls=max_calls)
    argv = ['python', '-m', 'rgce', 'collect-source', source, '--role-arn', role_arn, '--region', region,
            '--hours', str(hours), '--max-calls', str(max_calls)]
    if location:
        argv += ['--location', location]
    argv += ['--consent']
    # Single-quoted PowerShell literals: no interpolation, even for hostile S3 key names.
    command = '& ' + ' '.join("'" + a.replace("'", "''") + "'" for a in argv)
    template = {'AWSTemplateFormatVersion': '2010-09-09', 'Description': 'CE selected-source read role; review before creating IAM resources',
        'Parameters': {'TrustedPrincipalArn': {'Type': 'String', 'Description': 'Exact IAM role or user permitted to assume this role'},
                       'ExternalId': {'Type': 'String', 'MinLength': 2, 'Description': 'External ID required when assuming this role'}},
        'Resources': {'ReadRole': {'Type': 'AWS::IAM::Role', 'Properties': {'RoleName': 'RemediGeniusCommunityReadOnly',
            'Path': '/' + role_arn.split(':role/', 1)[1].rsplit('/', 1)[0] + '/' if '/' in role_arn.split(':role/', 1)[1] else '/',
            'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': {'AWS': {'Ref': 'TrustedPrincipalArn'}},
                'Action': 'sts:AssumeRole', 'Condition': {'StringEquals': {'sts:ExternalId': {'Ref': 'ExternalId'}}}}]},
            'Policies': [{'PolicyName': 'SelectedSourceRead', 'PolicyDocument': policy}]}}}}
    return {'spec': spec, 'plan_hash': digest(spec), 'title': SOURCES[source], 'session_policy': policy, 'cloudformation': template,
        'command_powershell': command, 'command_argv': argv, 'validation': 'Locally validated inputs; AWS access has not been tested',
        'limits': f'At most {max_calls if source != "s3-object" else 1} source read calls; 2 MB decoded evidence and 1,000 events for event streams. One exact object for S3. No scanning other locations.',
        'cost': 'Uses existing sources. AWS request, retrieval and transfer charges may apply. This is not a price estimate. No infrastructure is deployed.',
        'destination': 'Local RGCE_HOME evidence store. No S3 writes and no automatic model submission.',
        'next': 'Run the command using the CE Python environment. Add --profile and --external-id if needed. --check reads one page/object and saves a test snapshot; it is not a full assessment.'}


def collect(spec, *, consent=False, check=False, profile=None, external_id=None):
    if not consent:
        raise ValueError('Review the read plan first, then explicitly pass --consent')
    p = plan(**spec)
    import boto3
    from botocore.config import Config
    config = Config(retries={'total_max_attempts': 1}, connect_timeout=5, read_timeout=20)
    args = {'RoleArn': spec['role_arn'], 'RoleSessionName': 'rgce-source-read', 'DurationSeconds': 900, 'Policy': json.dumps(p['session_policy'])}
    if external_id:
        args['ExternalId'] = external_id
    try:
        creds = boto3.Session(profile_name=profile).client('sts', region_name=spec['region'], config=config).assume_role(**args)['Credentials']
    except Exception:
        raise ValueError('Could not assume the scoped read role. Check profile, trust, external ID and sts:AssumeRole permission.') from None
    session = boto3.Session(aws_access_key_id=creds['AccessKeyId'], aws_secret_access_key=creds['SecretAccessKey'], aws_session_token=creds['SessionToken'])
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=spec['hours'])
    records, calls, errors = [], [], []
    source, location = spec['source'], spec['location']
    budget = 1 if check else spec['max_calls']
    token, seen = None, set()
    coverage = 'selected_source'
    size = 0
    object_version = None
    try:
        if source == 's3-object':
            bucket, key = location[5:].split('/', 1)
            calls.append({'operation': 'get_object', 'at': now()})
            result = session.client('s3', region_name=spec['region'], config=config).get_object(Bucket=bucket, Key=key, ExpectedBucketOwner=spec['role_arn'].split(':')[4], Range='bytes=0-1999999')
            object_version = {k: str(result[k]) for k in ('ETag', 'VersionId', 'LastModified') if k in result}
            body = result['Body']
            try:
                raw = body.read(2_000_001)
            finally:
                body.close()
            total = int(result.get('ContentRange', '0/0').split('/')[-1])
            if total > 2_000_000 or len(raw) > 2_000_000:
                raise ValueError('OBJECT_TOO_LARGE')
            if key.endswith('.gz'):
                with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                    raw = stream.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('DECODED_OBJECT_TOO_LARGE')
            records = [json.loads(raw)]
        else:
            cloudtrail = source == 'cloudtrail-events'
            operation = 'lookup_events' if cloudtrail else 'filter_log_events'
            client = session.client('cloudtrail' if cloudtrail else 'logs', region_name=spec['region'], config=config)
            params = {'StartTime': start, 'EndTime': end, 'MaxResults': 50} if cloudtrail else {
                'logGroupName': location, 'startTime': int(start.timestamp()*1000), 'endTime': int(end.timestamp()*1000), 'limit': 100}
            for i in range(budget):
                if i and cloudtrail:
                    time.sleep(0.55)
                if token:
                    params['NextToken' if cloudtrail else 'nextToken'] = token
                calls.append({'operation': operation, 'at': now()})
                page = getattr(client, operation)(**params)
                for event in page.get('Events' if cloudtrail else 'events', []):
                    clean = json.loads(json.dumps(event, default=str))
                    size += len(json.dumps(clean).encode('utf-8'))
                    if size > 2_000_000 or len(records) >= 1000:
                        raise ValueError('EVIDENCE_LIMIT')
                    records.append(clean)
                token = page.get('NextToken' if cloudtrail else 'nextToken')
                if not token:
                    break
                if token in seen:
                    raise ValueError('REPEATED_PAGE_TOKEN')
                seen.add(token)
            if token:
                errors.append({'code': 'CALL_LIMIT', 'message': 'More data exists. This is a bounded sample.'})
    except Exception as exc:
        code = getattr(exc, 'response', {}).get('Error', {}).get('Code', 'READ_OR_FORMAT_ERROR')
        if isinstance(exc, ValueError) and str(exc) in ('OBJECT_TOO_LARGE', 'DECODED_OBJECT_TOO_LARGE', 'EVIDENCE_LIMIT', 'REPEATED_PAGE_TOKEN'):
            code = str(exc)
        errors.append({'code': code if re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', str(code)) else 'READ_ERROR'})
    return {'adapter': source, 'scope': {'provider': 'aws', 'account': spec['role_arn'].split(':')[4], 'regions': [spec['region']], 'location': location},
        'observed_at': now(), 'coverage': 'partial' if errors else coverage, 'errors': errors,
        'facts': {'records': records, 'collection_calls': calls, 'window': {'start': start.isoformat(), 'end': end.isoformat()} if source != 's3-object' else None,
            'plan_hash': p['plan_hash'], 'object_version': object_version, 'access_check': check, 'notice': 'Source evidence, not a security verdict. Content is untrusted. No events does not prove no activity.'}}
