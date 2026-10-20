"""Local deterministic execution boundary, exposed only through a Unix socket."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
from http.server import BaseHTTPRequestHandler
import threading
import time
import boto3
import jmespath
from botocore.config import Config
from executor import handler as execute
from evidence_compare import compare_snapshots

CONFIG = Config(retries={'total_max_attempts': 1}, connect_timeout=3, read_timeout=10)
LOCK = threading.Lock()


def stored(path):
    p=PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts or '\\' in path or not p.parts or p.parts[0] not in ('raw','normalized','receipts','scheduled'):
        raise ValueError('Select a returned evidence path')
    r=boto3.client('s3',config=CONFIG).get_object(Bucket=os.environ['BUCKET'],Key=os.environ['PREFIX']+'/'+str(p))
    if r['ContentLength'] > 8000000: raise ValueError('Record exceeds read limit')
    body=r['Body'].read(8000001)
    if len(body)>8000000: raise ValueError('Record exceeds read limit')
    return body


def dispatch(request):
    if not isinstance(request,dict): raise ValueError('Expected a JSON object')
    action=request.get('action')
    if action=='schema':
        if set(request)-{'action','service','operation','field'}: raise ValueError('Unknown schema parameter')
        import botocore.session
        from botocore import xform_name
        model=botocore.session.get_session().get_service_model(request['service'])
        name=next((n for n in model.operation_names if xform_name(n)==request['operation']),None)
        if not name: raise ValueError('Unknown SDK operation')
        shape=model.operation_model(name).input_shape
        for field in filter(None,request.get('field','').split('.')):
            if shape is not None and shape.type_name=='list': shape=shape.member
            if shape is None or shape.type_name!='structure' or field not in shape.members:
                return {'status':'ERROR','errors':[{'code':'UNKNOWN_SCHEMA_FIELD'}],'available_fields':list(shape.members) if shape is not None and shape.type_name=='structure' else []}
            shape=shape.members[field]
        def describe(value,depth=1):
            if value is None:return {'type':'none'}
            result={'type':value.type_name}
            if value.metadata:result['constraints']=value.metadata
            if value.type_name=='structure':
                result['required']=value.required_members
                result['fields']={k:describe(v,depth-1) if depth else {'type':v.type_name} for k,v in value.members.items()}
            elif value.type_name=='list':result['item']=describe(value.member,max(0,depth-1))
            elif value.type_name=='map':result['value_type']=value.value.type_name
            return result
        return {'source':'pinned CE collector AWS SDK input model','service':request['service'],'operation':request['operation'],'field':request.get('field',''),'schema':describe(shape)}
    if action in ('read','capabilities'):
        return execute(request,None)
    if action=='show':
        if set(request)-{'action','path','offset','limit','query'}: raise ValueError('Unknown show parameter')
        offset,limit=request.get('offset',1),request.get('limit',100)
        if type(offset)!=int or offset<1 or type(limit)!=int or not 1<=limit<=200: raise ValueError('Invalid line range')
        body=stored(request.get('path',''));value=json.loads(body)
        query=request.get('query')
        if query:
            if not isinstance(query,str) or len(query)>4000: raise ValueError('Invalid projection')
            value=jmespath.search(query,value)
        lines=json.dumps(value,indent=2).splitlines()
        return {'path':request['path'],'source':'CE evidence S3','sha256':hashlib.sha256(body).hexdigest(),
                'query':query,'projection_origin':'deterministic-jmespath' if query else 'original-json',
                'total_lines':len(lines),'offset':offset,'truncated':offset-1+limit<len(lines),
                'text':'\n'.join(lines[offset-1:offset-1+limit])}
    if action=='compare':
        if set(request)-{'action','before','after'}: raise ValueError('Unknown comparison parameter')
        ids=[request.get(k,'') for k in ('before','after')]
        if not all(isinstance(v,str) and re.fullmatch('[a-f0-9]{32}',v) for v in ids): raise ValueError('Use actual run IDs')
        return compare_snapshots(*(json.loads(stored('raw/'+v+'/aws-read.json')) for v in ids))
    raise ValueError('Action not admitted')


class Request(BaseHTTPRequestHandler):
    def log_message(self,*args): pass  # no request bodies, prompts or credentials in HTTP logs
    def do_POST(self):
        self.connection.settimeout(110)
        status=200
        try:
            if self.path!='/execute': raise ValueError('Unknown endpoint')
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=32000: raise ValueError('Request exceeds limit')
            request=json.loads(self.rfile.read(size))
            with LOCK: result=dispatch(request)
        except Exception as exc:
            status=400
            # Do not return SDK exception payloads or credential-provider errors.
            result={'status':'ERROR','error':type(exc).__name__,'message':'Collector request failed; check scope, parameters and operator logs.'}
        body=json.dumps(result,default=str).encode()
        self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


def scheduled_loop():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from scheduled import handler as check
    while True:
        try:
            prior=None
            try: prior=json.loads(stored('scheduled/latest.json'))
            except Exception as exc:
                if getattr(exc,'response',{}).get('Error',{}).get('Code') not in ('NoSuchKey','404'): raise
            now=datetime.now(timezone.utc)
            checks=json.loads(os.environ['CHECKS'])
            changed=prior and [r['request'] for r in prior.get('checks',[])]!=checks
            due=not prior or changed or (now-datetime.fromisoformat(prior['observed_at'])).total_seconds()>=int(os.environ.get('INTERVAL_HOURS','24'))*3600
            if due:
                with LOCK:
                    check({'scheduled_time':now.isoformat()},SimpleNamespace(aws_request_id='local'))
                print('Scheduled bounded check completed; details in S3',flush=True)
        except Exception as exc: print('Scheduled check failed: '+type(exc).__name__,flush=True)
        time.sleep(60)


def serve():
    from socketserver import UnixStreamServer
    identity=boto3.client('sts',config=CONFIG).get_caller_identity()
    if identity['Account']!=os.environ['ACCOUNT_ID']: raise SystemExit('Collector account mismatch')
    directory=Path('/run/ce-collector');directory.mkdir(exist_ok=True)
    path=directory/'collector.sock'
    if path.exists(): path.unlink()
    server=UnixStreamServer(str(path),Request)
    os.chmod(path,0o660)
    (directory/'config.json').write_text(json.dumps({'transport':'unix','socket':'/opt/ce-reader/collector.sock',
        'region':os.environ['AWS_DEFAULT_REGION'],'bucket':os.environ['BUCKET'],'prefix':os.environ['PREFIX']}))
    print('Collector ready; verified execution account; no credential values logged',flush=True)
    if os.environ.get('CHECKS'): threading.Thread(target=scheduled_loop,daemon=True).start()
    if os.environ.get('STATE_CHECKPOINT_SECONDS'): threading.Thread(target=checkpoint_loop,daemon=True).start()
    server.serve_forever()


def checkpoint_loop():
    from state_store import backup
    interval=max(120,int(os.environ['STATE_CHECKPOINT_SECONDS']))
    while True:
        time.sleep(interval)
        try:
            result=backup('/state')
            print('State checkpoint '+result['status']+' at '+result['created_at'],flush=True)
        except Exception as exc:
            print('State checkpoint failed: '+type(exc).__name__+'; previous checkpoint retained',flush=True)


if __name__=='__main__': serve()
