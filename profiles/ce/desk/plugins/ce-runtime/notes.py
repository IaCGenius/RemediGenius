"""Bounded, operator-confirmed Markdown notes. No cloud writes or model calls."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


def stage(home, params):
    if set(params)-{'action','title','scope','collection','content'}: raise ValueError('Unknown note field')
    for field,limit in [('title',200),('scope',800),('content',16000)]:
        value=params.get(field)
        if not isinstance(value,str) or not value.strip() or len(value)>limit:
            raise ValueError('Supply a bounded '+field)
    collection=params.get('collection','org/context')
    if not re.fullmatch(r'[a-z0-9_-]+(?:/[a-z0-9_-]+){0,3}',collection):raise ValueError('Use a plain collection name')
    record={k:params[k] for k in ('title','scope','content')}
    record['collection']=collection
    ident=hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()[:24]
    folder=Path(home)/'ce-knowledge/drafts';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(ident+'.json')
    if not path.exists():
        path.write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8');path.chmod(0o600)
    return {'status':'DRAFT','id':ident,**record,
            'next_step':'Review the exact text and scope. To use it in future investigations, send: publish knowledge '+ident,
            'notice':'Not yet selected knowledge. This operator assertion will not change AWS state.'}


def publish(home, params, user_message):
    if set(params)-{'action','id'}:raise ValueError('Unknown publish field')
    ident=params.get('id','')
    if not re.fullmatch('[a-f0-9]{24}',ident):raise ValueError('Use the staged note ID')
    if user_message.strip().lower()!='publish knowledge '+ident:
        return {'status':'NEEDS_OPERATOR_CONFIRMATION','next_step':'Send exactly: publish knowledge '+ident}
    root=Path(home)/'ce-knowledge'
    record=json.loads((root/'drafts'/(ident+'.json')).read_text(encoding='utf-8'))
    if hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()[:24]!=ident:
        raise ValueError('Draft changed; stage it again')
    folder=root/'notes'/record['collection']/ident;folder.mkdir(parents=True,exist_ok=True)
    content=record['content'].encode('utf-8')
    metadata={k:record[k] for k in ('title','scope','collection')}
    metadata.update(content_sha256=hashlib.sha256(content).hexdigest(),origin='operator-confirmed-chat-note',
        imported_at=datetime.now(timezone.utc).isoformat(),meaning='Organizational assertion, not independently verified AWS evidence')
    for filename,body in [('content.md',content),('metadata.json',json.dumps(metadata).encode())]:
        path=folder/filename
        if not path.exists():path.write_bytes(body);path.chmod(0o600)
    return {'status':'PUBLISHED','path':'notes/'+record['collection']+'/'+ident+'/content.md',
            'notice':'Selected for future knowledge lookup. A running assessment keeps its original knowledge snapshot.'}


def index(home):
    root=Path(home)/'ce-knowledge'
    lines=[]
    for path in sorted((root/'notes').glob('**/metadata.json')):
        record=json.loads(path.read_text(encoding='utf-8'))
        lines.append('- '+(path.parent/'content.md').relative_to(root).as_posix()+' '+json.dumps({k:record[k] for k in ('title','scope')},ensure_ascii=False))
    return '\n'.join(lines)
