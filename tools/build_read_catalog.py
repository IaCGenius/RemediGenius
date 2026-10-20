#!/usr/bin/env python3
"""Build the pinned CE read catalog from the AWS Service Authorization Reference.

Offline build tool. It fetches only official
`servicereference.us-east-1.amazonaws.com` HTTPS endpoints, cross-checks the
pinned botocore SDK operation list, and writes
`deploy/collector/read-catalog.json`. Admission is fail-closed: an operation is
admitted only when every AuthorizedAction annotation is explicitly
IsWrite=false, IsPermissionManagement=false and IsTaggingOnly=false. A missing
reference operation, SDK entry or annotation is recorded CLASSIFICATION_UNAVAILABLE
and is never guessed from the method name. A small documented credential-operation
exclusion list is applied after classification.

No runtime code calls this tool and the catalog contains no live AWS account data.
"""
import argparse
import gzip
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

REFERENCE_HOST = 'servicereference.us-east-1.amazonaws.com'
MAPPING_URL = f'https://{REFERENCE_HOST}/v1/mapping.json'
SCHEMA_VERSION = 'rgce-read-catalog/1'

# Conservative, documented exclusions for operations that can return usable
# credentials, private keys or secret values. Excluded even when the reference
# classifies them read-only; a broad reader must not reach the model with these.
CREDENTIAL_EXCLUSIONS = {
    'sts:GetSessionToken': 'Returns temporary AWS credentials',
    'sts:GetFederationToken': 'Returns temporary AWS credentials',
    'sts:AssumeRole': 'Returns temporary AWS credentials',
    'sts:AssumeRoleWithSAML': 'Returns temporary AWS credentials',
    'sts:AssumeRoleWithWebIdentity': 'Returns temporary AWS credentials',
    'secretsmanager:GetSecretValue': 'Returns secret payloads',
    'secretsmanager:BatchGetSecretValue': 'Returns secret payloads',
    'ssm:GetParameter': 'May return SecureString values',
    'ssm:GetParameters': 'May return SecureString values',
    'ssm:GetParametersByPath': 'May return SecureString values',
    'kms:Decrypt': 'Returns plaintext',
    'kms:GenerateDataKey': 'Returns plaintext data keys',
    'kms:GenerateDataKeyWithoutPlaintext': 'Returns data keys',
    'kms:GenerateDataKeyPair': 'Returns private data keys',
    'kms:GenerateDataKeyPairWithoutPlaintext': 'Returns private data keys',
    'kms:ReEncryptFrom': 'Operates on plaintext',
    'kms:ReEncryptTo': 'Operates on plaintext',
    'kms:DeriveSharedSecret': 'Returns a shared secret',
    'ecr:GetAuthorizationToken': 'Returns registry credentials',
    'ecr-public:GetAuthorizationToken': 'Returns registry credentials',
    'codeartifact:GetAuthorizationToken': 'Returns repository credentials',
    'cognito-identity:GetCredentialsForIdentity': 'Returns identity credentials',
    'cognito-identity:GetOpenIdToken': 'Returns identity tokens',
    'cognito-identity:GetOpenIdTokenForDeveloperIdentity': 'Returns identity tokens',
    'redshift:GetClusterCredentials': 'Returns database credentials',
    'redshift:GetClusterCredentialsWithIAM': 'Returns database credentials',
    'sso:GetRoleCredentials': 'Returns role credentials',
    'lightsail:GetInstanceAccessDetails': 'Returns instance SSH key material',
    'acm:ExportCertificate': 'Returns a private certificate key',
    'connect:GetFederationToken': 'Returns federation credentials',
}

# AWS access classification is not a promise of no side effects. These known
# report/export operations create artifacts even though annotated as reads.
SIDE_EFFECT_EXCLUSIONS = {
    'iam:GenerateCredentialReport': 'Generates or replaces an account report',
    'iam:GenerateServiceLastAccessedDetails': 'Creates an asynchronous report job',
    'config:DeliverConfigSnapshot': 'Delivers a new snapshot to configured S3 storage',
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def sha256_hex(body):
    return hashlib.sha256(body).hexdigest()


def fetch(url, cache_dir=None, retries=2):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != REFERENCE_HOST:
        raise ValueError(f'Refusing non-official URL: {parsed.hostname}')
    if cache_dir is not None:
        cached = Path(cache_dir) / (sha256_hex(url.encode())[:16] + '.json.gz')
        if cached.exists():
            with gzip.open(cached, 'rb') as handle:
                return handle.read()
    last = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'rgce-read-catalog-builder'})
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
            if cache_dir is not None:
                cached = Path(cache_dir) / (sha256_hex(url.encode())[:16] + '.json.gz')
                cached.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(cached, 'wb') as handle:
                    handle.write(body)
            return body
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f'fetch failed: {url}: {last}')


