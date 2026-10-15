"""Compare complete source snapshots; retain original records unchanged."""
import json
from datetime import datetime

TRANSPORT = frozenset(('ResponseMetadata', 'NextToken', 'nextToken', 'Marker',
                       'NextMarker', 'ContinuationToken', 'NextContinuationToken',
                       'IsTruncated'))


def compare_snapshots(old, new):
    reasons = []
    for field in ('target', 'account_id', 'region', 'service', 'operation', 'parameters'):
        if old['scope'].get(field) != new['scope'].get(field):
            reasons.append('Different ' + field)
    if datetime.fromisoformat(new['observed_at']) <= datetime.fromisoformat(old['observed_at']):
        reasons.append('After snapshot is not newer')
    if any(x['status'] != 'OK' or x['has_more'] or x['errors'] for x in (old, new)):
        reasons.append('Incomplete or failed source query')
    result = {'origin': 'deterministic-comparison', 'version': 2,
              'before': old['run_id'], 'after': new['run_id'],
              'comparable': not reasons, 'limitations': reasons,
              'notice': 'Snapshot differences do not certify remediation, security or causality.'}
    if reasons:
        return result | {'result': 'INCOMPARABLE', 'response_changed': None}
    if (old['scope']['service'], old['scope']['operation']) == ('securityhub', 'get_findings'):
        def indexed(snapshot):
            rows = {}
            for page in snapshot['pages']:
                for finding in page.get('Findings', []):
                    key = (finding.get('ProductArn'), finding.get('Id'))
                    if not all(isinstance(v, str) and v for v in key):
                        raise ValueError('Finding identity missing')
                    if key in rows and rows[key] != finding:
                        raise ValueError('Conflicting duplicate finding identity')
                    rows[key] = finding
            return rows
        try:
            before, after = indexed(old), indexed(new)
        except ValueError as exc:
            return result | {'comparable': False, 'result': 'INCOMPARABLE',
                             'response_changed': None, 'limitations': [str(exc)]}
        added, removed = sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())
        changed = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
        different = bool(added or removed or changed)
        return result | {'comparison': 'findings-by-product-and-id',
                         'result': 'CHANGED' if different else 'UNCHANGED',
                         'response_changed': different,
                         'before_count': len(before), 'after_count': len(after),
                         'added_count': len(added), 'removed_count': len(removed),
                         'changed_count': len(changed),
                         'changed_ids': [dict(ProductArn=p, Id=i) for p, i in changed[:50]],
                         'identity_preview_truncated': len(changed) > 50}
    bodies = [json.dumps([{k: v for k, v in page.items() if k not in TRANSPORT}
                          for page in x['pages']], sort_keys=True) for x in (old, new)]
    different = bodies[0] != bodies[1]
    return result | {'comparison': 'response-pages-excluding-transport',
                     'result': 'CHANGED' if different else 'UNCHANGED',
                     'response_changed': different,
                     'notice': 'Page/order differences may remain for this service. Not a semantic resource diff or proof of a fix.'}
