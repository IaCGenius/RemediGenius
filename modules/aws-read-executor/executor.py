"""Reusable SDK read execution with independently configured IAM and durable receipts.
No shell, generated code, credentials in responses, or arbitrary endpoint selection.
"""
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ParamValidationError

OPERATIONS = json.loads((Path(__file__).parent / 'operations.json').read_text())
CONFIG = Config(retries={'total_max_attempts': 1}, connect_timeout=3, read_timeout=10)

def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()

def handler(event, context):
    allowed = {'action','target','region','service','operation','parameters','max_pages'}
    if not isinstance(event, dict) or set(event)-allowed:
        raise ValueError('Use the documented AWS read request')
    targets = json.loads(os.environ['TARGETS'])
    if event.get('action') == 'capabilities':
        return {'targets':{k:{'regions':v['regions'],'account_id':v['account_id']} for k,v in targets.items()},
                'operations':{k:list(v) for k,v in OPERATIONS.items()},
                'max_pages':10,'max_bytes':4000000,'notice':'Configured scope; each call still must pass actual IAM permissions.'}
    if event.get('action') != 'read':
        raise ValueError('Supported actions: capabilities, read')
    required = ('target','region','service','operation')
    if any(not isinstance(event.get(key), str) or not event[key] for key in required):
        raise ValueError('Read requires target, region, service and operation strings')
    if event['target'] not in targets:
        raise ValueError('Unknown target; use a configured target from capabilities')
    target = targets[event['target']]
    region, service, operation = event['region'], event['service'], event['operation']
    if region not in target['regions'] or operation not in OPERATIONS.get(service, {}):
        raise ValueError('Operation or region outside configured scope')
    parameters = event.get('parameters', {})
    pages_limit = event.get('max_pages', 1)
    if not isinstance(parameters, dict) or type(pages_limit) is not int or not 1 <= pages_limit <= 10 or len(encoded(parameters)) > 16000:
        raise ValueError('Invalid parameters or page budget')
    if service == 'cloudcontrol':
        if not str(parameters.get('TypeName','')).startswith('AWS::') or any(
                k in parameters for k in ('RoleArn','TypeVersionId')):
            raise ValueError('Cloud Control requires an AWS:: type and configured read identity; role/version overrides are not allowed')
    if service == 'cloudtrail' and operation == 'lookup_events':
        parameters = dict(parameters)
        for field in ('StartTime','EndTime'):
            if not isinstance(parameters.get(field), str):
                raise ValueError('CloudTrail lookup requires StartTime and EndTime ISO-8601 strings')
            try:
                parameters[field] = datetime.fromisoformat(parameters[field].replace('Z','+00:00'))
            except ValueError as exc:
                raise ValueError('CloudTrail StartTime and EndTime must be valid ISO-8601 strings') from exc
        start, end = parameters['StartTime'], parameters['EndTime']
        if start.tzinfo is None or end.tzinfo is None or not 0 < (end-start).total_seconds() <= 90*86400:
            raise ValueError('Use an explicit timezone-aware window of at most 90 days')
    if not target.get('role_arn') and target['account_id'] != os.environ['ACCOUNT_ID']:
        raise ValueError('A different account requires an explicit configured role')
    if target.get('role_arn') and target['role_arn'].split(':')[4] != target['account_id']:
        raise ValueError('Configured role/account mismatch')
    run = uuid.uuid4().hex
    observed = datetime.now(timezone.utc).isoformat()
    pages, errors, total, partial = [], [], 0, False
    continuation, stop_reason = None, None
    began = time.monotonic()
    try:
        session = boto3.Session()
        if target.get('role_arn'):
            args = {'RoleArn':target['role_arn'],'RoleSessionName':'rgce-read','DurationSeconds':900,
                    'Policy':json.dumps({'Version':'2012-10-17','Statement':[{'Effect':'Allow','Action':OPERATIONS[service][operation],'Resource':'*'}]})}
            if target.get('external_id'): args['ExternalId'] = target['external_id']
            if service == 'cloudcontrol':
                partition = target['role_arn'].split(':')[1]
                # Allow downstream metadata reads, intersected with the target role.
                args['PolicyArns'] = [{'arn':f'arn:{partition}:iam::aws:policy/{p}'} for p in
                                     ('SecurityAudit','job-function/ViewOnlyAccess')]
            creds = session.client('sts', config=CONFIG).assume_role(**args)['Credentials']
            session = boto3.Session(aws_access_key_id=creds['AccessKeyId'],aws_secret_access_key=creds['SecretAccessKey'],aws_session_token=creds['SessionToken'])
        client = session.client(service, region_name=region, config=CONFIG)
        if client.can_paginate(operation):
            paginator = client.get_paginator(operation)
            iterator = iter(paginator.paginate(**parameters))
        else:
            iterator = iter([getattr(client, operation)(**parameters)])
        for n in range(pages_limit):
            if time.monotonic()-began > 55 or (context and context.get_remaining_time_in_millis() < 20000):
                partial = True
                stop_reason = 'TIME_LIMIT'
                break
            if n and service == 'cloudtrail': time.sleep(.6)
            try: page = next(iterator)
            except StopIteration: break
            total += len(encoded(page))
            if total > 4000000:
                errors.append({'code':'BYTE_LIMIT','notice':'Last page omitted; narrower selection required'})
                partial = True
                stop_reason = 'BYTE_LIMIT'
                break
            pages.append(page)
            # Preserve service tokens and label a bounded pagination stop honestly.
            partial = any(page.get(k) for k in ('NextToken','nextToken','Marker','NextMarker','ContinuationToken','NextContinuationToken')) or bool(page.get('IsTruncated'))
            if partial and client.can_paginate(operation):
                import jmespath
                cfg = getattr(paginator, '_pagination_cfg', {})
                inputs, outputs = cfg.get('input_token', []), cfg.get('output_token', [])
                inputs = [inputs] if isinstance(inputs,str) else inputs
                outputs = [outputs] if isinstance(outputs,str) else outputs
                tokens = {key:jmespath.search(expr,page) for key,expr in zip(inputs,outputs)}
                if tokens and all(value is not None for value in tokens.values()):
                    continuation = {**parameters, **tokens}
            if not partial: continuation = None
            if not partial: break
    except ParamValidationError as exc:
        errors.append({'code':'ParamValidationError','message':str(exc)[:3000],
                       'notice':'Inspect the SDK input schema; one corrected attempt is permitted.'})
    except ClientError as exc:
        errors.append({'code':exc.response.get('Error',{}).get('Code','AWS_ERROR')})
    except Exception as exc:
        errors.append({'code':type(exc).__name__})
    if partial and not stop_reason: stop_reason = 'PAGE_LIMIT'
    scope = {'target':event['target'],'execution_account':os.environ['ACCOUNT_ID'],'account_id':target['account_id'], 'region':region,
             'service':service,'operation':operation,'parameters':parameters,'max_pages':pages_limit,
             'notice':'Administrator APIs may include member-account records. Preserve source IDs and check actual membership/coverage.'}
    result = {'schema_version':'rgce-aws-read/1','run_id':run,'observed_at':observed,'scope':scope,
              'status':'ERROR' if errors and not pages else 'PARTIAL' if errors or partial else 'OK',
              'pages_returned':len(pages),'has_more':partial,'errors':errors,'pages':pages,
              'stop_reason':stop_reason,'continuation_parameters':continuation,
              'notice':'Source response, not a security verdict. OK describes this bounded request, not organization-wide coverage.'}
    s3 = boto3.client('s3',config=CONFIG)
    files=[]
    def save(path, value, layer):
        body=encoded(value)
        s3.put_object(Bucket=os.environ['BUCKET'],Key=os.environ['PREFIX']+'/'+path,Body=body,ContentType='application/json',IfNoneMatch='*')
        files.append({'path':path,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),'layer':layer})
    raw_path=f'raw/{run}/aws-read.json'
    save(raw_path,result,'raw')
    # Deterministic activity extraction; same CloudTrail capability for any EventSource/identity/resource filter.
    summary = {}
    if service in ('config','cloudcontrol','cloudformation','resource-explorer-2'):
        collections = {}
        for page in pages:
            for key,value in page.items():
                if isinstance(value,list): collections.setdefault(key,[]).extend(value)
        summary = {'collection_counts':{k:len(v) for k,v in collections.items()},
                   'records_preview':{k:v[:15] for k,v in collections.items()},
                   'preview_truncated':any(len(v)>15 for v in collections.values())}
        if service == 'cloudcontrol' and operation == 'get_resource':
            summary['resources'] = [p.get('ResourceDescription',{}) for p in pages]
        if service == 'cloudformation' and operation == 'describe_type':
            summary['schemas'] = []
            for p in pages:
                schema=json.loads(p.get('Schema','{}'))
                summary['schemas'].append({k:schema.get(k) for k in
                    ('typeName','primaryIdentifier','readOnlyProperties','writeOnlyProperties','handlers')})
    if service=='cloudtrail' and operation=='lookup_events':
        events={e['EventId']:e for p in pages for e in p.get('Events',[]) if e.get('EventId')}
        timeline=[]
        for e in events.values():
            row={k:e.get(k) for k in ('EventId','EventTime','EventName','EventSource','Username','Resources','ReadOnly')}
            try:
                detail=json.loads(e.get('CloudTrailEvent','{}'))
                if not isinstance(detail,dict): raise ValueError('Event body is not an object')
                row.update(ErrorCode=detail.get('errorCode'),ErrorMessage=detail.get('errorMessage'),
                           SourceIPAddress=detail.get('sourceIPAddress'),UserIdentity=detail.get('userIdentity'),
                           BodyParseStatus='OK')
            except (ValueError,TypeError):
                row.update(BodyParseStatus='ERROR',ErrorCode=None)
            timeline.append(row)
        timeline.sort(key=lambda e:str(e['EventTime']))
        counts = {}
        for e in timeline: counts[e['EventName']] = counts.get(e['EventName'],0)+1
        summary = {'event_count':len(timeline),'event_name_counts':counts,
                   'earliest_event_time':timeline[0]['EventTime'] if timeline else None,
                   'latest_event_time':timeline[-1]['EventTime'] if timeline else None,
                   'api_error_count':sum(bool(e.get('ErrorCode')) for e in timeline),
                   'body_parse_error_count':sum(e['BodyParseStatus']!='OK' for e in timeline),
                   'error_events':[e for e in timeline if e.get('ErrorCode')][:20],
                   'timeline_preview':timeline[:20],'preview_truncated':len(timeline)>20}
        save(f'normalized/{run}/timeline.json',{'scope':scope,'observed_at':observed,'count':len(timeline),'has_more':partial,'errors':errors,'events':timeline},'normalized')
    if service=='securityhub' and operation=='get_findings':
        findings={ (f.get('ProductArn',''),f.get('Id','')): f for p in pages for f in p.get('Findings',[]) }
        counts={}
        items=[]
        for f in findings.values():
            severity=f.get('Severity',{}).get('Label','UNKNOWN')
            counts[severity]=counts.get(severity,0)+1
            items.append({k:f.get(k) for k in ('Id','ProductArn','AwsAccountId','Region','Title','Severity','Workflow','RecordState','UpdatedAt','Resources','Compliance','Remediation')})
        summary={'finding_count':len(items),'severity_counts':counts,'findings_preview':items[:5],'preview_truncated':len(items)>5}
        save(f'normalized/{run}/findings.json',{'scope':scope,'observed_at':observed,'count':len(items),'severity_counts':counts,'has_more':partial,'errors':errors,'findings':items},'normalized')
    receipt=f'receipts/{run}.json'
    save(receipt,{'run_id':run,'observed_at':observed,'producer':'deterministic-boto3','boto3_version':boto3.__version__,
                  'collector_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':scope,'status':result['status'],'files':list(files)},'receipts')
    catalog={'schema_version':'rgce-source-catalog/1','run_id':run,'observed_at':observed,'account_id':target['account_id'],'region':region,
             'scope':f'Bounded {service}.{operation} query; see receipt for exact scope', 'sources':[], 'files':files,'receipt_path':receipt,
             'limitations':['Only the selected query was executed; use prior receipts for other sources.','Source records may include sensitive identifiers; expose only what the question requires.']}
    s3.put_object(Bucket=os.environ['BUCKET'],Key=os.environ['PREFIX']+'/catalog.json',Body=encoded(catalog),ContentType='application/json')
    return json.loads(encoded({k:result[k] for k in ('run_id','observed_at','scope','status','pages_returned','has_more','errors','stop_reason','continuation_parameters')} | {'receipt_path':receipt,'raw_path':raw_path,'files':files,'summary':summary}))
