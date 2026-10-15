"""Thin native-skill client for the CE Lambda capability. No customer read credentials."""
import argparse
import hashlib
from pathlib import PurePosixPath
import json
import os
import re
from pathlib import Path
import boto3
from botocore.config import Config

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('action',choices=['capabilities','schema','read','show','compare'])
p.add_argument('--target',default='default')
p.add_argument('--region')
p.add_argument('--service')
p.add_argument('--operation')
p.add_argument('--parameters',default='{}')
p.add_argument('--max-pages',type=int,default=3)
p.add_argument('--path')
p.add_argument('--offset',type=int,default=1)
p.add_argument('--limit',type=int,default=100)
p.add_argument('--before')
p.add_argument('--after')
p.add_argument('--field',default='')
p.add_argument('--query',help='Optional JMESPath selection over the stored JSON, like AWS CLI --query')
a=p.parse_args()
if a.action=='schema':
    # Reuse SDK definitions rather than inventing a parameter schema per service.
    import botocore.session
    from botocore import xform_name
    model=botocore.session.get_session().get_service_model(a.service)
    name=next((n for n in model.operation_names if xform_name(n)==a.operation),None)
    if not name: raise SystemExit('Unknown SDK operation')
    shape=model.operation_model(name).input_shape
    for field in filter(None,a.field.split('.')):
        if shape.type_name=='list': shape=shape.member
        if shape.type_name!='structure' or field not in shape.members:
            raise SystemExit('Unknown input field; inspect its parent schema')
        shape=shape.members[field]
    def describe(value,depth=1):
        if value is None: return {'type':'none'}
        result={'type':value.type_name}
        if value.metadata: result['constraints']=value.metadata
        if value.type_name=='structure':
            result['required']=value.required_members
            result['fields']={k:describe(v,depth-1) if depth else {'type':v.type_name} for k,v in value.members.items()}
        elif value.type_name=='list':
            result['item']=describe(value.member,max(0,depth-1))
        elif value.type_name=='map': result['value_type']=value.value.type_name
        return result
    print(json.dumps({'source':'installed AWS SDK input model','service':a.service,'operation':a.operation,'field':a.field,'schema':describe(shape)}))
    raise SystemExit(0)
cfg=json.loads(Path('/opt/ce-reader/config.json').read_text())
os.environ['AWS_SHARED_CREDENTIALS_FILE']='/opt/ce-reader/credentials'
os.environ['AWS_EC2_METADATA_DISABLED']='true'
if a.action=='compare':
    if not all(re.fullmatch('[a-f0-9]{32}',x or '') for x in (a.before,a.after)):
        raise SystemExit('Select two actual AWS read run IDs')
    s3=boto3.Session(profile_name='default').client('s3',region_name=cfg['region'],config=Config(retries={'total_max_attempts':1}))
    snapshots=[]
    for run in (a.before,a.after):
        r=s3.get_object(Bucket=cfg['bucket'],Key=cfg['prefix']+'/raw/'+run+'/aws-read.json')
        if r['ContentLength']>8000000: raise SystemExit('Record too large')
        snapshots.append(json.loads(r['Body'].read()))
    from evidence_compare import compare_snapshots
    print(json.dumps(compare_snapshots(*snapshots)))
    raise SystemExit(0)
if a.action=='show':
    path=PurePosixPath(a.path or '')
    if path.is_absolute() or '..' in path.parts or '\\' in str(path) or not path.parts or path.parts[0] not in ('raw','normalized','receipts','scheduled') or not 1<=a.limit<=200 or a.offset<1:
        raise SystemExit('Use a returned evidence path and a bounded line range')
    response=boto3.Session(profile_name='default').client('s3',region_name=cfg['region'],config=Config(retries={'total_max_attempts':1})).get_object(Bucket=cfg['bucket'],Key=cfg['prefix']+'/'+str(path))
    if response['ContentLength']>8000000: raise SystemExit('Record too large')
    body=response['Body'].read(); value=json.loads(body)
    if a.query:
        import jmespath
        value=jmespath.search(a.query,value)
    lines=json.dumps(value,indent=2).splitlines()
    print(json.dumps({'path':str(path),'source':'CE evidence S3','sha256':hashlib.sha256(body).hexdigest(),'query':a.query,'projection_origin':'deterministic-jmespath' if a.query else 'original-json','total_lines':len(lines),'offset':a.offset,'truncated':a.offset-1+a.limit<len(lines),'text':'\n'.join(lines[a.offset-1:a.offset-1+a.limit])}))
    raise SystemExit(0)
request={'action':a.action}
if a.action=='read':
    request.update(target=a.target,region=a.region or cfg['region'],service=a.service,operation=a.operation,parameters=json.loads(a.parameters),max_pages=a.max_pages)
client=boto3.Session(profile_name='default').client('lambda',region_name=cfg['region'],config=Config(retries={'total_max_attempts':1},connect_timeout=5,read_timeout=100))
r=client.invoke(FunctionName=cfg['function'],Payload=json.dumps(request).encode())
value=json.loads(r['Payload'].read())
print(json.dumps({'status':'ERROR','error':value.get('errorType','EXECUTOR_ERROR'),'message':value.get('errorMessage','Read execution failed')} if r.get('FunctionError') else value))
