"""Opt-in selected live AWS fixture -> installed CLI file -> Docker UI API import.
No model calls; identifiers and source contents remain in ignored acceptance files.
"""
import argparse
import json
import os
import subprocess
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from uuid import uuid4


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',required=True,action='store_true')
    p.add_argument('--python',required=True)
    p.add_argument('--url',default='http://127.0.0.1:8877')
    args=p.parse_args()
    parsed=urlparse(args.url)
    assert parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and not parsed.username
    root=Path(__file__).resolve().parents[1];private=root/'.rgce/aws-acceptance'
    cfg=json.loads((private/'test.tfvars.json').read_text())
    path=private/('portable-'+uuid4().hex+'.json')
    env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
    env['RGCE_STORAGE_BUCKET']='must-not-open-storage-for-file-export'
    command=[args.python,'-m','rgce','collect-source','s3-object','--role-arn',
        f"arn:aws:iam::{cfg['account_id']}:role/RemediGeniusCommunityReadOnly",'--region',cfg.get('region','us-east-1'),
        '--location',f"s3://{cfg['fixture_name']}/inputs/sample.json",'--external-id',cfg['external_id'],
        '--consent','--output',str(path)]
    run=subprocess.run(command,cwd=private,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
    (private/'rc9-portable-cli.stderr').write_text(run.stderr,encoding='utf-8')
    assert run.returncode==0,'Collector failed; inspect private stderr'
    status=json.loads(run.stdout);assert status['status']=='exported' and not status['errors']
    payload=json.loads(path.read_text(encoding='utf-8'));assert len(payload['facts']['records'])==1
    session=json.load(urllib.request.urlopen(args.url+'/api/session'))
    assert session['version']=='0.1.0rc9'
    req=urllib.request.Request(args.url+'/api/import',data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','X-RGCE-Token':session['token']})
    result=json.load(urllib.request.urlopen(req));record=result['evidence']
    assert result['assessment'] is None
    assert record['body']['coverage']=='unknown' and record['body']['authority']=='user_import'
    assert record['body']['facts']==payload['facts']
    again=subprocess.run(command,cwd=private,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert again.returncode==2 and 'new output filename' in again.stderr
    report={'installed_cli_live_s3_export':True,'no_workspace_opened_for_export':True,
        'docker_import_preserved_facts':True,'import_did_not_promote_coverage':True,'overwrite_refused':True,'model_calls':False}
    (private/'rc9-portable-proof.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
