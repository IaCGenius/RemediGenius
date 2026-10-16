"""Constructed control-flow tests; these are not live AWS/model evidence."""
import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1]/'profiles/ce/desk/plugins/ce-runtime/workflow.py'
spec = importlib.util.spec_from_file_location('assessment_under_test',path)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def engine(tmp_path, calls, model_calls):
    caps = {'targets': {'default': {'regions':['us-east-1']}},
            'operations': {service:[op for _,s,op,_ in module.SOURCES if s==service]
                           for _,service,_,_ in module.SOURCES}}
    def collect(args):
        calls.append(args)
        return {'status':'OK','run_id':str(len(calls)),'summary':{},'has_more':True}
    def reason(stage, packet, prior):
        model_calls.append((stage,packet))
        return 'Untrusted generated text: completed'
    return module.Assessment(tmp_path,caps,collect,lambda p:{'status':'NOT_SUPPLIED'},reason,{'pinned':'skill'})


def test_fixed_sequence_and_shared_packet(tmp_path):
    calls, models = [], []
    e=engine(tmp_path,calls,models)
    run=e.start(['default'],'us-east-1',['index.md'])
    for _ in range(len(module.SOURCES)+4):
        run=e.advance(run['id'])
    assert run['status']=='COMPLETE'
    assert len(calls)==len(module.SOURCES)
    assert all(x['max_pages']==1 and x['target']=='default' for x in calls)
    assert [x[0] for x in models]==['interpret','review','finish']
    assert len(set(x[1] for x in models))==1
    e.advance(run['id'])
    assert len(models)==3 and len(calls)==len(module.SOURCES)
    assert all(x['result']['has_more'] for x in run['results'])


def test_resume_uses_saved_cursor_not_chat(tmp_path):
    calls,models=[],[]
    e=engine(tmp_path,calls,models); run=e.start(['default'],'us-east-1',[])
    e.advance(run['id']); e.advance(run['id'])
    fresh=engine(tmp_path,calls,models); fresh.advance(run['id'])
    assert len(calls)==2 and calls[0]['operation']!=calls[1]['operation']


def test_interruption_never_replays(tmp_path):
    calls,models=[],[]; e=engine(tmp_path,calls,models)
    run=e.start(['default'],'us-east-1',[])
    saved=e.load(run['id']); saved['inflight']={'stage':'collect'}; e.save(saved)
    assert e.advance(run['id'])['status']=='BLOCKED'
    assert calls==models==[]


def test_failed_reasoning_cannot_claim_completion(tmp_path):
    e=engine(tmp_path,[],[]); run=e.start(['default'],'us-east-1',[])
    for _ in range(len(module.SOURCES)+1): e.advance(run['id'])
    e.reason=lambda *args: (_ for _ in ()).throw(TimeoutError('model timeout'))
    assert e.advance(run['id'])['status']=='BLOCKED'
    assert e.advance(run['id'])['status']=='BLOCKED'


@pytest.mark.parametrize('targets,region',[(['unknown'],'us-east-1'),(['default'],'us-west-2'),(['default','default'],'us-east-1')])
def test_scope_rejected(tmp_path,targets,region):
    with pytest.raises(ValueError): engine(tmp_path,[],[]).start(targets,region,[])


def test_cancel_and_path_boundary(tmp_path):
    e=engine(tmp_path,[],[]); run=e.start(['default'],'us-east-1',[])
    assert e.cancel(run['id'])['status']=='CANCELLED'
    assert e.advance(run['id'])['status']=='CANCELLED'
    with pytest.raises(ValueError): e.load('../other')
