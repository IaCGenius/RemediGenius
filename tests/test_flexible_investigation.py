"""Scripted adversarial control tests, explicitly not live model acceptance."""
import importlib.util
import json
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('flexible',Path(__file__).resolve().parents[1]/'profiles/ce/desk/plugins/ce-runtime/workflow.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)


def make(tmp_path, plans):
    calls=[];models=[]
    def reason(stage,packet,prior):
        models.append((stage,packet))
        if stage=='plan': return json.dumps(plans.pop(0))
        if stage=='finish': return json.dumps({'answer':'Qualified test interpretation',
            'observations':[], 'knowledge':[], 'proposals':[], 'limits':[], 'next_step':''})
        return 'Qualified test interpretation'
    def collect(req):
        calls.append(req)
        return {'status':'OK','run_id':'a'*32,'raw_path':'raw/returned.json'}
    e=w.Investigation(tmp_path,{'targets':{'default':{'regions':['us-east-1']}},
        'operations':{'ec2':['describe_instances']}},collect,lambda p:{'status':'NOT_SUPPLIED'},reason,{})
    run=e.start(['default'],'us-east-1',[],'Investigate the supplied issue',['Explain evidence and gaps'],['raw/test.json'])
    return e,run,calls,models


def plan(req):
    return {'decision':'collect','rationale':'Resolve a specific evidence gap',
            'steps':[{'question':'What does this evidence establish?', 'request':req}]}


def done(): return {'decision':'sufficient','rationale':'Evidence addresses criteria','steps':[]}


def test_flexible_path_does_not_enumerate_services(tmp_path):
    e,r,c,m=make(tmp_path,[plan({'action':'show','path':'raw/test.json'}),done()])
    for _ in range(7): r=e.advance(r['id'])
    assert r['status']=='COMPLETE' and r['round']==1
    assert c==[{'action':'show','path':'raw/test.json'}]
    packets=[p for stage,p in m if stage in ('interpret','review','finish')]
    assert len(packets)==3 and len(set(packets))==1


@pytest.mark.parametrize('req',[
    {'action':'read','target':'other','region':'us-east-1','service':'ec2','operation':'describe_instances','parameters':{},'max_pages':1},
    {'action':'read','target':'default','region':'us-east-1','service':'ec2','operation':'terminate_instances','parameters':{},'max_pages':1},
    {'action':'show','path':'raw/not-supplied.json'},
    {'action':'terminal','command':'aws iam create-user'},
    {'action':'compare','before':'a'*32,'after':'b'*32},
])
def test_invalid_proposals_cannot_execute(tmp_path,req):
    e,r,c,m=make(tmp_path,[plan(req),plan(req)])
    for _ in range(3):r=e.advance(r['id'])
    assert r['status']=='BLOCKED' and c==[] and r['plan_repairs']==2


def test_repeated_queries_do_not_execute_twice(tmp_path):
    p=plan({'action':'show','path':'raw/test.json'})
    e,r,c,m=make(tmp_path,[p,p,p])
    for _ in range(5): r=e.advance(r['id'])
    assert len(c)==1 and r['status']=='BLOCKED'


def test_round_cap_ends_inconclusive(tmp_path):
    terminal={'decision':'inconclusive','rationale':'Collection budget reached','steps':[]}
    e,r,c,m=make(tmp_path,[plan({'action':'schema','service':'ec2','operation':'describe_instances','field':field})
                          for field in ('','Filters','InstanceIds')]+[terminal])
    for _ in range(12):r=e.advance(r['id'])
    assert r['status']=='COMPLETE' and r['outcome']=='INCONCLUSIVE_BUDGET'
    assert len(c)==3 and len([x for x in m if x[0]=='plan'])==4


def test_resume_does_not_reset_consumption(tmp_path):
    e,r,c,m=make(tmp_path,[plan({'action':'show','path':'raw/test.json'})])
    for _ in range(3):r=e.advance(r['id'])
    saved=e.load(r['id'])
    assert saved['actions']==1 and saved['round']==1 and len(saved['signatures'])==1
    assert e.validate_plan(saved, json.dumps(done()))['decision']=='sufficient'


def test_denied_operation_stays_denied_with_changed_parameters(tmp_path):
    e,r,c,m=make(tmp_path,[]);saved=e.load(r['id'])
    req={'action':'read','target':'default','region':'us-east-1','service':'ec2',
         'operation':'describe_instances','parameters':{},'max_pages':1}
    saved['results']=[{'request':req,'result':{'errors':[{'code':'AccessDenied'}]}}]
    changed={**req,'parameters':{'MaxResults':5}}
    with pytest.raises(ValueError,match='denied'):e.validate_plan(saved,json.dumps(plan(changed)))


def test_budget_is_not_reset_by_new_plan(tmp_path):
    e,r,c,m=make(tmp_path,[]);saved=e.load(r['id']);saved['reads']=6;saved['pages']=6
    req={'action':'read','target':'default','region':'us-east-1','service':'ec2',
         'operation':'describe_instances','parameters':{},'max_pages':1}
    with pytest.raises(ValueError,match='budget'):e.validate_plan(saved,json.dumps(plan(req)))


def test_ten_page_read_and_timeout_preserve_collected_facts(tmp_path):
    req={'action':'read','target':'default','region':'us-east-1','service':'ec2',
         'operation':'describe_instances','parameters':{},'max_pages':10}
    e,r,c,m=make(tmp_path,[plan(req)])
    e.collect=lambda req:{'status':'PARTIAL','summary':{'count':50},'has_more':True,
        'receipt_path':'receipts/test.json','continuation_parameters':{'NextToken':'next'}}
    for _ in range(3):r=e.advance(r['id'])
    assert r['pages']==10
    def timeout(*args):raise TimeoutError()
    e.reason=timeout
    r=e.advance(r['id'])
    assert r['status']=='BLOCKED' and r['reason'].startswith('TimeoutError:')
    assert r['results'][0]['result']['summary']['count']==50
    assert r['results'][0]['result']['continuation_parameters']=={'NextToken':'next'}
    assert e.cancel(r['id'])['results']==r['results']

def test_returned_normalized_artifact_is_admitted_but_invented_sibling_is_not(tmp_path):
    e,r,_,_=make(tmp_path,[])
    saved=e.load(r['id'])
    saved['results']=[{'question':'Collected findings','request':{'action':'read'},
                      'result':{'files':[{'path':'normalized/actual/findings.json','layer':'normalized'}]}}]
    actual=plan({'action':'show','path':'normalized/actual/findings.json'})
    assert e.validate_plan(saved,json.dumps(actual))==actual
    assert e.view(saved)['results'][0]['result']['files'][0]['path']=='normalized/actual/findings.json'
    with pytest.raises(ValueError,match='Evidence path'):
        e.validate_plan(saved,json.dumps(plan({'action':'show','path':'normalized/invented/findings.json'})))

def test_lower_read_cap_is_frozen_and_prevents_followup_read(tmp_path):
    req={'action':'read','target':'default','region':'us-east-1','service':'ec2',
         'operation':'describe_instances','parameters':{},'max_pages':1}
    terminal={'decision':'inconclusive','rationale':'Read budget reached','steps':[]}
    e,_,calls,models=make(tmp_path,[plan(req),terminal])
    run=e.start(['default'],'us-east-1',[],'One read only',['Report result'],max_reads=1)
    for _ in range(9):run=e.advance(run['id'])
    assert len(calls)==1 and run['limits']['reads']==1
    assert run['status']=='COMPLETE' and run['outcome']=='INCONCLUSIVE_BUDGET'
    assert len([s for s,p in models if s=='plan'])==2


def test_dispatch_rechecks_saved_plan_read_budget(tmp_path):
    e,r,c,m=make(tmp_path,[])
    run=e.load(r['id']);run.update(stage='collect',reads=1,cursor=0)
    run['limits']['reads']=1
    run['plan']=[{'question':'Must not execute','request':{'action':'read','target':'default',
        'region':'us-east-1','service':'ec2','operation':'describe_instances','parameters':{},'max_pages':1}}]
    e.save(run)
    result=e.advance(r['id'])
    assert result['status']=='BLOCKED' and not c


def test_exhausted_budget_can_still_conclude_sufficient(tmp_path):
    req={'action':'read','target':'default','region':'us-east-1','service':'ec2',
         'operation':'describe_instances','parameters':{},'max_pages':1}
    e,_,calls,models=make(tmp_path,[plan(req),done()])
    run=e.start(['default'],'us-east-1',[],'One read only',['Report result'],max_reads=1)
    for _ in range(9):run=e.advance(run['id'])
    assert len(calls)==1 and run['status']=='COMPLETE' and run['outcome']=='AI_SUFFICIENT'
    assert len([s for s,p in models if s=='plan'])==2


def test_exhausted_budget_rejects_extra_read_without_repair_hop(tmp_path):
    req={'action':'read','target':'default','region':'us-east-1','service':'ec2',
         'operation':'describe_instances','parameters':{},'max_pages':1}
    e,_,calls,models=make(tmp_path,[plan(req),plan(req)])
    run=e.start(['default'],'us-east-1',[],'One read only',['Report result'],max_reads=1)
    for _ in range(9):run=e.advance(run['id'])
    assert len(calls)==1 and run['status']=='COMPLETE'
    assert run['outcome']=='INCONCLUSIVE_BUDGET' and run['plan_repairs']==0
