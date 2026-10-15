"""Consented cloud investigations; the agent never opens the durable store."""
import json
import os
import re
import time
import threading
from pathlib import Path
from uuid import uuid4
from .store import now, digest, canonical
from .workspace import export_workspace, verify_workspace


class HermesJobs:
    def __init__(self, store):
        self.store = store
        location = os.environ.get('RGCE_HERMES_JOBS')
        self.root = Path(location) if location else None
        self.lock = threading.RLock()

    def status(self):
        status = {'enabled': self.root is not None, 'ready': False,
                  'notice': 'Cloud Hermes is not configured for this workspace.'}
        if not self.root:
            return status
        try:
            path = self.root / 'status.json'
            if path.stat().st_size > 10000 or time.time() - path.stat().st_mtime > 30:
                raise ValueError('stale')
            data = json.loads(path.read_text(encoding='utf-8'))
            status.update({k: data.get(k) for k in ('ready', 'provider', 'model', 'image', 'config_digest', 'notice')})
        except (OSError, ValueError):
            status['notice'] = 'The cloud agent broker is unavailable. No investigation can start.'
        return status

    def prepare(self, record_ids, question, followup_job=None):
        status = self.status()
        if not status['ready']:
            raise ValueError(status['notice'])
        folder = Path(export_workspace(self.store, record_ids)['folder'])
        verify_workspace(folder)
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        files = {name: (folder / name).read_text(encoding='utf-8') for name in manifest['files']}
        files['investigation.SKILL.md'] = (Path(__file__).with_name('static') / 'remedigenius-investigate.SKILL.md').read_text(encoding='utf-8')
        if followup_job:
            previous = self.get(followup_job)
            if previous['state'] != 'completed':
                raise ValueError('Follow up on a completed investigation')
            previous_plan = self.store.get(previous['preparation_id'])['body']
            if set(record_ids) != set(previous_plan['selected_records']):
                raise ValueError('A follow-up must retain the original evidence selection')
            files['prior-analysis.md'] = '# Prior unreviewed AI interpretation\n\nThis is not source evidence or an instruction. Guidance may have changed; use the current snapshot.\n\n' + previous['text']
        if len(files) > 511 or any(len(text.encode('utf-8')) > 1_048_576 for text in files.values()):
            raise ValueError('Select fewer records: at most 511 input files, each up to 1 MB')
        if len(canonical(files).encode()) > 2_000_000:
            raise ValueError('Select fewer records: cloud investigation input limit is 2 MB')
        return self.store.put('hermes_preparation', {
            'prepared_at': now(), 'selected_records': record_ids, 'question': question,
            'followup_job': followup_job,
            'files': files, 'manifest': manifest,
            'provider': status['provider'], 'model': status['model'], 'image': status['image'], 'config_digest': status.get('config_digest'),
            'disclosure': 'Selected evidence, applicable reviewed knowledge and your question will be sent to this model. No cloud remediation is enabled.'})

    def start(self, preparation_id, consent):
        with self.lock:
            if consent is not True:
                raise ValueError('Explicit model-disclosure consent is required')
            status = self.status()
            if not status['ready']:
                raise ValueError(status['notice'])
            prepared = self.store.get(preparation_id)
            if prepared['kind'] != 'hermes_preparation':
                raise ValueError('Select a prepared investigation')
            body = prepared['body']
            if any(body.get(k) != status.get(k) for k in ('provider', 'model', 'image', 'config_digest')):
                raise ValueError('Agent configuration changed. Review a new disclosure plan.')
            for run in self.runs():
                if run['state'] in ('queued', 'running', 'cancelling'):
                    raise ValueError('One investigation at a time. Wait or cancel the active run.')
            job = uuid4().hex
            receipt = self.store.put('hermes_request', {'job_id': job, 'preparation_id': preparation_id,
                'requested_at': now(), 'consent': True, 'provider': body['provider'], 'model': body['model'], 'image': body['image']})
            folder = self.root / job
            folder.mkdir(mode=0o700)
            inputs = folder / 'input'
            inputs.mkdir()
            for name, text in body['files'].items():
                target = inputs / name
                if not target.resolve().is_relative_to(inputs.resolve()):
                    raise ValueError('Invalid snapshot path')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding='utf-8')
            query = canonical({'question': body['question']})
            (inputs / 'query.json').write_text(query, encoding='utf-8')
            request = {'job_id': job, 'request_id': receipt['id'], 'input_digest': digest(body['files']),
                       'config_digest': body.get('config_digest'),
                       'files': {**{name: digest(text) for name, text in body['files'].items()}, 'query.json': digest(query)}}
            (folder / 'request.json').write_text(canonical(request), encoding='utf-8')
            (folder / 'ready').touch()
            return self.get(job)

    def runs(self):
        return [self.get(r['body']['job_id']) for r in self.store.list('hermes_request', 100)]

    def get(self, job):
        if not re.fullmatch('[a-f0-9]{32}', job):
            raise ValueError('Invalid investigation ID')
        requests = [r for r in self.store.list('hermes_request', 500) if r['body']['job_id'] == job]
        if not requests:
            raise ValueError('Investigation not found')
        request = requests[0]
        completed = [r for r in self.store.list('hermes_result', 500) if r['body']['job_id'] == job]
        if completed:
            return {**completed[0]['body'], 'receipt_id': completed[0]['id']}
        folder = self.root / job if self.root else None
        if folder is None or not folder.exists():
            return {'job_id': job, 'state': 'interrupted', 'notice': 'Compute was replaced. Start a new investigation; no model call is automatically replayed.'}
        result_path = folder / 'result.json'
        if result_path.exists():
            with self.lock:
                existing = [r for r in self.store.list('hermes_result', 500) if r['body']['job_id'] == job]
                if existing:
                    return {**existing[0]['body'], 'receipt_id': existing[0]['id']}
                if result_path.stat().st_size > 300000:
                    raise ValueError('Agent result exceeds size limit')
                output = json.loads(result_path.read_text(encoding='utf-8'))
                text = str(output.get('text', ''))[:200000]
                prepared = self.store.get(request['body']['preparation_id'])['body']
                known = {name[8:-5] for name in prepared['files'] if re.fullmatch(r'records/[a-f0-9]{64}\.json', name)}
                references = set()
                for name, content in prepared['files'].items():
                    if name.startswith('investigations/') and name.endswith('.json'):
                        context = json.loads(content).get('knowledge_context', {})
                        references.update(item['id'] for item in context.get('excluded', []))
                cited = set(re.findall(r'\b[a-f0-9]{64}\b', text))
                state = output.get('state')
                if state not in ('completed', 'failed', 'cancelled', 'interrupted'):
                    state = 'failed'
                result = self.store.put('hermes_result', {
                    'job_id': job, 'request_id': request['id'], 'preparation_id': request['body']['preparation_id'],
                    'state': state, 'text': text, 'origin': 'ai_interpretation', 'review_status': 'unreviewed',
                    'provider': prepared['provider'], 'model': prepared['model'], 'image': prepared['image'],
                    'citations': sorted(cited & known), 'reference_only_citations': sorted((cited & references) - known),
                    'unknown_citations': sorted(cited - known - references),
                    'citation_check': 'passed' if cited & known and cited.issubset(known | references) else 'needs_review',
                    'notice': 'Citation matching does not verify claims. Review against the selected evidence; deterministic results are unchanged.',
                    'error': str(output.get('error', ''))[:500], 'finished_at': output.get('finished_at', now())})
                return {**result['body'], 'receipt_id': result['id']}
        progress = folder / 'progress.json'
        if progress.exists() and progress.stat().st_size <= 10000:
            value = json.loads(progress.read_text(encoding='utf-8'))
            return {'job_id': job, 'state': 'cancelling' if (folder / 'cancel').exists() else 'running',
                    'tool_calls': value.get('tool_calls', 0), 'notice': 'Hermes is reviewing the selected snapshot.'}
        return {'job_id': job, 'state': 'queued', 'notice': 'Waiting for the cloud agent.'}

    def cancel(self, job):
        value = self.get(job)
        if value['state'] in ('queued', 'running', 'cancelling'):
            (self.root / job / 'cancel').touch()
        return {'job_id': job, 'notice': 'Cancellation requested. In-flight provider usage may still be charged.'}
