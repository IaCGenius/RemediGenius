"""Explicit real-S3 persistence and fresh-container recovery. No model calls."""
import argparse
import json
import os
import subprocess
import uuid
from pathlib import Path
import boto3
from rgce import core, knowledge, documents
from rgce.store import Store
from rgce.object_storage import ObjectStorage, migrate_local
from rgce.onboarding import collect


def main():
    p=argparse.ArgumentParser(); p.add_argument('--run',required=True,action='store_true'); p.parse_args()
    root=Path(__file__).resolve().parents[1]; private=root/'.rgce/aws-acceptance'
    cfg=json.loads((private/'test.tfvars.json').read_text(encoding='utf-8'))
    region=cfg.get('region','us-east-1'); prefix='ce-workspace/test-'+uuid.uuid4().hex
    credentials=boto3.client('sts',region_name=region).assume_role(
        RoleArn=f"arn:aws:iam::{cfg['account_id']}:role/RemediGeniusCommunityWorkspaceTest",
        RoleSessionName='ce-storage-acceptance', ExternalId=cfg['external_id'],DurationSeconds=900)['Credentials']
    env={k:v for k,v in os.environ.items() if not k.startswith('AWS_')}
    values={'AWS_ACCESS_KEY_ID':credentials['AccessKeyId'],'AWS_SECRET_ACCESS_KEY':credentials['SecretAccessKey'],
        'AWS_SESSION_TOKEN':credentials['SessionToken'],'AWS_DEFAULT_REGION':region,'AWS_EC2_METADATA_DISABLED':'true',
        'RGCE_STORAGE_BUCKET':cfg['fixture_name'],'RGCE_STORAGE_PREFIX':prefix}
    session=boto3.Session(aws_access_key_id=credentials['AccessKeyId'],aws_secret_access_key=credentials['SecretAccessKey'],aws_session_token=credentials['SessionToken'],region_name=region)
    client=session.client('s3'); backend=ObjectStorage(cfg['fixture_name'],prefix,client)
    store=Store(private/('storage-'+uuid.uuid4().hex),backend)
    source=collect({'source':'s3-object','role_arn':f"arn:aws:iam::{cfg['account_id']}:role/RemediGeniusCommunityReadOnly",
        'region':region,'location':f"s3://{cfg['fixture_name']}/inputs/sample.json",'hours':1,'max_calls':1},consent=True,external_id=cfg['external_id'])
    assert not source['errors']
    live=core.ingest(store,source,authority='collector')
    demo=core.demo(store); assessment=demo['before']; finding=assessment['body']['findings'][0]
    doc=documents.intake(store,'synthetic-policy.md',b'# Synthetic acceptance policy\nOnly approved VPN access.','policies')
    draft=knowledge.simple_draft(store,'Synthetic baseline: only approved VPN access.',title='Baseline',source_ids=[doc['id']])
    baseline=knowledge.publish(store,draft['id'],draft['id'],'Synthetic operator')
    draft=knowledge.simple_draft(store,'Synthetic test-only variation; does not alter severity.',title='Variation',baseline_id=baseline['id'],scope={'resource':finding['resource_id']})
    variation=knowledge.publish(store,draft['id'],draft['id'],'Synthetic operator')
    expected=core.investigation(store,assessment['id'],finding['row_id'])
    core.proposal(store,assessment['id'],finding['row_id'])
    report={}
    local=Store(private/('local-migration-'+uuid.uuid4().hex))
    core.demo(local)
    documents.intake(local,'migration.md',b'# Synthetic migration document')
    migration_target=ObjectStorage(cfg['fixture_name'],prefix+'-migration',client)
    migration=migrate_local(local,migration_target)
    assert migration['source_retained'] and migration['originals_verified']==1
    assert migrate_local(local,migration_target)==migration
    recovered=Store(private/('migration-recovered-'+uuid.uuid4().hex),migration_target)
    assert len(recovered.list())==migration['records_verified']
    report['migration_verified']=True
    report['migration_retry_verified']=True
    for name,call in (
        ('delete_denied',lambda:client.delete_object(Bucket=cfg['fixture_name'],Key=prefix+'/records/'+assessment['id']+'.json')),
        ('outside_prefix_denied',lambda:client.get_object(Bucket=cfg['fixture_name'],Key='inputs/sample.json')),
        ('unconditional_overwrite_denied',lambda:client.put_object(Bucket=cfg['fixture_name'],Key=prefix+'/bad',Body=b'bad'))):
        try: call()
        except client.exceptions.ClientError as exc:
            assert exc.response['Error']['Code']=='AccessDenied'; report[name]=True
        else: raise AssertionError(name)
    # Entirely fresh tmpfs /data: no host SQLite, originals, AWS config or source checkout mounted.
    code='''import json,sys,hashlib
from pathlib import Path
from rgce.store import Store
from rgce import core,knowledge
from rgce.workspace import export_workspace,verify_workspace
x=json.load(sys.stdin);s=Store('/data');a=s.get(x['assessment']);d=s.get(x['document'])
assert s.get(x['live_source'])['body']==x['live_body']
actual=core.investigation(s,a['id'],x['row'])
actual['knowledge_context']=knowledge.resolve(s,a,actual['finding'],at=x['investigation']['knowledge_context']['evaluated_at'])
assert actual==x['investigation'], 'Recovered evidence or knowledge differs at the same evaluation time'
assert s.get(x['variation'])['kind']=='concept_publication'
assert core.compare(s,a['id'],x['after'])['comparable']
p=Path('/data/knowledge/originals')/d['body']['source_sha256']/'source.md'
assert hashlib.sha256(p.read_bytes()).hexdigest()==d['body']['source_sha256']
receipt=json.loads((Path('/data/knowledge/documents')/d['id']/'receipt.json').read_text())
assert receipt['id']==d['id'] and receipt['body']['source_sha256']==d['body']['source_sha256']
assert verify_workspace(export_workspace(s,[a['id']])['folder'])['status']=='verified'
print(json.dumps({'fresh_container_recovery':True,'live_source_preserved':True,'knowledge_variation_preserved':True,'original_restored':True,'document_receipt_restored':True,'reassessment':True,'export_verified':True}))
'''
    payload={'assessment':assessment['id'],'row':finding['row_id'],'document':doc['id'],'variation':variation['id'],'after':demo['after']['id'],'investigation':expected,'live_source':live['id'],'live_body':live['body']}
    command=['docker','run','--rm','-i','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
        '--tmpfs','/data:rw,uid=10001,gid=10001,mode=0700','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--entrypoint','python']
    for key in values: command.extend(['-e',key])
    command.extend(['remedigenius-ce:0.1.0rc9','-c',code])
    run=subprocess.run(command,input=json.dumps(payload),text=True,encoding='utf-8',capture_output=True,env={**env,**values},timeout=180)
    (private/'rc9-storage-container.stderr').write_text(run.stderr,encoding='utf-8')
    if run.returncode: raise RuntimeError('Recovery failed; see private stderr')
    report.update(json.loads(run.stdout)); report['objects_verified']=len(list(backend.records()))
    (private/'rc9-storage-proof.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
