"""Focused runtime tests for bounded review context and deterministic rendering.

These use constructed states only; no live AWS, model or network calls.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


runtime=module('ce_runtime_bound','profiles/ce/desk/plugins/ce-runtime/__init__.py')
workflow=module('ce_workflow_bound','profiles/ce/desk/plugins/ce-runtime/workflow.py')


@pytest.fixture
def rt(monkeypatch,tmp_path):
    monkeypatch.setenv('HERMES_HOME',str(tmp_path))
    return runtime.Runtime(SimpleNamespace())


def test_large_prior_history_is_bounded_and_disclosed(rt):
    seen=[]
    async def critique(messages,**kwargs):
        seen.append((json.loads(messages[-1]['content']),len(messages[-1]['content'])))
        return SimpleNamespace(text='No issues identified, not certified.',model='unit')
    rt.ctx=SimpleNamespace(llm=SimpleNamespace(acomplete=critique))
    state={'session_id':'big','reviewed':False,'request':'Review the current finding',
           'evidence':['prior-evidence-%02d'%i+'x'*17000 for i in range(8)],
           'collections':[{'run_id':'a'*32,'status':'OK','has_more':False}],
           'capabilities':{'targets':{'default':{'regions':['us-east-1']}},
                           'operations':{'ec2':['describe_instances']*50}}}
    for i in range(4):
        rt.remember_skill(state,{'name':'skill-%d'%i},('s%d'%i)+'r'*14000,'current turn')
    rt.persist_evidence(state)
    state['evidence']=['current-evidence'+'y'*17000]
    state['skill_context']=[]
    result=rt.review(state,{'draft':'Current draft under review'})
    assert result['status']=='AI_CRITIQUED' and seen
    payload,size=seen[0]
    assert size<=rt.policy['review_context_max_chars']
    assert payload['draft']=='Current draft under review'
    assert payload['request']=='Review the current finding'
    assert payload['collection_facts'][0]['run_id']=='a'*32
    assert payload['evidence'][0]['text'].startswith('current-evidence')
    assert len(payload['evidence'])>=5
    assert payload['configured_capabilities']['operation_counts']=={'ec2':50}
    assert 'operations' not in payload['configured_capabilities']
    assert payload['context_omitted'] and 'skill_results' in payload['context_omitted']
    assert result['context_omitted']==payload['context_omitted']


def test_review_context_max_is_policy_controlled(rt):
    assert rt.policy['review_context_max_chars']==90000


def test_review_with_no_evidence_or_skills_stays_not_grounded(rt):
    seen=[]
    async def critique(messages,**kwargs):
        seen.append(json.loads(messages[-1]['content']))
        return SimpleNamespace(text='No issues identified, not certified.',model='unit')
    rt.ctx=SimpleNamespace(llm=SimpleNamespace(acomplete=critique))
    state={'reviewed':False,'request':'Explain something','evidence':[]}
    result=rt.review(state,{'draft':'A claim'})
    assert result['status']=='NOT_GROUNDED' and seen
    assert seen[-1]['draft']=='A claim'


def test_identifier_underscores_are_not_markdown_escaped():
    run={'results':[{'request':{'action':'show','path':'raw/x.json'},'result':{'status':'OK'}}],
         'knowledge_paths':[],'knowledge':[],'outcome':'COMPLETE','critique':''}
    value={'answer':'Use ce_aws, not _emphasis_, and keep us_east_1.','observations':[],
           'knowledge':[],'proposals':[],'limits':[],'next_step':''}
    text=workflow.render_answer(value,run)
    assert 'ce_aws' in text and 'ce\\_aws' not in text and 'us_east_1' in text
    assert '\\_emphasis\\_' in text