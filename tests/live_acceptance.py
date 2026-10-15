"""Explicit operator-run AWS acceptance test. Not collected by pytest.

Uses only the isolated deploy/aws-test stack and its private local parameters.
Raw evidence and AWS identifiers stay under .rgce; stdout is a compact test summary.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from rgce import core
from rgce.adapters import collect_aws
from rgce.onboarding import collect, plan
from rgce.store import Store, digest, now

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.rgce/aws-acceptance'


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('phase',choices=['before','after','reader','paused'])
    ap.add_argument('--run',action='store_true',required=True)
    args=ap.parse_args()
    cfg=json.loads((LOCAL/'test.tfvars.json').read_text(encoding='utf-8'))
    raw=json.loads(subprocess.check_output(['terraform','-chdir='+str(ROOT/'deploy/aws-test'),'output','-json']))
    outputs={k:v['value'] for k,v in raw.items()}
    settings=Config(connect_timeout=5,read_timeout=70,retries={'total_max_attempts':1})
    operator=boto3.Session()
    assert operator.client('sts',config=settings).get_caller_identity()['Account']==cfg['account_id']
    assert outputs['bucket']==cfg['fixture_name'] and outputs['log_group']=='/rgce-test/'+cfg['fixture_name']
    store=Store(LOCAL/'evidence')
    report={'phase':args.phase,'at':now(),'checks':{},'records':{}}
    role=outputs['role_arn'];region=cfg.get('region','us-east-1')
    def client(service):return operator.client(service,region_name=region,config=settings)
    def source(kind,location='',**extra):
        return {'source':kind,'role_arn':role,'region':region,'location':location,'hours':1,'max_calls':5,**extra}
    def deny(name,fn):
        try:fn()
        except ClientError as e:
            code=e.response['Error']['Code']
            assert code in ('AccessDenied','AccessDeniedException','UnauthorizedOperation','TooManyRequestsException'),code
            report['checks'][name]={'passed':True,'aws_code':code}
        else:raise AssertionError(name+' unexpectedly succeeded')
    if args.phase in ('before','after'):
        if args.phase=='before':
            logs=client('logs')
            try:logs.create_log_stream(logGroupName=outputs['log_group'],logStreamName='synthetic')
            except logs.exceptions.ResourceAlreadyExistsException:pass
            logs.put_log_events(logGroupName=outputs['log_group'],logStreamName='synthetic',logEvents=[{'timestamp':int(time.time()*1000),'message':json.dumps({'synthetic':True,'application':'CE-test','event':'Example successful sign-in'})}])
        envelope=collect_aws('sg',role,cfg['external_id'],[region],max_calls=50,group_ids=[outputs['security_group']])
        assert not envelope['errors'],envelope['errors']
        evidence=core.ingest(store,envelope,authority='collector');assessment=core.assess(store,evidence['id'])
        found=[f for f in assessment['body']['findings'] if f['resource_id'].endswith('/'+outputs['security_group'])]
        report['records']['sg']=assessment['id']
        report['checks']['sg_fixture']={'passed':bool(found) if args.phase=='before' else not found,'matching_rules':[f['rule_id'] for f in found]}
        assert report['checks']['sg_fixture']['passed']
        if args.phase=='after':
            before=json.loads((LOCAL/'before.json').read_text())['records']['sg']
            result=core.compare(store,before,assessment['id'])
            assert result['comparable'],result['limitations']
            cleared=[x for x in result['no_longer_observed'] if outputs['security_group'] in x['row_id']]
            assert cleared and all(x['status']=='RULE_NO_LONGER_MATCHES' for x in cleared)
            (LOCAL/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            report['checks']['rule_clearance']={'passed':True,'comparable':True,'status':'RULE_NO_LONGER_MATCHES'}
        else:
            for name,spec in [('cloudtrail',source('cloudtrail-events')),('logs',source('cloudwatch-logs',outputs['log_group'])),('s3',source('s3-object','s3://'+outputs['bucket']+'/inputs/sample.json'))]:
                data=collect(spec,consent=True,external_id=cfg['external_id'])
                assert not [e for e in data['errors'] if e['code']!='CALL_LIMIT'],data['errors']
                assert data['facts']['records'],name+' returned no records'
                r=core.ingest(store,data,authority='collector')
                report['records'][name]=r['id']
                report['checks'][name]={'passed':True,'count':len(data['facts']['records']),'coverage':data['coverage']}
            hub=collect_aws('securityhub-asff',role,cfg['external_id'],[region],max_calls=5)
            r=core.ingest(store,hub,authority='collector')
            a=core.assess(store,r['id']);report['records']['securityhub']=a['id']
            report['checks']['securityhub']={'passed':not hub['errors'],'errors':hub['errors'],'count':len(hub['facts']['Findings']),'coverage':hub['coverage']}
            deny('incorrect_external_id',lambda:client('sts').assume_role(RoleArn=role,RoleSessionName='rgce-negative',ExternalId='wrong-synthetic-id',DurationSeconds=900))
            c=client('sts').assume_role(RoleArn=role,RoleSessionName='rgce-permission-test',ExternalId=cfg['external_id'],DurationSeconds=900)['Credentials']
            scoped=boto3.Session(aws_access_key_id=c['AccessKeyId'],aws_secret_access_key=c['SecretAccessKey'],aws_session_token=c['SessionToken'])
            s3=scoped.client('s3',region_name=region,config=settings)
            deny('unselected_object',lambda:s3.get_object(Bucket=outputs['bucket'],Key='denied/not-authorized.json'))
            deny('source_role_cannot_write',lambda:s3.put_object(Bucket=outputs['bucket'],Key='denied/should-not-write.json',Body=b'SYNTHETIC'))
    else:
        function=outputs['reader_function']
        spec=source('s3-object','s3://'+outputs['bucket']+'/inputs/sample.json',max_calls=1)
        event={'consent':True,'plan_hash':plan(**spec)['plan_hash']}
        if args.phase=='paused':
            deny('paused_reader_cannot_start',lambda:client('lambda').invoke(FunctionName=function,InvocationType='RequestResponse',Payload=json.dumps(event).encode()))
        else:
            denied=client('lambda').invoke(FunctionName=function,Payload=b'{"consent":false,"plan_hash":"wrong"}')
            assert denied.get('FunctionError'),'Missing consent must fail'
            report['checks']['lambda_requires_consent']={'passed':True}
            r=client('lambda').invoke(FunctionName=function,Payload=json.dumps(event).encode())
            body=json.loads(r['Payload'].read())
            if r.get('FunctionError'):raise AssertionError(body)
            receipt=json.loads(client('s3').get_object(Bucket=outputs['bucket'],Key=body['key'])['Body'].read())
            assert receipt['evidence_hash']==digest(receipt['evidence'])
            assert receipt['code_sha256']==__import__('hashlib').sha256((ROOT/'modules/approved-reader/build/reader.zip').read_bytes()).hexdigest()
            assert not receipt['evidence']['errors'],receipt['evidence']['errors']
            record=core.ingest(store,receipt['evidence'],authority='collector')
            report['records']['lambda_source']=record['id']
            report['checks']['lambda_read_and_s3_receipt']={'passed':True,'python':receipt['python'],'boto3':receipt['boto3'],'evidence_hash_verified':True,'code_hash_verified':True}
            (LOCAL/'lambda-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    (LOCAL/(args.phase+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'phase':args.phase,'checks':report['checks'],'evidence_saved_locally':True},indent=2))


if __name__=='__main__':main()
