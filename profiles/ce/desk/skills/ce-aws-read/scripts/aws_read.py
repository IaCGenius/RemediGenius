"""Thin native-skill client for the local CE collector. No AWS credentials."""
import argparse
import json
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('action',choices=['capabilities','schema','read','show','compare'])
p.add_argument('--target',default='default')
p.add_argument('--region')
p.add_argument('--service')
p.add_argument('--operation')
p.add_argument('--parameters',default='{}')
p.add_argument('--max-pages',type=int,default=1)
p.add_argument('--path')
p.add_argument('--offset',type=int,default=1)
p.add_argument('--limit',type=int,default=100)
p.add_argument('--before')
p.add_argument('--after')
p.add_argument('--field',default='')
p.add_argument('--query',help='Optional JMESPath selection over the stored JSON, like AWS CLI --query')
a=p.parse_args()
cfg=json.loads(Path('/opt/ce-reader/config.json').read_text())
if cfg.get('transport') == 'unix':
    import http.client
    import socket
    class LocalConnection(http.client.HTTPConnection):
        def connect(self):
            self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self.sock.settimeout(105)
            self.sock.connect(cfg['socket'])
    request={'action':a.action}
    if a.action=='read':
        request.update(target=a.target,region=a.region or cfg['region'],service=a.service,operation=a.operation,
                       parameters=json.loads(a.parameters),max_pages=a.max_pages)
    elif a.action=='schema': request.update(service=a.service,operation=a.operation,field=a.field)
    elif a.action=='show':
        request.update(path=a.path,offset=a.offset,limit=a.limit)
        if a.query: request['query']=a.query
    elif a.action=='compare': request.update(before=a.before,after=a.after)
    connection=LocalConnection('localhost',timeout=105)
    connection.request('POST','/execute',body=json.dumps(request),headers={'Content-Type':'application/json'})
    response=connection.getresponse()
    body=response.read(8000001)
    if len(body)>8000000: raise SystemExit('Collector response exceeds limit')
    print(json.dumps(json.loads(body)))
    connection.close()
    raise SystemExit(0)
raise SystemExit('Local collector transport is not configured; use the current CE launcher')