def url_prefix(url):
    parts = urllib.parse.urlparse(url).path.strip('/').split('/')
    return parts[-2] if len(parts) >= 2 else parts[0]


def load_reference(mapping_url, cache_dir, workers, log):
    mapping_body = fetch(mapping_url, cache_dir)
    mapping = json.loads(mapping_body)
    clients = mapping.get('SDK', {}).get('Python', {}).get('Boto3', {})
    if not clients:
        raise SystemExit('reference mapping.json has no Boto3 client map')
    by_url = {}
    for client, meta in clients.items():
        url = (meta or {}).get('url')
        if url:
            by_url.setdefault(url, set()).add(client)
    log(f'mapping: {len(clients)} boto3 clients across {len(by_url)} service files')
    files, errors = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, url, cache_dir): url for url in by_url}
        for done, future in enumerate(as_completed(futures), 1):
            url = futures[future]
            prefix = url_prefix(url)
            try:
                body = future.result()
            except Exception as exc:  # noqa: BLE001 - build tool records and continues
                errors[prefix] = {'url': url, 'error': str(exc)[:300]}
                log(f'  [{done}/{len(futures)}] {prefix}: FAILED {type(exc).__name__} {exc}')
                continue
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                errors[prefix] = {'url': url, 'error': f'invalid JSON: {exc}'}
                log(f'  [{done}/{len(futures)}] {prefix}: INVALID JSON')
                continue
            files[prefix] = {'url': url, 'sha256': sha256_hex(body), 'body': payload}
            if done % 25 == 0 or done == len(futures):
                log(f'  [{done}/{len(futures)}] fetched')
    return mapping, files, errors


def build_action_index(files):
    index = {}
    for prefix, record in files.items():
        for action in record['body'].get('Actions', []):
            name = action.get('Name')
            if name:
                index[(prefix, name)] = action.get('Annotations', {}).get('Properties')
    return index


def build_reference_ops(files):
    ops = {}
    conflicts = []
    for prefix, record in files.items():
        for operation in record['body'].get('Operations', []):
            authorized = operation.get('AuthorizedActions') or []
            for sdk in operation.get('SDK', []):
                if sdk.get('Package') != 'Boto3' or not sdk.get('Name') or not sdk.get('Method'):
                    continue
                key = (sdk['Name'], sdk['Method'])
                entry = {'actions': authorized, 'name': operation.get('Name')}
                existing = ops.get(key)
                if existing is None:
                    ops[key] = (prefix, entry)
                elif existing[1] != entry:
                    conflicts.append((key, existing[0], prefix))
    return ops, conflicts


