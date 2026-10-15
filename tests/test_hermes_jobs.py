import json
import importlib.util
from pathlib import Path
import pytest
from rgce import core
from rgce.store import Store
from rgce.hermes_jobs import HermesJobs


def configured(tmp_path, monkeypatch):
    jobs = tmp_path / 'jobs'; jobs.mkdir()
    monkeypatch.setenv('RGCE_HERMES_JOBS', str(jobs))
    (jobs / 'status.json').write_text(json.dumps({'ready': True, 'provider': 'test-provider', 'model': 'test-model', 'image': 'sha256:test', 'notice': 'test broker'}))
    store = Store(tmp_path / 'store'); assessment = core.demo(store)['before']
    return store, HermesJobs(store), assessment, jobs


def test_consent_config_change_and_single_job(tmp_path, monkeypatch):
    store, controller, assessment, jobs = configured(tmp_path, monkeypatch)
    plan = controller.prepare([assessment['id']], 'Explain with citations')
    with pytest.raises(ValueError, match='consent'): controller.start(plan['id'], False)
    status = json.loads((jobs / 'status.json').read_text()); status['model'] = 'changed'
    (jobs / 'status.json').write_text(json.dumps(status))
    with pytest.raises(ValueError, match='configuration changed'): controller.start(plan['id'], True)
    status['model'] = 'test-model'; (jobs / 'status.json').write_text(json.dumps(status))
    run = controller.start(plan['id'], True)
    assert run['state'] == 'queued'
    with pytest.raises(ValueError, match='One investigation'): controller.start(plan['id'], True)
    controller.cancel(run['job_id'])
    assert (jobs / run['job_id'] / 'cancel').exists()


def test_result_receipt_preserves_rules_and_marks_unknown_citations(tmp_path, monkeypatch):
    store, controller, assessment, jobs = configured(tmp_path, monkeypatch)
    before = store.get(assessment['id'])
    plan = controller.prepare([assessment['id']], 'Investigate')
    run = controller.start(plan['id'], True)
    output = {'state': 'completed', 'text': 'Known '+assessment['id']+' unknown '+'f'*64}
    (jobs / run['job_id'] / 'result.json').write_text(json.dumps(output))
    result = controller.get(run['job_id'])
    assert result['citation_check'] == 'needs_review'
    assert result['unknown_citations'] == ['f'*64]
    assert result['origin'] == 'ai_interpretation' and result['review_status'] == 'unreviewed'
    assert store.get(assessment['id']) == before
    assert controller.get(run['job_id'])['receipt_id'] == result['receipt_id']
    monkeypatch.delenv('RGCE_HERMES_JOBS')
    assert HermesJobs(store).get(run['job_id'])['text'] == output['text']


def test_recovery_never_replays_model_call(tmp_path, monkeypatch):
    store, controller, assessment, jobs = configured(tmp_path, monkeypatch)
    plan = controller.prepare([assessment['id']], 'Investigate')
    run = controller.start(plan['id'], True)
    other = tmp_path / 'freshjobs'; other.mkdir()
    monkeypatch.setenv('RGCE_HERMES_JOBS', str(other))
    assert HermesJobs(store).get(run['job_id'])['state'] == 'interrupted'
    assert not list(other.iterdir())


def test_followup_is_explicit_unreviewed_context_and_retains_selection(tmp_path, monkeypatch):
    store, controller, assessment, jobs = configured(tmp_path, monkeypatch)
    plan = controller.prepare([assessment['id']], 'Investigate')
    run = controller.start(plan['id'], True)
    text = 'Unreviewed conclusion citing '+assessment['id']
    (jobs / run['job_id'] / 'result.json').write_text(json.dumps({'state':'completed','text':text}))
    controller.get(run['job_id'])
    follow = controller.prepare([assessment['id']], 'What should the owner verify?', run['job_id'])
    assert 'not source evidence' in follow['body']['files']['prior-analysis.md']
    assert text in follow['body']['files']['prior-analysis.md']
    with pytest.raises(ValueError, match='original evidence'):
        controller.prepare([assessment['body']['evidence_id']], 'Other evidence', run['job_id'])
    assert len(store.list('hermes_request')) == 1  # Preparation is not a model call.


def test_agent_tools_cannot_read_secret_or_traverse(tmp_path):
    path = Path(__file__).parents[1] / 'deploy/hermes/runner.py'
    spec = importlib.util.spec_from_file_location('ce_runner', path)
    runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
    selected = tmp_path / 'input'; selected.mkdir()
    (selected / 'evidence.txt').write_text('synthetic evidence')
    (tmp_path / 'secret.txt').write_text('not selected')
    assert 'synthetic evidence' in runner.safe_read('evidence.txt', selected)['text']
    assert runner.safe_search('synthetic', selected)['matches']
    for forbidden in ('../secret.txt', '/proc/self/environ', 'C:/secret.txt', '..\\secret.txt'):
        with pytest.raises(ValueError): runner.safe_read(forbidden, selected)


def test_hermes_api_keeps_local_mutation_boundary(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from rgce.app import create_app
    store, _, assessment, _ = configured(tmp_path, monkeypatch)
    with TestClient(create_app(store.home)) as client:
        payload = {'record_ids': [assessment['id']], 'question': 'Investigate'}
        assert client.post('/api/hermes/prepare', json=payload).status_code == 403
        token = client.get('/api/session').json()['token']
        headers = {'x-rgce-token': token}
        response = client.post('/api/hermes/prepare', json=payload, headers=headers)
        assert response.status_code == 200
        assert 'files' not in response.json()
        assert client.post('/api/hermes/start', json={'preparation_id':response.json()['id'], 'consent':False}, headers=headers).status_code == 400
