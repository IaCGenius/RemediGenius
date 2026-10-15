"""Constructed output-pattern and input-boundary tests, not live AWS evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile
import pytest
from tools.package_native_hermes import package

ROOT=Path(__file__).resolve().parents[1]
def load(relative):
    spec=importlib.util.spec_from_file_location('subject',ROOT/relative)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
runtime=load('profiles/ce/desk/plugins/ce-runtime/__init__.py')

@pytest.mark.parametrize('text',[
 'aws iam attach-role-policy --role-name example --policy-arn arn:aws:iam::aws:policy/AdministratorAccess',
 'aws iam create-access-key --user-name example',
 'aws cloudtrail stop-logging --name example',
 'aws guardduty delete-detector --detector-id example',
 'aws inspector2 disable --resource-types EC2',
 'aws macie2 disable-macie',
 'aws ec2 authorize-security-group-ingress --cidr 0.0.0.0/0',
 'ingress { cidr_ipv6 = "::/0" }',
 'BlockPublicAcls: false',
 'aws s3api put-bucket-acl --acl public-read',
 '{"Action": ["*"], "Resource": "*"}',
 '{"Principal": {"AWS": "*"}}',
 '{"Principal": {"AWS": "arn:aws:iam::'+('9'*12)+':root"}}',
])
def test_high_risk_patterns_are_fixed_runtime_warnings(text):
    result=runtime.proposal_check(text,{'8'*12})
    assert 'Deterministic check:' in result
    assert runtime.PROPOSAL_NOTICE in result
    assert text in result

def test_read_command_not_flagged_but_not_certified():
    result=runtime.proposal_check('```sh\naws ec2 describe-instances\n```')
    assert 'Deterministic check:' not in result
    assert runtime.PROPOSAL_NOTICE in result

def test_plain_answer_is_not_littered_with_command_warnings():
    assert runtime.proposal_check('No current evidence was collected.')=='No current evidence was collected.'
    text='CIS AWS Foundations 2.5. Why BlockPublicPolicy=false alone does not prove a public bucket: inspect the effective policy.'
    assert runtime.proposal_check(text)==text

def test_known_account_trust_does_not_trigger_unknown_account_match():
    account='8'*12
    result=runtime.proposal_check('```json\n{"Principal":{"AWS":"arn:aws:iam::'+account+':root"}}\n```',{account})
    assert 'outside configured targets' not in result

def test_packaging_covers_every_shipped_skill_and_reference(tmp_path):
    output=tmp_path/'native.zip';package(output)
    with zipfile.ZipFile(output) as z:
        manifest=json.loads(z.read('profiles/ce/desk/plugins/ce-runtime/manifest.json'))['files']
        skills=[n for n in z.namelist() if n.startswith('profiles/ce/desk/skills/') and n.endswith('.md')]
        assert len([n for n in skills if n.endswith('/SKILL.md')])>=16
        for name in skills:
            relative=name.removeprefix('profiles/ce/desk/')
            assert manifest[relative]==hashlib.sha256(z.read(name)).hexdigest()

@pytest.mark.parametrize('change,match',[
 ({'target':'unknown'},'Unknown target'),
 ({'target':None},'requires target'),
 ({'parameters':{}},'StartTime and EndTime'),
 ({'parameters':{'StartTime':False,'EndTime':'bad'}},'ISO-8601'),
 ({'parameters':{'StartTime':'bad','EndTime':'bad'}},'ISO-8601'),
])
def test_invalid_read_never_reaches_aws(monkeypatch,change,match):
    module=load('modules/aws-read-executor/executor.py')
    monkeypatch.setenv('TARGETS',json.dumps({'default':{'regions':['us-east-1'],'account_id':'unit'}}))
    monkeypatch.setattr(module.boto3,'Session',lambda:pytest.fail('Invalid request reached AWS'))
    request={'action':'read','target':'default','region':'us-east-1','service':'cloudtrail','operation':'lookup_events','parameters':{}}
    request.update(change)
    with pytest.raises(ValueError,match=match):module.handler(request,None)
