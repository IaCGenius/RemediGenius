import json
import pytest
from pathlib import Path
from rgce import core, knowledge
from rgce.store import Store
from rgce.workspace import export_workspace, verify_workspace


def test_export_pins_evidence_and_resolves_knowledge(tmp_path):
    store=Store(tmp_path)
    a=core.demo(store)['before']
    d=knowledge.simple_draft(store,'SAMPLE: only the VPN may reach SSH.',title='Sample guidance')
    k=knowledge.publish(store,d['id'],d['id'],'Test operator')
    result=export_workspace(store,[a['id']])
    folder=Path(result['folder'])
    assert verify_workspace(folder)['status']=='verified'
    assert (folder/'records'/f"{a['body']['evidence_id']}.json").exists()
    assert (folder/'knowledge'/f"{k['id']}.md").exists()
    assert 'SAMPLE:' in next((folder/'investigations').glob('*.json')).read_text(encoding='utf-8')
    (folder/'summary.md').write_text('modified',encoding='utf-8')
    with pytest.raises(ValueError,match='changed'): verify_workspace(folder)


def test_context_only_export_and_selection(tmp_path):
    store=Store(tmp_path)
    a=core.demo(store)['before']
    e=store.get(a['body']['evidence_id'])
    folder=Path(export_workspace(store,[e['id']])['folder'])
    assert not (folder/'investigations').exists()
    assert len(list((folder/'records').glob('*')))==1
    manifest=json.loads((folder/'manifest.json').read_text())
    manifest['files']['../outside']='x'
    (folder/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='escapes'): verify_workspace(folder)


def test_export_keeps_variation_and_baseline(tmp_path):
    store=Store(tmp_path);a=core.demo(store)['before'];f=a['body']['findings'][0]
    d=knowledge.simple_draft(store,'Synthetic baseline',title='Baseline')
    baseline=knowledge.publish(store,d['id'],d['id'],'Test operator')
    d=knowledge.simple_draft(store,'Synthetic variation',title='Variation',baseline_id=baseline['id'],scope={'resource':f['resource_id']})
    variation=knowledge.publish(store,d['id'],d['id'],'Test operator')
    folder=Path(export_workspace(store,[a['id']])['folder'])
    assert (folder/'knowledge'/f"{baseline['id']}.md").exists()
    assert (folder/'knowledge'/f"{variation['id']}.md").exists()


def test_export_includes_operator_scope_receipt(tmp_path):
    store=Store(tmp_path);a=core.demo(store)['before'];f=a['body']['findings'][0]
    mapping=knowledge.mapping(store,a['id'],f['resource_id'],{'environment':'acceptance'},'Test operator')
    folder=Path(export_workspace(store,[a['id']])['folder'])
    assert json.loads((folder/'records'/f"{mapping['id']}.json").read_text())['kind']=='resource_context'


def test_packaged_skill_matches_reviewed_source():
    root=Path(__file__).parents[1]
    assert (root/'rgce/static/remedigenius-investigate.SKILL.md').read_bytes()==(root/'integrations/skills/remedigenius-investigate/SKILL.md').read_bytes()


def test_browser_export_requires_local_session(tmp_path):
    from fastapi.testclient import TestClient
    from rgce.app import create_app
    store=Store(tmp_path);a=core.demo(store)['before'];client=TestClient(create_app(tmp_path))
    request={'record_ids':[a['id']]}
    assert client.post('/api/workspace/export',json=request).status_code==403
    token=client.get('/api/session').json()['token']
    response=client.post('/api/workspace/export',json=request,headers={'x-rgce-token':token})
    assert response.status_code==200
    assert verify_workspace(response.json()['folder'])['status']=='verified'
    import io, zipfile
    download=client.get(response.json()['download_url'])
    assert download.status_code==200
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert 'START-HERE.md' in archive.namelist()
        assert 'manifest.json' in archive.namelist()
        assert all(not n.startswith('/') and '..' not in n.split('/') for n in archive.namelist())
    assert client.get('/api/workspace/download/not-an-id').status_code==400
    (Path(response.json()['folder'])/'summary.md').write_text('tampered',encoding='utf-8')
    assert client.get(response.json()['download_url']).status_code==400
