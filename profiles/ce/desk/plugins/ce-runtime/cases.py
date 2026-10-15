"""Small tracking adapter over native Hermes Kanban; no worker dispatch."""
import hashlib
import json
import sqlite3
from pathlib import Path


def case_action(params):
    from hermes_cli import kanban_db as kb
    import hermes_yaml as yaml
    home = Path('/opt/data')
    config = yaml.safe_load((home/'config.yaml').read_text()) or {}
    board = config.get('kanban', {})
    if board.get('dispatch_in_gateway') is not False or board.get('review_dispatch') is not False:
        raise ValueError('Manual tracking requires Kanban dispatch and review dispatch disabled')
    action = params.get('action')
    if action not in ('list','show','create','comment','wait','verify','close','archive'):
        raise ValueError('Unknown case action')
    db = kb.init_db(home/'kanban.db')
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    def view(t):
        return {k:getattr(t,k,None) for k in ('id','title','body','status','created_at','updated_at')}
    try:
        if action == 'list':
            return {'status':'OK','cases':[view(t) for t in kb.list_tasks(conn,tenant='ce-cases',include_archived=bool(params.get('include_archived')),limit=50)]}
        if action == 'create':
            identity = params.get('identity','')
            if not identity or len(identity)>2000 or not params.get('body') or not params.get('title'):
                raise ValueError('Supply exact account/region/resource/finding identity, title and evidence-linked body')
            task_id = kb.create_task(conn, title=params['title'][:200], body=params['body'][:18000],
                                     assignee='ce-desk', created_by='ce-desk', tenant='ce-cases',
                                     triage=True, initial_status='running', max_retries=0,
                                     idempotency_key='ce:'+hashlib.sha256(identity.encode()).hexdigest(),
                                     completion_contract='local-only')
            return {'status':'SAVED','case':view(kb.get_task(conn,task_id)), 'notice':'Local tracking only; no cloud changes or worker dispatch.'}
        task_id = params.get('id','')
        task = kb.get_task(conn,task_id)
        if not task or task.tenant != 'ce-cases':
            raise ValueError('Select a CE case from list')
        if action == 'show':
            return {'status':'OK','case':view(task),'comments':[{'author':c.author,'body':c.body} for c in kb.list_comments(conn,task_id)[-30:]]}
        if task.status == 'running':
            raise ValueError('Unexpected runnable task; inspect dispatch configuration before changing it')
        note = params.get('note','')
        if not isinstance(note,str) or not note.strip() or len(note)>18000:
            raise ValueError('Supply a bounded reason/evidence note')
        if action == 'archive' and task.status != 'done':
            raise ValueError('Conclude the case with an explicit disposition before archiving')
        if action == 'close':
            disposition = params.get('disposition')
            if disposition not in ('verified_fix','operator_false_positive','accepted_risk','retired','duplicate','cancelled'):
                raise ValueError('Select an explicit closure disposition')
            if disposition in ('verified_fix','retired') and not params.get('evidence'):
                raise ValueError('Fresh evidence reference required; absence or failed reads are not proof')
            if disposition == 'accepted_risk' and not params.get('review_date'):
                raise ValueError('Accepted risk needs an operator review/expiry date')
            note = json.dumps({k:params.get(k) for k in ('disposition','note','evidence','review_date')})
        if task.status == 'triage' and action in ('wait','verify','close'):
            kb.specify_triage_task(conn,task_id,author='ce-desk')
            task = kb.get_task(conn,task_id)
        kb.add_comment(conn,task_id,'ce-desk',note)
        changed = True
        if action == 'wait': changed = kb.block_task(conn,task_id,reason=note)
        elif action == 'verify':
            if task.status == 'blocked': kb.unblock_task(conn,task_id)
            elif task.status == 'triage': kb.specify_triage_task(conn,task_id,author='ce-desk')
            changed = kb.request_review(conn,task_id,summary=note,force=True)
        elif action == 'close': changed = kb.complete_task(conn,task_id,summary=note,force=True,fire_lifecycle_hook=False)
        elif action == 'archive': changed = kb.archive_task(conn,task_id)
        return {'status':'SAVED','transition_changed':bool(changed),'case':view(kb.get_task(conn,task_id)),
                'notice':'Local operator/agent record, not independent verification or AWS suppression.'}
    finally:
        conn.close()
