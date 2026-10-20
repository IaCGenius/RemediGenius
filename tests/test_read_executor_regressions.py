"""Focused regression tests for the broad-reader audit-role, pagination and
normalized-summary changes.

Every SDK client, page and CSV row in this file is fabricated unit data. These
tests are not live AWS acceptance evidence and contain no credentials, keys or
real account records.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / 'deploy/collector'

# Metadata-only fixture: lifecycle flags, no passwords, keys or secret values.
CREDENTIAL_REPORT_CSV = (
    'user,arn,user_creation_time,password_enabled,password_last_used,mfa_active,access_key_1_active\n'
    'unit-user-1,arn:aws:iam::000000000000:user/unit-user-1,2026-01-01T00:00:00Z,true,N/A,true,false\n'
    'unit-user-2,arn:aws:iam::000000000000:user/unit-user-2,2026-01-02T00:00:00Z,false,N/A,false,false\n'
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_executor():
    return _load('rgce_read_executor_regression_test', COLLECTOR / 'executor.py')


@pytest.fixture(scope='module')
def catalog():
    return _load('rgce_read_catalog_regression_test', COLLECTOR / 'read_catalog.py')


def set_env(monkeypatch, targets=None, account='unit-test', extra=None):
    values = {'TARGETS': json.dumps(targets or {'default': {'regions': ['us-east-1'], 'account_id': account}}),
              'ACCOUNT_ID': account, 'BUCKET': 'unit-test', 'PREFIX': 'evidence'}
    values.update(extra or {})
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _storage(objects):
    return SimpleNamespace(put_object=lambda **kw: objects.__setitem__(kw['Key'], kw['Body']))


def _sts(assumed=None):
    class STS:
        def assume_role(self, **kwargs):
            if assumed is not None:
                assumed.append(kwargs)
            return {'Credentials': {'AccessKeyId': 'a', 'SecretAccessKey': 'b', 'SessionToken': 'c'}}
    return STS()


def _session(sts, service_client):
    return lambda **kw: SimpleNamespace(client=lambda name, **k: sts if name == 'sts' else service_client)


def _finding(index):
    return {'Id': f'unit-finding-{index:02d}',
            'ProductArn': 'arn:aws:securityhub:us-east-1::product/unit/constructed',
            'AwsAccountId': '000000000000', 'Region': 'us-east-1',
            'Title': f'Constructed finding {index}',
            'Severity': {'Label': 'CRITICAL' if index % 2 == 0 else 'HIGH'},
            'Workflow': {'Status': 'NEW'}, 'RecordState': 'ACTIVE',
            'UpdatedAt': '2026-01-01T00:00:00Z',
            'Resources': [{'Type': 'AwsEc2Instance', 'Id': f'unit-resource-{index}'}]}


def test_credential_report_admitted_as_lifecycle_metadata(catalog):
    body = json.loads((COLLECTOR / 'read-catalog.json').read_text())
    assert 'iam:GetCredentialReport' not in body['admission']['credential_exclusions']
    info = catalog.authorize('iam', 'get_credential_report')
    assert info['actions'] == ['iam:GetCredentialReport']
    classification = info['classification']
    assert classification['IsWrite'] is False
    assert classification['IsPermissionManagement'] is False
    assert classification['IsTaggingOnly'] is False
    assert info['provenance'] == 'aws-service-authorization-reference'


def test_dynamic_read_uses_audit_role_without_chaining_target_role(monkeypatch):
    module = load_executor()
    set_env(monkeypatch,
            targets={'default': {'regions': ['us-east-1'], 'account_id': 'unit-test',
                                 'role_arn': 'arn:aws:iam::unit-test:role/target'}},
            extra={'AUDIT_ROLE_ARN': 'arn:aws:iam::unit-test:role/ce-audit'})
    assumed = []

    class Dynamo:
        def can_paginate(self, operation):
            return False

        def scan(self, **kwargs):
            return {'Items': [], 'Count': 0}

    monkeypatch.setattr(module.boto3, 'Session', _session(_sts(assumed), Dynamo()))
    monkeypatch.setattr(module.boto3, 'client', lambda *a, **k: _storage({}))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'dynamodb', 'operation': 'scan',
                             'parameters': {'TableName': 'unit-table'}}, None)
    assert result['status'] == 'OK'
    # One assume_role proves the audit role is used directly, not chained through
    # the configured target role.
    assert len(assumed) == 1
    assert assumed[0]['RoleArn'] == 'arn:aws:iam::unit-test:role/ce-audit'
    assert 'PolicyArns' not in assumed[0]


def test_credential_report_normalized_without_generate_action(monkeypatch):
    module = load_executor()
    set_env(monkeypatch, extra={'AUDIT_ROLE_ARN': 'arn:aws:iam::unit-test:role/ce-audit'})
    objects, calls = {}, []
    generated_time = '2026-01-02T03:04:05+00:00'

    class IAM:
        def can_paginate(self, operation):
            return False

        def get_credential_report(self, **kwargs):
            calls.append('get_credential_report')
            return {'Content': CREDENTIAL_REPORT_CSV.encode(), 'GeneratedTime': generated_time}

        def generate_credential_report(self, **kwargs):
            raise AssertionError('executor must not generate a credential report')

    monkeypatch.setattr(module.boto3, 'Session', _session(_sts(), IAM()))
    monkeypatch.setattr(module.boto3, 'client', lambda *a, **k: _storage(objects))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'iam', 'operation': 'get_credential_report'}, None)
    assert result['status'] == 'OK'
    assert calls == ['get_credential_report']
    assert result['scope']['admitted_actions'] == ['iam:GetCredentialReport']
    report = result['summary']['reports'][0]
    assert report['generated_at'] == generated_time
    assert report['user_count'] == 2 and report['preview_truncated'] is False
    assert 'generation was not requested' in result['summary']['notice'].lower()
    normalized = json.loads(objects['evidence/normalized/' + result['run_id'] + '/credential-report.json'])
    assert normalized['reports'][0]['generated_at'] == generated_time
    assert [row['user'] for row in normalized['reports'][0]['rows']] == ['unit-user-1', 'unit-user-2']


def test_credential_report_missing_is_reported_honestly(monkeypatch):
    module = load_executor()
    set_env(monkeypatch, extra={'AUDIT_ROLE_ARN': 'arn:aws:iam::unit-test:role/ce-audit'})
    objects, calls = {}, []

    class IAM:
        def can_paginate(self, operation):
            return False

        def get_credential_report(self, **kwargs):
            calls.append('get_credential_report')
            raise ClientError({'Error': {'Code': 'CredentialReportNotPresentException'}}, 'GetCredentialReport')

        def generate_credential_report(self, **kwargs):
            raise AssertionError('executor must not generate a credential report')

    monkeypatch.setattr(module.boto3, 'Session', _session(_sts(), IAM()))
    monkeypatch.setattr(module.boto3, 'client', lambda *a, **k: _storage(objects))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'iam', 'operation': 'get_credential_report'}, None)
    assert calls == ['get_credential_report']
    assert result['status'] == 'ERROR'
    assert [e['code'] for e in result['errors']] == ['CredentialReportNotPresentException']
    assert result['has_more'] is False
    assert result['summary']['reports'] == []
    assert 'generation was not requested' in result['summary']['notice'].lower()
    normalized = json.loads(objects['evidence/normalized/' + result['run_id'] + '/credential-report.json'])
    assert normalized['reports'] == []


def test_pagination_preserves_dictionary_token_from_sdk_config(monkeypatch):
    module = load_executor()
    set_env(monkeypatch, extra={'AUDIT_ROLE_ARN': 'arn:aws:iam::unit-test:role/ce-audit'})
    requested = {}

    class Paginator:
        # SDK-style DynamoDB config: token is a dict, not a NextToken string.
        _pagination_cfg = {'input_token': 'ExclusiveStartKey', 'output_token': 'LastEvaluatedKey'}

        def paginate(self, **kwargs):
            requested.update(kwargs)
            yield {'Items': [{'id': 'constructed-1'}],
                   'LastEvaluatedKey': {'id': 'constructed-1', 'sk': '2'}}

    class Dynamo:
        def can_paginate(self, operation):
            return True

        def get_paginator(self, operation):
            return Paginator()

    monkeypatch.setattr(module.boto3, 'Session', _session(_sts(), Dynamo()))
    monkeypatch.setattr(module.boto3, 'client', lambda *a, **k: _storage({}))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'dynamodb', 'operation': 'scan',
                             'parameters': {'TableName': 'unit-table'}, 'max_pages': 1}, None)
    assert result['pages_returned'] == 1 and result['has_more'] is True
    assert result['continuation_parameters']['TableName'] == 'unit-table'
    assert result['continuation_parameters']['ExclusiveStartKey'] == {'id': 'constructed-1', 'sk': '2'}


@pytest.mark.parametrize('is_truncated,expected_more', [(False, False), (True, True)])
def test_more_results_flag_governs_pagination_stop(monkeypatch, is_truncated, expected_more):
    module = load_executor()
    set_env(monkeypatch, extra={'AUDIT_ROLE_ARN': 'arn:aws:iam::unit-test:role/ce-audit'})

    class Paginator:
        # SDK-style S3 config carries a more_results flag alongside the token.
        _pagination_cfg = {'input_token': 'ContinuationToken', 'output_token': 'NextContinuationToken',
                           'more_results': 'IsTruncated'}

        def paginate(self, **kwargs):
            yield {'Contents': [{'Key': 'constructed'}], 'NextContinuationToken': 'token-1',
                   'IsTruncated': is_truncated}

    class S3:
        def can_paginate(self, operation):
            return True

        def get_paginator(self, operation):
            return Paginator()

    monkeypatch.setattr(module.boto3, 'Session', _session(_sts(), S3()))
    monkeypatch.setattr(module.boto3, 'client', lambda *a, **k: _storage({}))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 's3', 'operation': 'list_objects_v2',
                             'parameters': {'Bucket': 'unit-bucket'}}, None)
    assert result['has_more'] is expected_more
    assert (result['continuation_parameters'] is not None) is expected_more
    if expected_more:
        assert result['continuation_parameters']['ContinuationToken'] == 'token-1'


@pytest.mark.parametrize('count,next_token,expected_status', [(24, 'next-page', 'PARTIAL'), (60, None, 'OK')])
def test_securityhub_preview_ranks_all_collected_findings(monkeypatch, count, next_token, expected_status):
    module = load_executor()
    set_env(monkeypatch)
    objects, calls = {}, []
    findings = [_finding(i) for i in range(count)][::-1]  # mixed order, HIGH before CRITICAL

    class Paginator:
        _pagination_cfg = {'input_token': 'NextToken', 'output_token': 'NextToken'}

        def paginate(self, **kwargs):
            page = {'Findings': findings}
            if next_token:
                page['NextToken'] = next_token
            yield page

    class SecurityHub:
        def can_paginate(self, operation):
            calls.append(('can_paginate', operation))
            return True

        def get_paginator(self, operation):
            calls.append(('get_paginator', operation))
            return Paginator()

    monkeypatch.setattr(module.boto3, 'Session', lambda **kw: SimpleNamespace(client=lambda *a, **k: SecurityHub()))
    monkeypatch.setattr(module.boto3, 'client', lambda *a, **k: _storage(objects))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'securityhub', 'operation': 'get_findings', 'parameters': {}}, None)
    assert result['status'] == expected_status
    summary = result['summary']
    assert summary['finding_count'] == count
    assert summary['severity_counts'] == {'CRITICAL': (count + 1) // 2, 'HIGH': count // 2}
    assert len(summary['findings_preview']) == min(count, 50)
    assert summary['preview_truncated'] is (count > 50)
    assert summary['preview_order'] == 'severity then finding ID'
    assert [f['Severity']['Label'] for f in summary['findings_preview'][:5]] == ['CRITICAL'] * 5
    # Only the one paginated read is touched; summary work makes no extra AWS call.
    assert ('get_paginator', 'get_findings') in calls
    assert all(operation == 'get_findings' for _, operation in calls)
    normalized = json.loads(objects['evidence/normalized/' + result['run_id'] + '/findings.json'])
    assert normalized['count'] == count
    assert normalized['has_more'] is (next_token is not None)
    assert normalized['errors'] == []


def test_securityhub_errors_retained_in_normalized_summary(monkeypatch):
    module = load_executor()
    set_env(monkeypatch)
    objects = {}

    class Paginator:
        _pagination_cfg = {'input_token': 'NextToken', 'output_token': 'NextToken'}

        def paginate(self, **kwargs):
            raise ClientError({'Error': {'Code': 'AccessDeniedException'}}, 'GetFindings')
            yield {}  # pragma: no cover - makes this a generator

    class SecurityHub:
        def can_paginate(self, operation):
            return True

        def get_paginator(self, operation):
            return Paginator()

    monkeypatch.setattr(module.boto3, 'Session', lambda **kw: SimpleNamespace(client=lambda *a, **k: SecurityHub()))
    monkeypatch.setattr(module.boto3, 'client', lambda *a, **k: _storage(objects))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'securityhub', 'operation': 'get_findings', 'parameters': {}}, None)
    assert result['status'] == 'ERROR'
    assert [e['code'] for e in result['errors']] == ['AccessDeniedException']
    assert result['summary']['finding_count'] == 0
    normalized = json.loads(objects['evidence/normalized/' + result['run_id'] + '/findings.json'])
    assert [e['code'] for e in normalized['errors']] == ['AccessDeniedException']
    assert normalized['has_more'] is False