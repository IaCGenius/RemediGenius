"""Offline pinned AWS read catalog.

Loads `read-catalog.json`, a snapshot built by `tools/build_read_catalog.py` from
the AWS Service Authorization Reference and the pinned botocore SDK schemas. The
executor uses this module instead of the fixed operations allowlist as the read
ceiling. Admission is fail-closed: an operation is admitted only when every
AuthorizedAction annotation is explicitly IsWrite=false,
IsPermissionManagement=false and IsTaggingOnly=false. Missing mappings are
CLASSIFICATION_UNAVAILABLE and are never guessed from a method name.

No network access, no credentials and no AWS account data. `read-catalog.json`
is the only source of truth; this module never expands the pinned snapshot.
"""
import hashlib
import json
from pathlib import Path

CATALOG_PATH = Path(__file__).parent / 'read-catalog.json'
CATALOG_BYTES = CATALOG_PATH.read_bytes()
CATALOG_SHA256 = hashlib.sha256(CATALOG_BYTES).hexdigest()
CATALOG = json.loads(CATALOG_BYTES)
CATALOG_ID = CATALOG.get('catalog_id', 'sha256:' + CATALOG_SHA256)

NOTICES = {
    'SIDE_EFFECT_OPERATION_EXCLUDED': 'This operation creates a report or export and is excluded from CE investigation reads.',
    'SERVICE_UNAVAILABLE': 'Service is not present in the pinned read catalog.',
    'UNKNOWN_OPERATION': 'Operation is not present in the pinned read catalog.',
    'CLASSIFICATION_UNAVAILABLE': (
        'No read-only classification is available for this operation in the pinned '
        'catalog; it is not admitted and is not guessed from its method name.'),
    'WRITE_OPERATION': (
        'AWS Service Authorization Reference classifies this operation as a write, '
        'so it is not admitted for read.'),
    'PERMISSION_MANAGEMENT_OPERATION': (
        'Operation is classified as permission management and is not admitted for read.'),
    'TAGGING_ONLY_OPERATION': (
        'Operation is classified as tagging-only and is not admitted for read.'),
    'CREDENTIAL_OPERATION_EXCLUDED': (
        'Operation can return credentials, private keys or secret values and is '
        'excluded from the broad reader even when classified read-only.'),
}


class CatalogError(Exception):
    """Typed, safe catalog rejection. Carries a short code and a short notice."""

    def __init__(self, code, notice=None):
        self.code = code
        self.notice = notice or NOTICES.get(code, 'Operation is not admitted by the read catalog.')
        super().__init__(f'{code}: {self.notice}')

    def as_dict(self):
        return {'code': self.code, 'notice': self.notice}


def catalog_summary():
    """Compact catalog identity and counts plus services with admitted operations."""
    counts = CATALOG.get('counts', {})
    services = sorted(name for name, record in CATALOG['services'].items() if record.get('operations'))
    return {
        'schema_version': CATALOG.get('schema_version'),
        'catalog_id': CATALOG_ID,
        'catalog_sha256': CATALOG_SHA256,
        'generated_at': CATALOG.get('generated_at'),
        'services': services,
        'service_count': len(services),
        'counts': counts,
        'admission_rule': CATALOG.get('admission', {}).get('rule'),
    }


def _service(service):
    if not isinstance(service, str):
        raise CatalogError('SERVICE_UNAVAILABLE')
    record = CATALOG['services'].get(service)
    if record is None:
        raise CatalogError('SERVICE_UNAVAILABLE', f'Service {service!r} is not in the pinned read catalog.')
    return record


def operations_for(service):
    """Return admitted operations (method -> entry) for one service."""
    record = _service(service)
    return record.get('operations', {})


def authorize(service, operation):
    """Return the action mapping and classification for one admitted operation.

    Raises CatalogError for unknown, unavailable, write, permission-management,
    tagging-only or credential-vending operations. Never guesses a classification.
    """
    record = _service(service)
    if not isinstance(operation, str):
        raise CatalogError('UNKNOWN_OPERATION')
    entry = record.get('operations', {}).get(operation)
    if entry is not None:
        return {'service': service, 'operation': operation, 'actions': list(entry['actions']),
                'authorized_actions': list(entry.get('authorized_actions', [])),
                'classification': entry.get('classification'), 'provenance': entry.get('provenance')}
    rejected = record.get('rejected', {}).get(operation)
    if rejected is not None:
        raise CatalogError(rejected.get('code', 'CLASSIFICATION_UNAVAILABLE'))
    if operation in record.get('unavailable', []):
        raise CatalogError('CLASSIFICATION_UNAVAILABLE')
    raise CatalogError('UNKNOWN_OPERATION')


def admitted_actions(service, operation):
    return authorize(service, operation)['actions']
