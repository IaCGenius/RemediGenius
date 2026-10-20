"""Small, deterministic account baseline and status document. No model calls."""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path


def default_checks(region):
    base = {'target': 'default', 'region': region, 'parameters': {}, 'max_pages': 2}
    return [
        base | {'service': 'config', 'operation': 'get_discovered_resource_counts'},
        base | {'service': 'config', 'operation': 'describe_configuration_recorders'},
        base | {'service': 'ec2', 'operation': 'describe_instances'},
        base | {'service': 'securityhub', 'operation': 'get_findings', 'max_pages': 10,
                'parameters': {'Filters': {'RecordState': [{'Value': 'ACTIVE', 'Comparison': 'EQUALS'}]}}},
    ]


def document(report, load):
    rows = []
    for item in report['checks']:
        request, result = item['request'], item.get('result', {})
        summary = result.get('summary', {})
        facts = {k: summary[k] for k in ('finding_count', 'severity_counts') if k in summary}
        # Derive simple inventory counts from already stored pages, not an LLM.
        if result.get('raw_path') and request['service'] in ('config', 'ec2'):
            try:
                pages = (load(result['raw_path']) or {}).get('pages', [])
                if pages and request['operation'] == 'get_discovered_resource_counts':
                    facts['recorded_resource_types'] = [
                        row for page in pages for row in page.get('resourceCounts', [])]
                elif pages and request['operation'] == 'describe_configuration_recorders':
                    facts['recorder_count'] = sum(len(p.get('ConfigurationRecorders', [])) for p in pages)
                    facts['note'] = 'Configuration only; recording status was not checked.'
                elif pages and request['operation'] == 'describe_instances':
                    states = {}
                    for page in pages:
                        for reservation in page.get('Reservations', []):
                            for instance in reservation.get('Instances', []):
                                state = instance.get('State', {}).get('Name', 'unknown')
                                states[state] = states.get(state, 0) + 1
                    facts['instances_by_state'] = states
            except Exception as exc:
                facts['summary_error'] = type(exc).__name__
        rows.append({
            'source': request['service'] + '.' + request['operation'],
            'account': result.get('scope', {}).get('account_id', os.environ.get('ACCOUNT_ID')),
            'region': request['region'], 'status': result.get('status', item.get('error', 'UNKNOWN')),
            'observed_at': result.get('observed_at'), 'pages_returned': result.get('pages_returned'),
            'has_more': result.get('has_more'), 'error_codes': [
                e.get('code', e.get('Code', 'UNKNOWN')) for e in result.get('errors', [])],
            'facts': facts, 'receipt': result.get('receipt_path'),
            'raw_path': result.get('raw_path'), 'change': item.get('comparison', {}).get('result'),
        })
    return {
        'schema': 'rgce-account-status/1', 'status': report['status'],
        'observed_at': report['observed_at'],
        'next_expected_refresh': (datetime.fromisoformat(report['observed_at']) +
                                  timedelta(hours=report['interval_hours'])).isoformat(),
        'interval_hours': report['interval_hours'], 'checks': rows,
        'notice': 'Saved bounded baseline, not full inventory or a security verdict. '
                  'Overdue refresh means stale; compute must be running. Config covers recorded resources only.',
        'context': 'Confirm account purpose, workload scope and priorities through knowledge onboarding.',
    }


def markdown(status):
    lines = ['# Account status', '', status['notice'], '',
             f"Observed: {status['observed_at']}",
             f"Next expected refresh: {status['next_expected_refresh']}",
             f"Run status: {status['status']}", '']
    for row in status['checks']:
        lines += [f"## {row['source']}", '',
                  f"Account: {row['account']} | Region: {row['region']} | Read: {row['status']}",
                  f"Pages: {row['pages_returned']} | More pages: {row['has_more']} | Change: {row['change']}",
                  '```json', json.dumps(row['facts'], indent=2), '```',
                  f"Errors: {', '.join(row['error_codes']) or 'none reported'}",
                  f"Receipt: {row['receipt']}", '']
    return '\n'.join(lines + [
        '## Confirm context', '', status['context'],
        'In ce-desk ask: "Onboard this account using the saved status."',
        'Or: "Help me onboard our knowledge. Ask one question at a time."',
        'Facts refresh automatically; user-confirmed knowledge is kept separately.',
    ])


def publish(report, load, save):
    status = document(report, load)
    save('scheduled/account-status.json', status)
    # A readable page in the existing Hermes workspace; S3 JSON remains authoritative.
    directory = Path(os.environ.get('ACCOUNT_STATUS_DIRECTORY', '/state/work'))
    if directory.parent.exists():
        directory.mkdir(parents=True, exist_ok=True)
        pending = directory / '.ACCOUNT-STATUS.md.pending'
        pending.write_text(markdown(status), encoding='utf-8')
        pending.replace(directory / 'ACCOUNT-STATUS.md')
