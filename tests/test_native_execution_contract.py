"""Local constructed boundary/regression cases, not live AWS acceptance evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value

comparison=module('ce_compare','profiles/ce/desk/skills/ce-aws-read/scripts/evidence_compare.py')
runtime=module('ce_runtime','profiles/ce/desk/plugins/ce-runtime/__init__.py')

def snapshot():
    return {'run_id':'a'*32,'observed_at':'2026-01-01T00:00:00+00:00',
            'scope':{'target':'default','account_id':'unit-account','region':'us-east-1',
                     'service':'securityhub','operation':'get_findings','parameters':{}},
            'status':'OK','has_more':False,'errors':[],
            'pages':[{'Findings':[{'ProductArn':'unit-product','Id':'one','Severity':{'Label':'HIGH'}},
                                  {'ProductArn':'unit-product','Id':'two','Severity':{'Label':'LOW'}}],
                      'NextToken':'before','ResponseMetadata':{'RequestId':'before'}}]}

def pair():
    old=snapshot();new=copy.deepcopy(old)
    new.update(run_id='b'*32,observed_at='2026-01-01T00:01:00+00:00')
    return old,new

def test_pagination_rotation_order_and_page_boundaries_are_not_finding_changes():
    old,new=pair();rows=new['pages'][0]['Findings']
    new['pages']=[{'Findings':[rows[1]],'NextToken':'different'}, {'Findings':[rows[0]]}]
    result=comparison.compare_snapshots(old,new)
    assert result['result']=='UNCHANGED' and result['after_count']==2


def test_assessment_blocks_independent_tools(rt):
    rt.turns[('session','turn')]['assessment_active']='a'*32
    for tool in ('ce_aws','ce_validate','ce_case','ce_review'):
        result=rt.gate(tool,{},session_id='session',turn_id='turn')
        assert result['action']=='block' and 'assessment' in result['message']
    assert rt.gate('ce_assessment',{'action':'next'},session_id='session',turn_id='turn')['action']=='modify'


def test_assessment_model_timeout_respects_remaining_turn(rt):
    received=[]
    async def answer(*args,**kwargs):
        received.append(kwargs['timeout'])
        return SimpleNamespace(text=json.dumps({'decision':'inconclusive','rationale':'No evidence supplied','steps':[]}),model='test')
    rt.ctx=SimpleNamespace(llm=SimpleNamespace(acomplete=answer))
    rt.knowledge=lambda args: {'path':args['path'],'content':''}
    state=rt.turns[('session','turn')]
    state['session_id']='session'
    run=rt.assessment(state,{'action':'start','objective':'Inventory resources','criteria':['List resources'],
                             'targets':['default'],'region':'us-east-1','knowledge_paths':[]})
    rt.assessment(state,{'action':'next','id':run['id']})
    state['start']=time.monotonic()-rt.policy['dispatch_deadline_seconds']+5
    result=rt.assessment(state,{'action':'next','id':run['id']})
    assert received and 0<received[0]<=5
    assert result['status']=='RUNNING'


def test_assessment_final_output_cannot_be_rewritten_by_outer_model(rt):
    rt.turns[('session','turn')]['assessment_result']={
        'id':'a'*32,'notice':'Not a secure verdict','results':[],
        'answer':'Exact saved interpretation with uncertainty'}
    text=rt.label('Everything is secure',session_id='session',turn_id='turn')
    assert 'Exact saved interpretation' in text and 'Everything is secure' not in text


def test_blocked_contract_cannot_be_bypassed_by_outer_answer(rt):
    rt.turns[('session','turn')]['assessment_blocked']={
        'id':'a'*32,'stage':'finish','reason':'Answer contract: unknown evidence reference'}
    text=rt.label('Everything is secure. Tool validation PASS.',session_id='session',turn_id='turn')
    assert 'BLOCKED' in text and 'unknown evidence reference' in text
    assert 'Everything is secure' not in text and 'validation PASS' not in text


@pytest.mark.parametrize('status',['PASS','FAIL','BLOCKED'])
def test_assessment_keeps_requested_validator_results_visible(rt,status):
    state=rt.turns[('session','turn')]
    state['assessment_result']={'id':'a'*32,'notice':'Not a secure verdict',
        'results':[],'answer':'Exact saved source conclusion'}
    state['validations']={'aws-cli':{'status':status,'attempt':1,'attempt_limit':3}}
    text=rt.label('Requested syntax result; no deployment.',session_id='session',turn_id='turn')
    assert 'Exact saved source conclusion' in text and 'Requested follow-up' in text
    assert 'aws-cli · '+status in text and 'Requested syntax result' in text

def test_actual_finding_change_is_not_hidden():
    old,new=pair();new['pages'][0]['Findings'][0]['Severity']['Label']='CRITICAL'
    result=comparison.compare_snapshots(old,new)
    assert result['result']=='CHANGED' and result['changed_count']==1

@pytest.mark.parametrize('kind',['partial','scope','older','duplicate'])
def test_invalid_comparisons_never_report_unchanged(kind):
    old,new=pair()
    if kind=='partial':new['has_more']=True
    if kind=='scope':new['scope']['account_id']='different'
    if kind=='older':new['observed_at']=old['observed_at']
    if kind=='duplicate':new['pages'][0]['Findings'].append({'ProductArn':'unit-product','Id':'one'})
    result=comparison.compare_snapshots(old,new)
    assert result['result']=='INCOMPARABLE' and result['response_changed'] is None

@pytest.fixture
def rt(monkeypatch,tmp_path):
    monkeypatch.setenv('HERMES_HOME',str(tmp_path))
    value=runtime.Runtime(SimpleNamespace())
    value.turns[('session','turn')]={'start':time.monotonic(),'calls':0,'reads':0,
        'requests':{},'denied':set(),'ready':True,'capabilities':{
            'targets':{'default':{'regions':['us-east-1']}},
            'operations':{'macie2':['get_macie_session']}}}
    return value

@pytest.mark.parametrize('tool',['terminal','execute_code','write_file','patch','read_file','skill_manage','unexpected_plugin'])
def test_unreviewed_execution_routes_blocked(rt,tool):
    assert rt.gate(tool,{},session_id='session',turn_id='turn')['action']=='block'

def test_missing_preflight_and_deadline_block(rt):
    assert rt.gate('ce_aws',{},session_id='other',turn_id='turn')['action']=='block'
    rt.turns[('session','turn')]['start']-=rt.policy['dispatch_deadline_seconds']+1
    assert rt.gate('ce_aws',{},session_id='session',turn_id='turn')['action']=='block'

def test_tool_budget_and_missing_admission_ticket(rt):
    for _ in range(rt.policy['max_tool_calls']):
        assert rt.gate('ce_aws',{},session_id='session',turn_id='turn')['action']=='modify'
    assert rt.gate('ce_aws',{},session_id='session',turn_id='turn')['action']=='block'
    assert json.loads(rt.handle('ce_aws',{'action':'capabilities'}))['status']=='BLOCKED'

@pytest.mark.parametrize('action',['read','compare'])
def test_live_execution_cannot_skip_workflow(rt,action):
    result=rt.gate('ce_aws',{'action':action},session_id='session',turn_id='turn')
    assert result['action']=='block' and 'ce_assessment' in result['message']
    assert rt.tickets == {}
    assert rt.turns[('session','turn')]['reads']==0

@pytest.mark.parametrize('action',['capabilities','schema','show'])
def test_saved_inspection_still_available_without_workflow(rt,action):
    assert rt.gate('ce_aws',{'action':action},session_id='session',turn_id='turn')['action']=='modify'

def test_denial_cannot_be_retried_by_omitting_default_target(rt,monkeypatch):
    calls=[]
    monkeypatch.setattr(runtime,'invoke_helper',lambda p:calls.append(p) or {'errors':[{'code':'AccessDeniedException'}]})
    params={'action':'read','target':'default','region':'us-east-1','service':'macie2','operation':'get_macie_session'}
    rt.aws(rt.turns[('session','turn')],params)
    del params['target']
    with pytest.raises(ValueError,match='denied'):rt.aws(rt.turns[('session','turn')],params)
    assert len(calls)==1

def test_knowledge_escape_and_symlink_rejected(rt,monkeypatch,tmp_path):
    home=tmp_path/'knowledge';home.mkdir();monkeypatch.setattr(runtime,'KNOWLEDGE',home)
    with pytest.raises(ValueError):rt.knowledge({'path':'../credentials.json'})
    assert rt.knowledge({'path':'index.md'})['status']=='NOT_SUPPLIED'

def test_review_only_once(rt):
    state=rt.turns[('session','turn')];state['reviewed']=True
    with pytest.raises(ValueError,match='One review'):rt.review(state,{'draft':'test'})


def test_knowledge_read_carries_provenance_and_detects_changed_content(rt,monkeypatch,tmp_path):
    home=tmp_path/'selected';home.mkdir();monkeypatch.setattr(runtime,'KNOWLEDGE',home)
    content=home/'content.md';content.write_bytes(b'Operator supplied context.\n')
    metadata={'scope':'unit test only','content_sha256':hashlib.sha256(content.read_bytes()).hexdigest()}
    (home/'metadata.json').write_text(json.dumps(metadata))
    result=rt.knowledge({'path':'content.md'})
    assert result['metadata']==metadata and result['provenance_status']=='HASH_MATCHED'
    content.write_bytes(b'Changed without reimport\n')
    with pytest.raises(ValueError,match='differs'):rt.knowledge({'path':'content.md'})


def test_knowledge_missing_metadata_is_explicit(rt,monkeypatch,tmp_path):
    home=tmp_path/'selected';home.mkdir();monkeypatch.setattr(runtime,'KNOWLEDGE',home)
    (home/'content.md').write_text('Readable source without provenance')
    assert rt.knowledge({'path':'content.md'})['provenance_status']=='NOT_SUPPLIED'

def test_review_total_deadline_cancels_without_retry(rt):
    import asyncio
    cancelled=[]
    async def slow(*args,**kwargs):
        try: await asyncio.sleep(20)
        finally: cancelled.append(True)
    rt.ctx=SimpleNamespace(llm=SimpleNamespace(acomplete=slow))
    rt.policy['review_timeout_seconds']=.02
    state=rt.turns[('session','turn')]
    state.update(reviewed=False,evidence=[],request='test')
    started=time.monotonic()
    assert rt.review(state,{'draft':'test'})['status']=='NOT_REVIEWED'
    assert time.monotonic()-started<1 and cancelled==[True]
    with pytest.raises(ValueError,match='One review'):rt.review(state,{'draft':'test'})

def test_empty_critique_is_not_reviewed(rt):
    async def empty(*args,**kwargs): return SimpleNamespace(text=' ',model='unit')
    rt.ctx=SimpleNamespace(llm=SimpleNamespace(acomplete=empty))
    state=rt.turns[('session','turn')]
    state.update(reviewed=False,evidence=[],request='test')
    assert rt.review(state,{'draft':'test'})['status']=='NOT_REVIEWED'

@pytest.mark.parametrize('changed',['package','active'])
def test_changed_reviewed_instructions_fail_integrity(monkeypatch,tmp_path,changed):
    source=tmp_path/'package';source.mkdir()
    active=tmp_path/'active';active.mkdir()
    here=source/'plugins/ce-runtime';here.mkdir(parents=True)
    for root in (source,active): (root/'SOUL.md').write_text('reviewed instructions')
    digest=hashlib.sha256((source/'SOUL.md').read_bytes()).hexdigest()
    (here/'manifest.json').write_text(json.dumps({'version':'unit','files':{'SOUL.md':digest}}))
    monkeypatch.setattr(runtime,'ROOT',source);monkeypatch.setattr(runtime,'HERE',here)
    monkeypatch.setenv('HERMES_HOME',str(active))
    assert runtime.checked_manifest()['version']=='unit'
    ((source if changed=='package' else active)/'SOUL.md').write_text('changed instructions')
    with pytest.raises(ValueError): runtime.checked_manifest()

def test_large_displays_do_not_drop_review_draft_or_collection_facts(rt):
    seen=[]
    async def critique(messages,**kwargs):
        seen.append(json.loads(messages[-1]['content']))
        return SimpleNamespace(text='No issues identified, not certified.',model='unit')
    rt.ctx=SimpleNamespace(llm=SimpleNamespace(acomplete=critique))
    state=rt.turns[('session','turn')]
    state.update(reviewed=False,evidence=['x'*18000]*8,request='test',
                 collections=[{'status':'OK','has_more':False}])
    assert rt.review(state,{'draft':'The complete draft must survive.'})['status']=='AI_CRITIQUED'
    assert seen[0]['draft']=='The complete draft must survive.'
    assert seen[0]['collection_facts']==[{'status':'OK','has_more':False}]
    assert seen[0]['configured_capabilities']==state['capabilities']
    assert seen[0]['runtime_limits']['max_cloud_reads']==6
    assert 'skill_view' in seen[0]['admitted_tools']
    assert 'skill_manage' not in seen[0]['admitted_tools']
    assert any('mfa_delete' in item['text'] for item in seen[0]['reviewed_guidance'])
    assert all(item['origin']=='packaged guidance, not an AWS observation' for item in seen[0]['reviewed_guidance'])
    assert 'Bounded same-session tool excerpts' in seen[0]['context_boundary']
    assert all(e['display_truncated'] for e in seen[0]['evidence'])


def test_runtime_label_deduplicates_heading_without_losing_explanation(rt):
    rt.turns[('session','turn')]['review']={'status':'AI_REVIEWED'}
    result=rt.label('**AI interpretation — NOT_REVIEWED.** (Earlier context retained.)\n\nAnswer.',
                    session_id='session',turn_id='turn')
    assert result.count('**AI interpretation —')==1
    assert 'AI_REVIEWED' in result and 'NOT_REVIEWED' not in result
    assert '(Earlier context retained.)' in result and result.endswith('Answer.')


def test_review_without_evidence_is_not_grounded(rt):
    async def critique(messages, **kwargs):
        return SimpleNamespace(text='No issues identified', model='unit')
    rt.ctx = SimpleNamespace(llm=SimpleNamespace(acomplete=critique))
    state = rt.turns[('session','turn')]
    state.update(reviewed=False,evidence=[],request='test')
    assert rt.review(state,{'draft':'A claim'})['status'] == 'NOT_GROUNDED'


def test_critiqued_proposal_still_requires_operator_review(rt):
    rt.turns[('session','turn')]['review']={'status':'AI_CRITIQUED'}
    draft='MINIMAL TERRAFORM EDIT (AI interpretation / unreviewed draft)\nterraform validate NOT_RUN'
    result=rt.label(draft,session_id='session',turn_id='turn')
    assert 'draft requiring operator review' in result
    assert 'unreviewed draft' not in result
    assert 'terraform validate NOT_RUN' in result
    rt.turns[('session','turn')]['review']={'status':'NOT_REVIEWED'}
    assert 'unreviewed draft' in rt.label(draft,session_id='session',turn_id='turn')


def test_runtime_owns_review_status_even_when_model_repeats_it(rt):
    rt.turns[('session','turn')]['review']={'status':'AI_CRITIQUED'}
    result=rt.label('Answer.\n\nReview status: NOT_REVIEWED (model-written).',session_id='session',turn_id='turn')
    assert 'Answer.' in result and result.count('AI_CRITIQUED')==1
    assert 'NOT_REVIEWED' not in result and 'Review status:' not in result


def test_prior_evidence_survives_runtime_restart_without_cross_session_leak(rt,monkeypatch,tmp_path):
    monkeypatch.setenv('HERMES_HOME',str(tmp_path))
    state={'session_id':'one','evidence':['receipt evidence']}
    rt.persist_evidence(state)
    fresh=runtime.Runtime(None)
    assert fresh.prior_evidence({'session_id':'one'}) == ['receipt evidence']
    assert fresh.prior_evidence({'session_id':'two'}) == []


def test_native_skill_results_reach_critic_exactly_and_survive_restart(rt):
    seen=[]
    async def critique(messages, **kwargs):
        seen.append(json.loads(messages[-1]['content']))
        return SimpleNamespace(text='No unsupported command identified.',model='unit')
    rt.ctx=SimpleNamespace(llm=SimpleNamespace(acomplete=critique))
    state=rt.turns[('session','turn')]
    state.update(session_id='session',evidence=[],request='Explain publication',reviewed=False)
    text=json.dumps({'content':'Run python -m rgce.knowledge_publish. This does not activate a view.'})
    args={'name':'ce-knowledge','file_path':'references/onboarding.md'}
    rt.observe_skill('skill_view',args,text,session_id='session',turn_id='turn')
    response=rt.review(state,{'draft':'Use the operator publisher; activation is separate.'})
    assert response['status']=='AI_CRITIQUED' and response['skill_results']==1
    assert seen[0]['loaded_skill_results'][0]['result']==text
    assert seen[0]['loaded_skill_results'][0]['sha256']==hashlib.sha256(text.encode()).hexdigest()
    assert not seen[0]['skill_context_omitted']
    fresh=runtime.Runtime(None)
    records,omitted=fresh.review_skills({'session_id':'session'})
    assert records[0]['result']==text and records[0]['origin']=='prior session turn'
    assert not omitted and fresh.review_skills({'session_id':'unrelated'})==([],False)


def test_skill_capture_does_not_capture_other_tools_or_modify_result(rt):
    state=rt.turns[('session','turn')]
    state.update(session_id='session',evidence=[])
    assert rt.observe_skill('terminal',{},'not admitted',session_id='session',turn_id='turn') is None
    assert rt.review_skills(state)==([],False)
    rt.observe_skill('skill_view',{},'other session',session_id='unrelated',turn_id='turn')
    assert rt.review_skills(state)==([],False)


def test_skill_context_budget_is_explicit_and_new_reference_is_retained(rt):
    state={'session_id':'bounded','evidence':[]}
    rt.remember_skill(state,{'name':'large'},'x'*(rt.policy['skill_context_max_chars']+1),'current turn')
    rt.remember_skill(state,{'name':'selected'},'Complete selected reference','current turn')
    rt.persist_evidence(state)
    records,omitted=rt.review_skills(state)
    assert omitted and len(records)==1 and records[0]['result']=='Complete selected reference'
    assert len(json.dumps(records))<=rt.policy['skill_context_max_chars']


def test_history_recovers_only_actual_skill_tool_results(rt,monkeypatch):
    monkeypatch.setattr(runtime,'checked_manifest',lambda: (_ for _ in ()).throw(ValueError('offline test')))
    history=[{'role':'assistant','tool_calls':[{'id':'s1','function':{'name':'skill_view','arguments':'{"name":"ce-knowledge"}'}}]},
             {'role':'tool','tool_call_id':'unrelated','content':'not a skill result'},
             {'role':'tool','tool_call_id':'s1','content':'Exact earlier reference'}]
    rt.begin(session_id='history',turn_id='next',conversation_history=history)
    records,omitted=rt.review_skills(rt.turns[('history','next')])
    assert len(records)==1 and records[0]['result']=='Exact earlier reference'
    assert records[0]['origin']=='history' and not omitted


def test_oversized_review_does_not_call_model(rt):
    async def must_not_call(*args,**kwargs):
        pytest.fail('Oversized packet must not invoke the provider')
    rt.ctx=SimpleNamespace(llm=SimpleNamespace(acomplete=must_not_call))
    state=rt.turns[('session','turn')]
    state.update(reviewed=False,evidence=[],request='x'*100000)
    result=rt.review(state,{'draft':'Small draft'})
    assert result['status']=='NOT_REVIEWED' and 'no model call' in result['notice']


def test_three_loaded_guides_fit_without_silent_reference_loss(rt):
    state={}
    for name in ('security','reader','fix'):
        rt.remember_skill(state,{'name':name},'x'*14000,'current turn')
    assert len(state['skill_context'])==3
    assert not state.get('skill_context_omitted',False)


def test_limited_review_is_visible_without_model_cooperation(rt):
    rt.turns[('session','turn')]['review']={'status':'AI_CRITIQUED','skill_context_omitted':True}
    text=rt.label('A draft.',session_id='session',turn_id='turn')
    assert 'AI_CRITIQUED_LIMITED_CONTEXT' in text

def test_active_home_uses_hermes_profile_context_not_process_environment(monkeypatch,tmp_path):
    import sys
    from contextvars import ContextVar
    selected=ContextVar('test_profile',default=tmp_path/'default')
    monkeypatch.setenv('HERMES_HOME',str(tmp_path/'wrong-process-home'))
    monkeypatch.setitem(sys.modules,'hermes_constants',SimpleNamespace(get_hermes_home=lambda:selected.get()))
    token=selected.set(tmp_path/'ce-desk')
    try:
        assert runtime.active_home()==tmp_path/'ce-desk'
    finally:
        selected.reset(token)
    assert runtime.active_home()==tmp_path/'default'
