import copy
from datetime import datetime, timezone, timedelta
import pytest
import yaml
from fastapi.testclient import TestClient
from rgce import core, knowledge as k
from rgce.app import create_app
from rgce.store import Store


def doc(statement='Private ingress required', scope=None, overrides=None, due='2099-01-01T00:00:00Z', requirement='ingress', **metadata):
    meta={'type':'Security Guidance', 'title':'Networking', 'stale_after':due,
          'rgce':{'requirement':requirement, 'scope':scope or {}, 'overrides':overrides or []}, **metadata}
    return '---\n'+yaml.safe_dump(meta)+'---\n'+statement


def published(s, name='baseline', document=None, source_ids=None, base=None):
    d=k.draft(s,name,document or doc(),'Author',source_ids,base)
    return k.publish(s,d['id'],d['id'],'Reviewer')


def setup(tmp):
    s=Store(tmp); a=core.demo(s)['before']; f=a['body']['findings'][0]
    return s,a,f


def test_reuse_variation_refresh_and_historical_receipt(tmp_path):
    s,a,f=setup(tmp_path)
    source=s.put('document_source',{'name':'networking v1'})
    base=published(s,source_ids=[source['id']])
    exported,_=k.parse_okf(k.export_okf(s,base['id']))
    assert exported['sources'][0]['resource']=='urn:rgce:document:'+source['id']
    variant=published(s,'portal',doc('Public HTTPS allowed only on ingress',{'application':'portal','component':'ingress'},[base['id']]))
    k.mapping(s,a['id'],f['resource_id'],{'application':'portal','component':'ingress'},'Reviewer')
    p=core.proposal(s,a['id'],f['row_id']); ctx=p['knowledge_context']
    assert ctx['status']=='READY'
    assert [r['id'] for r in ctx['applied']]==[variant['id']]
    assert [r['id'] for r in ctx['supporting_baselines']]==[base['id']]
    assert p['contextual_guidance']==['Public HTTPS allowed only on ingress']
    receipt=s.put('knowledge_use',ctx)
    later=core.demo(s)['before']
    k.mapping(s,later['id'],f['resource_id'],{'application':'portal','component':'ingress'},'Reviewer')
    assert core.investigation(s,later['id'],f['row_id'])['knowledge_context']['applied'][0]['id']==variant['id']
    new_source=s.put('document_source',{'name':'networking v2'})
    k.replace_source(s,source['id'],new_source['id'],'Reviewer')
    assert all(e['state']=='needs_review' for e in k.catalog(s))
    assert core.proposal(s,a['id'],f['row_id'])['contextual_guidance']==[]
    base2=published(s,source_ids=[new_source['id']],base=base['id'])
    assert k.catalog(s)[1]['state']=='needs_review'
    v2=published(s,'portal',doc('Public HTTPS with monitoring',{'application':'portal','component':'ingress'},[base2['id']]),base=variant['id'])
    assert core.proposal(s,a['id'],f['row_id'])['knowledge_context']['applied'][0]['id']==v2['id']
    assert s.get(receipt['id'])['body']==ctx
    assert k.use_history(s)[0]['state']=='CONTEXT_CHANGED'
    assert s.get(a['id'])['body']['findings'][0]['severity']==f['severity']


def test_missing_context_mismatch_conflict_and_withdrawal(tmp_path):
    s,a,f=setup(tmp_path); base=published(s)
    v=published(s,'portal',doc('Public ingress',{'application':'portal'},[base['id']]))
    assert k.resolve(s,a,f)['status']=='NEEDS_CONTEXT'
    k.mapping(s,a['id'],f['resource_id'],{'application':'internal'},'Reviewer')
    r=k.resolve(s,a,f);assert r['status']=='READY' and r['applied'][0]['id']==base['id']
    k.mapping(s,a['id'],f['resource_id'],{'application':'portal'},'Reviewer')
    v2=published(s,'conflict',doc('No ingress',{'application':'portal'},[base['id']]))
    assert k.resolve(s,a,f)['conflicts']
    assert core.proposal(s,a['id'],f['row_id'])['contextual_guidance']==[]
    k.withdraw(s,v2['id'],'Reviewer','Incorrect guidance')
    assert k.resolve(s,a,f)['status']=='NEEDS_CONTEXT'


def test_expiry_boundary_and_not_yet_effective(tmp_path):
    s,a,f=setup(tmp_path)
    published(s,document=doc(due='2030-01-01T00:00:00Z'))
    assert k.resolve(s,a,f,'2029-12-31T23:59:59Z')['status']=='READY'
    assert k.resolve(s,a,f,'2030-01-01T00:00:00Z')['status']=='NEEDS_CONTEXT'


