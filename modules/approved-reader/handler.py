"""Operator-approved kiosk reader. Fixed reviewed code; no runtime code generation."""
import json
import os
import platform
import boto3
from rgce.onboarding import collect, plan
from rgce.store import digest, now


def main(event, context):
    if os.environ.get('RGCE_ENABLED') != 'true':
        raise PermissionError('Reader is paused')
    spec = json.loads(os.environ['RGCE_SOURCE'])
    expected = plan(**spec)['plan_hash']
    if not isinstance(event, dict) or set(event) != {'consent', 'plan_hash'} or event['consent'] is not True or event['plan_hash'] != expected:
        raise PermissionError('Explicit consent for the deployed source plan is required')
    payload = collect(spec, consent=True, external_id=os.environ['RGCE_EXTERNAL_ID'])
    receipt = {'collected_at': now(), 'request_id': context.aws_request_id, 'plan_hash': expected,
        'code_sha256': os.environ['RGCE_CODE_SHA256'], 'python': platform.python_version(),
        'boto3': boto3.__version__, 'evidence_hash': digest(payload), 'evidence': payload}
    key = 'outputs/reader/' + context.aws_request_id + '.json'
    boto3.client('s3').put_object(Bucket=os.environ['RGCE_OUTPUT_BUCKET'], Key=key,
        Body=json.dumps(receipt, allow_nan=False).encode(), ContentType='application/json', ServerSideEncryption='AES256')
    return {'key': key, 'evidence_hash': receipt['evidence_hash'], 'coverage': payload['coverage'], 'errors': payload['errors']}