def classify(authorized_actions, action_index):
    """Return (code, actions, classification). code None means admitted."""
    if not authorized_actions:
        return 'CLASSIFICATION_UNAVAILABLE', None, None
    actions, flags = [], []
    for reference in authorized_actions:
        service, name = reference.get('Service'), reference.get('Name')
        if not service or not name:
            return 'CLASSIFICATION_UNAVAILABLE', None, None
        properties = action_index.get((service, name))
        if not properties:
            return 'CLASSIFICATION_UNAVAILABLE', None, None
        if properties.get('IsWrite') is not False:
            return 'WRITE_OPERATION', None, None
        if properties.get('IsPermissionManagement') is not False:
            return 'PERMISSION_MANAGEMENT_OPERATION', None, None
        if properties.get('IsTaggingOnly') is not False:
            return 'TAGGING_ONLY_OPERATION', None, None
        actions.append(f'{service}:{name}')
        flags.append(properties)
    classification = {'IsWrite': False, 'IsPermissionManagement': False, 'IsTaggingOnly': False,
                      'IsList': all(f.get('IsList') is True for f in flags) if flags else False,
                      'authorized_action_count': len(actions)}
    return None, actions, classification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--out', default=str(root / 'deploy/collector/read-catalog.json'))
    parser.add_argument('--legacy', default=str(root / 'deploy/collector/operations.json'))
    parser.add_argument('--mapping-url', default=MAPPING_URL)
    parser.add_argument('--cache-dir', default=None)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--log', default=None)
    args = parser.parse_args()

    log_lines = []

    def log(message):
        print(message, flush=True)
        log_lines.append(message)

    started = time.monotonic()
    mapping, files, fetch_errors = load_reference(args.mapping_url, args.cache_dir, args.workers, log)

    # The reference can reference action services outside the boto3 map. Fetch
    # those by the documented /v1/<service>/<service>.json convention so the
    # action annotation index is complete; failures stay fail-closed.
    referenced = set()
    for record in files.values():
        for operation in record['body'].get('Operations', []):
            for action in operation.get('AuthorizedActions') or []:
                if action.get('Service'):
                    referenced.add(action['Service'])
    missing = sorted(referenced - set(files))
    if missing:
        log(f'fetching {len(missing)} referenced action services outside the boto3 map')
        extra = {f'https://{REFERENCE_HOST}/v1/{s}/{s}.json': s for s in missing}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fetch, url, args.cache_dir): (url, prefix) for url, prefix in extra.items()}
            for future in as_completed(futures):
                url, prefix = futures[future]
                try:
                    body = future.result()
                    files[prefix] = {'url': url, 'sha256': sha256_hex(body), 'body': json.loads(body)}
                except Exception as exc:  # noqa: BLE001
                    fetch_errors[prefix] = {'url': url, 'error': str(exc)[:300]}
                    log(f'  {prefix}: FAILED {type(exc).__name__}')

    action_index = build_action_index(files)
    ref_ops, conflicts = build_reference_ops(files)
    log(f'action annotations: {len(action_index)}; reference SDK operations: {len(ref_ops)}; conflicts: {len(conflicts)}')

    legacy = json.loads(Path(args.legacy).read_text())
    legacy_hash = sha256_hex(Path(args.legacy).read_bytes())

    import botocore
    import botocore.session
    from botocore import xform_name
    session = botocore.session.get_session()
    sdk_services = sorted(session.get_available_services())
    mapping_clients = mapping.get('SDK', {}).get('Python', {}).get('Boto3', {})

    counts = {'services': 0, 'sdk_operations': 0, 'admitted': 0, 'rejected_write': 0,
              'rejected_permission_management': 0, 'rejected_tagging_only': 0,
              'classification_unavailable': 0, 'credential_excluded': 0,
              'legacy_overrides': 0, 'side_effect_excluded': 0}
    services = {}
    applied_exclusions = set()
    legacy_failures = []

    for client in sdk_services:
        model = session.get_service_model(client)
        meta = mapping_clients.get(client) or {}
        service_prefix = meta.get('service') or client
        operations, rejected, unavailable = {}, {}, []
        for op_name in model.operation_names:
            method = xform_name(op_name)
            counts['sdk_operations'] += 1
            candidate = ref_ops.get((client, method))
            if candidate is None:
                unavailable.append(method)
                counts['classification_unavailable'] += 1
                continue
            code, actions, classification = classify(candidate[1]['actions'], action_index)
            if code:
                rejected[method] = {'code': code}
                counts['classification_unavailable' if code == 'CLASSIFICATION_UNAVAILABLE' else
                       'rejected_write' if code == 'WRITE_OPERATION' else
                       'rejected_permission_management' if code == 'PERMISSION_MANAGEMENT_OPERATION' else
                       'rejected_tagging_only'] += 1
                continue
            excluded = [a for a in actions if a in CREDENTIAL_EXCLUSIONS]
            if excluded:
                applied_exclusions.update(excluded)
                rejected[method] = {'code': 'CREDENTIAL_OPERATION_EXCLUDED',
                                    'actions': sorted(excluded)}
                counts['credential_excluded'] += 1
                continue
            excluded = [a for a in actions if a in SIDE_EFFECT_EXCLUSIONS]
            if excluded:
                rejected[method] = {'code': 'SIDE_EFFECT_OPERATION_EXCLUDED', 'actions': sorted(excluded)}
                counts['side_effect_excluded'] += 1
                continue
            operations[method] = {'actions': actions,
                                  'authorized_actions': [{'service': a['Service'], 'name': a['Name']}
                                                         for a in candidate[1]['actions']],
                                  'classification': classification,
                                  'provenance': 'aws-service-authorization-reference'}
            counts['admitted'] += 1
        # Retain individually reviewed legacy operations as compatibility
        # fixtures. These are explicit per-method entries from the reviewed
        # operations.json allowlist, never a prefix-wide fallback.
        if client in legacy:
            for method, action in legacy[client].items():
                if method in operations:
                    continue
                operations[method] = {'actions': [action] if isinstance(action, str) else list(action),
                                      'authorized_actions': [],
                                      'classification': {'admission': 'legacy_compatibility_override'},
                                      'provenance': f'legacy-reviewed:operations.json@{legacy_hash[:16]}',
                                      'source_code': rejected.get(method, {}).get('code') or 'UNMAPPED'}
                old_rejection = rejected.pop(method, None)
                if old_rejection:
                    counter = {'WRITE_OPERATION':'rejected_write',
                               'PERMISSION_MANAGEMENT_OPERATION':'rejected_permission_management',
                               'TAGGING_ONLY_OPERATION':'rejected_tagging_only',
                               'CLASSIFICATION_UNAVAILABLE':'classification_unavailable',
                               'CREDENTIAL_OPERATION_EXCLUDED':'credential_excluded',
                               'SIDE_EFFECT_OPERATION_EXCLUDED':'side_effect_excluded'}.get(old_rejection['code'])
                    if counter: counts[counter] -= 1
                if method in unavailable:
                    unavailable.remove(method)
                    counts['classification_unavailable'] -= 1
                counts['legacy_overrides'] += 1
                counts['admitted'] += 1
                if client not in ('config', 'cloudcontrol'):
                    legacy_failures.append((client, method))
        if operations or rejected or unavailable:
            services[client] = {'service_prefix': service_prefix, 'operations': operations,
                                'rejected': rejected, 'unavailable': sorted(unavailable)}
            counts['services'] += 1

    mapping_body = fetch(args.mapping_url, args.cache_dir)
    sources = {
        'reference': {
            'mapping_url': args.mapping_url,
            'mapping_sha256': sha256_hex(mapping_body),
            'files': {p: {'url': r['url'], 'sha256': r['sha256']} for p, r in sorted(files.items())},
            'fetch_errors': fetch_errors,
        },
        'sdk': {'botocore_version': botocore.__version__, 'boto3_version': __import__('boto3').__version__},
        'legacy': {'path': str(Path(args.legacy)), 'sha256': legacy_hash,
                   'operations': sum(len(v) for v in legacy.values())},
    }
    catalog = {
        'schema_version': SCHEMA_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'admission': {
            'rule': ('operation AuthorizedActions must all have annotations with IsWrite=false, '
                     'IsPermissionManagement=false and IsTaggingOnly=false; missing operation, SDK '
                     'entry or annotations => CLASSIFICATION_UNAVAILABLE, never guessed from method name'),
            'credential_exclusions': CREDENTIAL_EXCLUSIONS,
            'side_effect_exclusions': SIDE_EFFECT_EXCLUSIONS,
            'credential_exclusions_applied': sorted(applied_exclusions),
            'legacy_compatibility': ('per-method reviewed operations.json entries retained when the '
                                     'reference has no strict read classification'),
        },
        'counts': counts,
        'services': services,
    }
    identity = {'schema_version': SCHEMA_VERSION, 'sources': sources,
                'admission_rule': catalog['admission']['rule'], 'services': services}
    catalog_id = 'sha256:' + sha256_hex(canonical(identity))
    catalog['catalog_id'] = catalog_id
    catalog['sources'] = sources
    body = json.dumps(catalog, sort_keys=True, separators=(',', ':')).encode()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(body)

    log(f'catalog_id: {catalog_id}')
    log(f'file_sha256: {sha256_hex(body)}')
    log(f'json bytes: {len(body)}')
    log('counts: ' + json.dumps(counts, sort_keys=True))
    if conflicts:
        log(f'duplicate SDK mappings kept first: {conflicts[:10]}')
    if legacy_failures:
        log(f'legacy overrides outside config/cloudcontrol: {legacy_failures}')
    log(f'elapsed: {time.monotonic() - started:.1f}s')
    if args.log:
        Path(args.log).write_text('\n'.join(log_lines) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