def test_context_dependency_failure_propagates_through_variation(tmp_path):
    s,a,f=setup(tmp_path)
    base=published(s)
    remote=published(s,'remote',doc(scope={'application':'other'}, requirement='remote'))
    prerequisite=published(s,'prerequisite',doc(requirement='prerequisite',
        rgce={'requirement':'prerequisite','scope':{},'depends_on':[remote['id']]}))
    variation=published(s,'variation',doc(rgce={'requirement':'ingress','scope':{},
        'overrides':[base['id']], 'depends_on':[prerequisite['id']]}))
    result=k.resolve(s,a,f)
    assert result['status']=='NEEDS_CONTEXT'
    assert [r['id'] for r in result['applied']]==[base['id']]
    assert not result['supporting_baselines']
    assert {r['id'] for r in result['excluded']}=={remote['id'],prerequisite['id'],variation['id']}
    k.mapping(s,a['id'],f['resource_id'],{'application':'other'},'Reviewer')
    result=k.resolve(s,a,f)
    assert result['status']=='READY'
    assert variation['id'] in [r['id'] for r in result['applied']]
    assert [r['id'] for r in result['supporting_baselines']]==[base['id']]


def test_revision_heads_reject_forks_instead_of_picking_one(tmp_path):
    s,a,f=setup(tmp_path)
    first=published(s)
    second=published(s,base=first['id'])
    s.put('concept_publication',{**second['body'],'text':'A conflicting branch'})
    with pytest.raises(ValueError,match='forked'):
        k.heads(s)


def test_simple_variation_edit_preserves_scope_and_baseline(tmp_path):
    s,a,f=setup(tmp_path)
    base=published(s)
    variation=published(s,'variant',doc(scope={'resource':f['resource_id']},overrides=[base['id']]))
    draft=k.simple_draft(s,'Updated contextual guidance',revision_id=variation['id'])
    updated=k.publish(s,draft['id'],draft['id'],'Reviewer')
    ext=updated['body']['metadata']['rgce']
    assert ext['overrides']==[base['id']]
    assert ext['scope']=={'resource':f['resource_id']}
    result=k.resolve(s,a,f)
    assert result['status']=='READY'
    assert [r['id'] for r in result['applied']]==[updated['id']]


def test_okf_roundtrip_preserves_unknown_and_does_not_trust_import(tmp_path):
    s,a,f=setup(tmp_path)
    original=doc(verified=[{'by':'human:external','at':'2026-01-01T00:00:00Z'}],custom={'integer':3,'flag':True})
    d=k.draft(s,'imported',original,'Importer')
    assert not k.catalog(s)
    meta,_=k.parse_okf(k.export_okf(s,d['id']))
    assert meta['custom']=={'integer':3,'flag':True}
    assert meta['verified'][0]['by']=='human:external'
    r=k.publish(s,d['id'],d['id'],'Local reviewer')
    other=Store(tmp_path/'other')
    k.draft(other,'imported',k.export_okf(s,r['id']),'Importer')
    assert not k.catalog(other)
    generic=k.draft(s,'generic','---\ntype: Reference\ncustom: useful\n---\nUseful text','Author')
    with pytest.raises(ValueError,match='configure'):k.publish(s,generic['id'],generic['id'],'Reviewer')


def test_stale_revision_and_scope_broadening_rejected(tmp_path):
    s,a,f=setup(tmp_path);base=published(s,document=doc(scope={'account':'111122223333'}))
    with pytest.raises(ValueError,match='broaden'):k.draft(s,'variation',doc(overrides=[base['id']]),'Author')
    d1=k.draft(s,'baseline',doc(scope={'account':'111122223333'}),'A',base_version=base['id'])
    d2=k.draft(s,'baseline',doc('New guidance',scope={'account':'111122223333'}),'B',base_version=base['id'])
    k.publish(s,d1['id'],d1['id'],'R')
    with pytest.raises(ValueError,match='Concurrent'):k.publish(s,d2['id'],d2['id'],'R')
    with pytest.raises(ValueError,match='exact'):k.publish(s,d2['id'],'wrong','R')


