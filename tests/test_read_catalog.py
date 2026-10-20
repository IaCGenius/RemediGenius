"""Focused constructed tests for the pinned read catalog and executor admission.

These are boundary tests with stubbed SDK clients, not live AWS evidence. They
verify fail-closed classification, credential exclusions, audit-role use and
pagination preservation for the catalog-backed read path.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / 'deploy/collector'
CATALOG_PATH = COLLECTOR / 'read-catalog.json'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def catalog():
    return _load('rgce_read_catalog_test', COLLECTOR / 'read_catalog.py')


@pytest.fixture(scope='module')
def builder():
    return _load('rgce_build_read_catalog_test', ROOT / 'tools/build_read_catalog.py')


def load_executor():
    return _load('rgce_read_executor_catalog_test', COLLECTOR / 'executor.py')


def set_env(monkeypatch, targets=None, account='unit-test', extra=None):
    values = {'TARGETS': json.dumps(targets or {'default': {'regions': ['us-east-1'], 'account_id': account}}),
              'ACCOUNT_ID': account, 'BUCKET': 'unit-test', 'PREFIX': 'evidence'}
    values.update(extra or {})
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_catalog_snapshot_hashes_and_counts():
    body = json.loads(CATALOG_PATH.read_text())
    assert body['schema_version'] == 'rgce-read-catalog/1'
    assert body['catalog_id'].startswith('sha256:')
    assert body['generated_at']
    assert body['sources']['reference']['mapping_sha256']
    assert body['sources']['reference']['files']
    assert body['sources']['sdk']['botocore_version']
    counts = body['counts']
    for key in ('sdk_operations', 'admitted', 'classification_unavailable'):
        assert counts[key] > 0
    assert counts['admitted'] > 5000


def test_catalog_summary_and_operations_for_nonlegacy_service(catalog):
    summary = catalog.catalog_summary()
    assert summary['catalog_id'].startswith('sha256:')
    assert summary['counts']['admitted'] > 5000
    assert 'dynamodb' in summary['services']
    operations = catalog.operations_for('dynamodb')
    assert 'scan' in operations and operations['scan']['actions'] == ['dynamodb:Scan']
    with pytest.raises(catalog.CatalogError) as exc:
        catalog.operations_for('not-a-service')
    assert exc.value.code == 'SERVICE_UNAVAILABLE'


def test_authorize_returns_actions_and_classification(catalog):
    info = catalog.authorize('dynamodb', 'scan')
    assert info['actions'] == ['dynamodb:Scan']
    assert info['classification']['IsWrite'] is False
    assert info['classification']['IsPermissionManagement'] is False
    assert info['classification']['IsTaggingOnly'] is False
    assert info['provenance'] == 'aws-service-authorization-reference'


@pytest.mark.parametrize('operation', ['put_item', 'delete_item', 'update_item', 'transact_write_items'])
def test_mutations_rejected(catalog, operation):
    with pytest.raises(catalog.CatalogError) as exc:
        catalog.authorize('dynamodb', operation)
    assert exc.value.code == 'WRITE_OPERATION'


def test_credential_vending_operations_excluded(catalog):
    body = json.loads(CATALOG_PATH.read_text())
    assert 'secretsmanager:GetSecretValue' in body['admission']['credential_exclusions']
    assert 'kms:Decrypt' in body['admission']['credential_exclusions']
    # iam:GetCredentialReport is lifecycle metadata, not a secret; it is admitted
    # and covered by test_credential_report_admitted_as_lifecycle_metadata.
    for service, operation in (('secretsmanager', 'get_secret_value'), ('ssm', 'get_parameter')):
        with pytest.raises(catalog.CatalogError) as exc:
            catalog.authorize(service, operation)
        assert exc.value.code == 'CREDENTIAL_OPERATION_EXCLUDED'


@pytest.mark.parametrize('service,operation', [
    ('iam','generate_credential_report'), ('iam','generate_service_last_accessed_details'),
    ('config','deliver_config_snapshot')])
def test_report_generation_side_effects_are_excluded(catalog, service, operation):
    with pytest.raises(catalog.CatalogError) as exc:
        catalog.authorize(service, operation)
    assert exc.value.code == 'SIDE_EFFECT_OPERATION_EXCLUDED'


def test_missing_mapping_fails_closed(catalog):
    with pytest.raises(catalog.CatalogError) as exc:
        catalog.authorize('applicationcostprofiler', 'get_report_definition')
    assert exc.value.code == 'CLASSIFICATION_UNAVAILABLE'


def test_unknown_operation_and_service(catalog):
    with pytest.raises(catalog.CatalogError) as exc:
        catalog.authorize('dynamodb', 'not_a_real_operation')
    assert exc.value.code == 'UNKNOWN_OPERATION'
    with pytest.raises(catalog.CatalogError) as exc:
        catalog.authorize('not-a-service', 'anything')
    assert exc.value.code == 'SERVICE_UNAVAILABLE'


def test_catalog_surfaces_permission_and_tagging_codes(catalog, monkeypatch):
    monkeypatch.setitem(catalog.CATALOG['services'], 'faketest', {
        'operations': {}, 'unavailable': [],
        'rejected': {'perm': {'code': 'PERMISSION_MANAGEMENT_OPERATION'},
                     'tag': {'code': 'TAGGING_ONLY_OPERATION'}}})
    with pytest.raises(catalog.CatalogError) as exc:
        catalog.authorize('faketest', 'perm')
    assert exc.value.code == 'PERMISSION_MANAGEMENT_OPERATION'
    with pytest.raises(catalog.CatalogError) as exc:
        catalog.authorize('faketest', 'tag')
    assert exc.value.code == 'TAGGING_ONLY_OPERATION'


def test_classify_requires_every_flag_explicitly_false(builder):
    def annotations(**flags):
        return dict(flags)

    index = {
        ('svc', 'Read'): annotations(IsWrite=False, IsPermissionManagement=False, IsTaggingOnly=False),
        ('svc', 'Write'): annotations(IsWrite=True, IsPermissionManagement=False, IsTaggingOnly=False),
        ('svc', 'Perm'): annotations(IsWrite=False, IsPermissionManagement=True, IsTaggingOnly=False),
        ('svc', 'Tag'): annotations(IsWrite=False, IsPermissionManagement=False, IsTaggingOnly=True),
        ('svc', 'Missing'): {},
    }
    action = lambda name: [{'Service': 'svc', 'Name': name}]
    assert builder.classify(action('Read'), index)[0] is None
    assert builder.classify(action('Write'), index)[0] == 'WRITE_OPERATION'
    assert builder.classify(action('Perm'), index)[0] == 'PERMISSION_MANAGEMENT_OPERATION'
    assert builder.classify(action('Tag'), index)[0] == 'TAGGING_ONLY_OPERATION'
    assert builder.classify(action('Missing'), index)[0] == 'CLASSIFICATION_UNAVAILABLE'
    assert builder.classify(action('Unknown'), index)[0] == 'CLASSIFICATION_UNAVAILABLE'
    assert builder.classify([], index)[0] == 'CLASSIFICATION_UNAVAILABLE'


def test_legacy_cloudcontrol_override_has_provenance(catalog):
    info = catalog.authorize('cloudcontrol', 'list_resources')
    assert info['classification'].get('admission') == 'legacy_compatibility_override'
    assert info['provenance'].startswith('legacy-reviewed')


def test_capabilities_without_service_keeps_legacy_starting_points(catalog, monkeypatch):
    module = load_executor()
    set_env(monkeypatch)
    capabilities = module.handler({'action': 'capabilities'}, None)
    assert capabilities['dynamic_reads'] is True
    assert capabilities['recommended_operations'] == capabilities['operations']
    assert sum(len(ops) for ops in capabilities['operations'].values()) == 105
    assert capabilities['catalog']['counts']['admitted'] > 5000
    assert 'dynamodb' in capabilities['catalog']['services']


def test_capabilities_with_service_returns_catalog_operations(monkeypatch):
    module = load_executor()
    set_env(monkeypatch)
    capabilities = module.handler({'action': 'capabilities', 'service': 'dynamodb'}, None)
    assert capabilities['dynamic_reads'] is True
    assert capabilities['service'] == 'dynamodb'
    assert 'scan' in capabilities['operations']
    assert 'put_item' not in capabilities['operations']
    assert 'catalog' not in capabilities
    rejected = module.handler({'action': 'capabilities', 'service': 'not-a-service'}, None)
    assert rejected['status'] == 'ERROR' and rejected['errors'][0]['code'] == 'SERVICE_UNAVAILABLE'


def test_dynamic_read_requires_audit_role(monkeypatch):
    module = load_executor()
    set_env(monkeypatch)
    monkeypatch.delenv('AUDIT_ROLE_ARN', raising=False)
    monkeypatch.setattr(module.boto3, 'Session', lambda *a, **k: pytest.fail('Reached AWS without audit role'))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'dynamodb', 'operation': 'scan', 'parameters': {'TableName': 't'}}, None)
    assert result['status'] == 'ERROR' and result['pages_returned'] == 0
    assert result['errors'][0]['code'] == 'READ_ROLE_REQUIRED'


def test_dynamic_read_rejects_audit_role_in_other_account(monkeypatch):
    module = load_executor()
    set_env(monkeypatch, extra={'AUDIT_ROLE_ARN': 'arn:aws:iam::999999999999:role/ce-audit'})
    monkeypatch.setattr(module.boto3, 'Session', lambda *a, **k: pytest.fail('Reached AWS with foreign audit role'))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'dynamodb', 'operation': 'scan', 'parameters': {'TableName': 't'}}, None)
    assert result['status'] == 'ERROR' and result['pages_returned'] == 0
    assert result['errors'][0]['code'] == 'READ_ROLE_SCOPE_MISMATCH'


def test_dynamic_read_assumes_audit_role(catalog, monkeypatch):
    module = load_executor()
    set_env(monkeypatch, extra={'AUDIT_ROLE_ARN': 'arn:aws:iam::unit-test:role/ce-audit'})
    assumed, sessions, objects = [], [], {}

    class STS:
        def assume_role(self, **kwargs):
            assumed.append(kwargs)
            return {'Credentials': {'AccessKeyId': 'a', 'SecretAccessKey': 'b', 'SessionToken': 'c'}}

    class Dynamo:
        def can_paginate(self, operation):
            return False

        def scan(self, **kwargs):
            return {'Items': [], 'Count': 0}

    class Session:
        def __init__(self, **kwargs):
            sessions.append(kwargs)

        def client(self, name, **kwargs):
            return STS() if name == 'sts' else Dynamo()

    monkeypatch.setattr(module.boto3, 'Session', Session)
    monkeypatch.setattr(module.boto3, 'client',
                        lambda *a, **k: SimpleNamespace(put_object=lambda **kw: objects.__setitem__(kw['Key'], kw['Body'])))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'dynamodb', 'operation': 'scan', 'parameters': {'TableName': 't'}}, None)
    assert result['status'] == 'OK'
    assert len(assumed) == 1
    assert assumed[0]['RoleArn'] == 'arn:aws:iam::unit-test:role/ce-audit'
    assert json.loads(assumed[0]['Policy'])['Statement'][0]['Action'] == ['dynamodb:Scan']
    assert any(session.get('aws_access_key_id') == 'a' for session in sessions)


def test_executor_rejects_mutation_and_missing_mapping_without_aws(monkeypatch):
    module = load_executor()
    set_env(monkeypatch)
    monkeypatch.setenv('AUDIT_ROLE_ARN', 'arn:aws:iam::unit-test:role/ce-audit')
    monkeypatch.setattr(module.boto3, 'Session', lambda *a, **k: pytest.fail('Reached AWS on rejected request'))
    mutation = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                               'service': 'dynamodb', 'operation': 'put_item',
                               'parameters': {'TableName': 't', 'Item': {}}}, None)
    assert mutation['errors'][0]['code'] == 'WRITE_OPERATION'
    missing = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                              'service': 'applicationcostprofiler', 'operation': 'get_report_definition'}, None)
    assert missing['errors'][0]['code'] == 'CLASSIFICATION_UNAVAILABLE'


def test_dynamic_read_preserves_pagination_tokens(monkeypatch):
    module = load_executor()
    set_env(monkeypatch, extra={'AUDIT_ROLE_ARN': 'arn:aws:iam::unit-test:role/ce-audit'})

    class Paginator:
        _pagination_cfg = {'input_token': 'NextToken', 'output_token': 'NextToken'}

        def paginate(self, **kwargs):
            yield {'Items': [{'id': '1'}], 'NextToken': 'tok-1'}
            yield {'Items': [{'id': '2'}], 'NextToken': 'tok-2'}

    class Dynamo:
        def can_paginate(self, operation):
            return True

        def get_paginator(self, operation):
            return Paginator()

    class STS:
        def assume_role(self, **kwargs):
            return {'Credentials': {'AccessKeyId': 'a', 'SecretAccessKey': 'b', 'SessionToken': 'c'}}

    monkeypatch.setattr(module.boto3, 'Session',
                        lambda **kwargs: SimpleNamespace(client=lambda name, **k: STS() if name == 'sts' else Dynamo()))
    monkeypatch.setattr(module.boto3, 'client', lambda *a, **k: SimpleNamespace(put_object=lambda **kw: None))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'dynamodb', 'operation': 'scan', 'parameters': {'TableName': 't'},
                             'max_pages': 1}, None)
    assert result['pages_returned'] == 1 and result['has_more'] is True
    assert result['continuation_parameters']['NextToken'] == 'tok-1'


def test_wrong_region_rejected_before_aws(monkeypatch):
    module = load_executor()
    set_env(monkeypatch)
    monkeypatch.setattr(module.boto3, 'Session', lambda *a, **k: pytest.fail('Reached AWS with wrong region'))
    with pytest.raises(ValueError, match='outside configured scope'):
        module.handler({'action': 'read', 'target': 'default', 'region': 'eu-west-1',
                        'service': 'dynamodb', 'operation': 'scan'}, None)


def test_legacy_operation_keeps_prior_behavior_without_audit_role(monkeypatch):
    module = load_executor()
    set_env(monkeypatch)
    monkeypatch.delenv('AUDIT_ROLE_ARN', raising=False)
    calls = []
    objects = {}

    class Config:
        def can_paginate(self, operation):
            return False

        def describe_configuration_recorder_status(self, **parameters):
            calls.append(parameters)
            return {'ConfigurationRecordersStatus': []}

    monkeypatch.setattr(module.boto3, 'Session', lambda *a, **k: SimpleNamespace(client=lambda *a, **kw: Config()))
    monkeypatch.setattr(module.boto3, 'client',
                        lambda *a, **k: SimpleNamespace(put_object=lambda **kw: objects.__setitem__(kw['Key'], kw['Body'])))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1', 'service': 'config',
                             'operation': 'describe_configuration_recorder_status', 'parameters': {}}, None)
    assert result['status'] == 'OK' and calls == [{}]


def test_executor_credential_operation_excluded_without_aws(monkeypatch):
    module = load_executor()
    set_env(monkeypatch)
    monkeypatch.setattr(module.boto3, 'Session', lambda *a, **k: pytest.fail('Reached AWS on excluded credential read'))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'secretsmanager', 'operation': 'get_secret_value',
                             'parameters': {'SecretId': 'x'}}, None)
    assert result['errors'][0]['code'] == 'CREDENTIAL_OPERATION_EXCLUDED'


def test_dynamic_cloudcontrol_keeps_downstream_read_policies(monkeypatch):
    module = load_executor()
    set_env(monkeypatch, extra={'AUDIT_ROLE_ARN': 'arn:aws:iam::unit-test:role/ce-audit'})
    assumed = []

    class STS:
        def assume_role(self, **kwargs):
            assumed.append(kwargs)
            return {'Credentials': {'AccessKeyId': 'a', 'SecretAccessKey': 'b', 'SessionToken': 'c'}}

    class CloudControl:
        def can_paginate(self, operation):
            return False

        def list_resource_requests(self, **kwargs):
            return {'ResourceRequestStatusSummaries': []}

    monkeypatch.setattr(module.boto3, 'Session',
                        lambda **kw: SimpleNamespace(client=lambda name, **k: STS() if name == 'sts' else CloudControl()))
    monkeypatch.setattr(module.boto3, 'client', lambda *a, **k: SimpleNamespace(put_object=lambda **kw: None))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'cloudcontrol', 'operation': 'list_resource_requests',
                             'parameters': {'TypeName': 'AWS::EC2::Instance'}}, None)
    assert result['status'] == 'OK'
    arns = [p['arn'] for p in assumed[0]['PolicyArns']]
    assert any(a.endswith('SecurityAudit') for a in arns)
    assert any(a.endswith('job-function/ViewOnlyAccess') for a in arns)
    assert json.loads(assumed[0]['Policy'])['Statement'][0]['Action'] == ['cloudformation:ListResourceRequests']


def test_legacy_cloudcontrol_role_retains_downstream_policies(monkeypatch):
    module = load_executor()
    set_env(monkeypatch, targets={'default': {'regions': ['us-east-1'], 'account_id': 'unit-test',
                                              'role_arn': 'arn:aws:iam::unit-test:role/target'}})
    assumed = []

    class STS:
        def assume_role(self, **kwargs):
            assumed.append(kwargs)
            return {'Credentials': {'AccessKeyId': 'a', 'SecretAccessKey': 'b', 'SessionToken': 'c'}}

    class CloudControl:
        def can_paginate(self, operation):
            return False

        def list_resources(self, **kwargs):
            return {'ResourceDescriptions': []}

    monkeypatch.setattr(module.boto3, 'Session',
                        lambda **kw: SimpleNamespace(client=lambda name, **k: STS() if name == 'sts' else CloudControl()))
    monkeypatch.setattr(module.boto3, 'client', lambda *a, **k: SimpleNamespace(put_object=lambda **kw: None))
    result = module.handler({'action': 'read', 'target': 'default', 'region': 'us-east-1',
                             'service': 'cloudcontrol', 'operation': 'list_resources',
                             'parameters': {'TypeName': 'AWS::EC2::Instance'}}, None)
    assert result['status'] == 'OK'
    arns = [p['arn'] for p in assumed[0]['PolicyArns']]
    assert any(a.endswith('SecurityAudit') for a in arns)
    assert json.loads(assumed[0]['Policy'])['Statement'][0]['Action'] == 'cloudformation:ListResources'


def test_dockerfile_copies_catalog_snapshot():
    dockerfile = (COLLECTOR / 'Dockerfile').read_text()
    assert 'read-catalog.json' in dockerfile
    assert CATALOG_PATH.exists()