@pytest.mark.parametrize('document',[
    '---\ntype: Test\ntype: Other\n---\nbody',
    '---\ntype: !!python/object:os.system bad\n---\nbody',
    '---\ntype: Test\nx: &a [*a]\n---\nbody',
    doc(due='2030-01-01'),doc(scope={'application':'*'}),
    doc(rgce={'requirement':'a','conditions':{'anything':'yes'}}),
])
def test_invalid_metadata(tmp_path,document):
    with pytest.raises(ValueError):k.draft(Store(tmp_path),'bad',document,'Author')


def test_no_catalog_pagination_loss(tmp_path):
    s,a,f=setup(tmp_path)
    base=published(s)
    for i in range(505):s.put('concept_draft',{'not_an_approval':i})
    assert k.resolve(s,a,f)['applied'][0]['id']==base['id']


def test_http_review_token_and_saved_receipt(tmp_path):
    client=TestClient(create_app(tmp_path)); token=client.get('/api/session').json()['token'];h={'X-RGCE-Token':token}
    a=client.post('/api/demo',headers=h).json()['before'];f=a['body']['findings'][0]
    payload={'concept_id':'baseline','document':doc(),'author':'A'}
    assert client.post('/api/concepts/draft',json=payload).status_code==403
    d=client.post('/api/concepts/draft',json=payload,headers=h).json()
    r=client.post('/api/concepts/approve',json={'draft_id':d['id'],'expected_hash':d['id'],'reviewer':'R'},headers=h)
    assert r.status_code==200
    p=client.post('/api/proposal',json={'assessment_id':a['id'],'row_id':f['row_id']},headers=h).json()
    receipt=client.get('/api/records/'+p['knowledge_receipt_id']).json()
    assert receipt['body']['applied'][0]['id']==r.json()['id']
    assert client.get('/api/concepts/export/'+r.json()['id']).status_code==200


def test_cross_account_and_unmodified_requirements(tmp_path):
    s,a,f=setup(tmp_path)
    base=published(s,document=doc(scope={'account':'111122223333'}))
    backend=published(s,'backend',doc('Backend stays private',requirement='backend',scope={'account':'111122223333'}))
    variation=published(s,'portal',doc('Public portal',scope={'account':'111122223333','application':'portal'},overrides=[base['id']]))
    unrelated=published(s,'different-account',doc('Different policy',scope={'account':'999900001111'}))
    k.mapping(s,a['id'],f['resource_id'],{'application':'portal'},'R')
    r=k.resolve(s,a,f)
    assert r['status']=='READY'
    assert {x['id'] for x in r['applied']}=={backend['id'],variation['id']}
    assert any(x['id']==unrelated['id'] and 'Scope mismatch' in x['reasons'][0] for x in r['excluded'])


def test_future_effective_and_expired_baseline_block_variation(tmp_path):
    s,a,f=setup(tmp_path)
    base=published(s,document=doc(due='2030-01-01T00:00:00Z'))
    v=published(s,'variation',doc('variation',overrides=[base['id']]))
    assert k.resolve(s,a,f,'2030-01-01T00:00:00Z')['status']=='NEEDS_CONTEXT'
    meta,body=k.parse_okf(doc())
    meta['rgce']['effective_from']='2080-01-01T00:00:00Z'
    future=published(s,'future', '---\n'+yaml.safe_dump(meta)+'---\n'+body)
    assert any('Not yet effective' in e['reasons'] for e in k.catalog(s,'2029-01-01T00:00:00Z'))


def test_dependency_scope_is_checked_and_retired_export_is_deprecated(tmp_path):
    s,a,f=setup(tmp_path)
    dep=published(s,'owner',doc('Other account owner',scope={'account':'999900001111'},requirement='owner'))
    meta,body=k.parse_okf(doc())
    meta['rgce']['depends_on']=[dep['id']]
    concept=published(s,document='---\n'+yaml.safe_dump(meta)+'---\n'+body)
    assert k.resolve(s,a,f)['status']=='NEEDS_CONTEXT'
    k.withdraw(s,concept['id'],'R','Retired')
    exported,_=k.parse_okf(k.export_okf(s,concept['id']))
    assert exported['status']=='deprecated'


def test_ai_can_cite_resolved_concepts_but_not_invented_context(tmp_path):
    s,a,f=setup(tmp_path); r=published(s)
    note=core.annotate(s,a['id'],f['row_id'],'Interpretation of reviewed guidance','external/model',[r['id']])
    assert note['body']['status']=='unreviewed'
    assert note['body']['origin']=='ai_interpretation'
    with pytest.raises(ValueError):core.annotate(s,a['id'],f['row_id'],'Invented','external/model',['fake'])
