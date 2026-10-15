"""Build/start the pinned credential-free Linux validator alongside native Hermes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def run(*args, capture=False):
    return subprocess.run(args,check=True,text=True,encoding='utf-8',
        stdout=subprocess.PIPE if capture else None).stdout


def start(name):
    source=ROOT/'deploy/validator'
    lock=json.loads((source/'toolchain.json').read_text(encoding='utf-8-sig'))
    fingerprint=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(source.iterdir()) if p.is_file())).hexdigest()[:16]
    image='remedigenius-validator:'+fingerprint
    if subprocess.run(['docker','image','inspect',image],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        run('docker','build','--platform',lock['platform'],'--build-arg','TERRAFORM_VERSION='+lock['terraform'],
            '--build-arg','AWS_CLI_VERSION='+lock['aws_cli'],'--build-arg','AWS_PROVIDER_VERSION='+lock['aws_provider'],
            '--build-arg','CFN_LINT_VERSION='+lock['cfn_lint'],'--build-arg','PYTHON_IMAGE='+lock['python_image'],
            '-t',image,str(source))
    network=name+'-validation';container=name+'-validator'
    if subprocess.run(['docker','network','inspect',network],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        run('docker','network','create','--internal',network)
    else:
        details=json.loads(run('docker','network','inspect',network,capture=True))[0]
        if not details.get('Internal'): raise ValueError('Validator network must be internal')
    existing=subprocess.run(['docker','inspect',container],capture_output=True,text=True)
    if existing.returncode==0:
        value=json.loads(existing.stdout)[0]
        if value['Config']['Labels'].get('com.remedigenius.ce')!='validator':
            raise ValueError('Refusing to replace an unrelated validator container')
        run('docker','rm','-f',container)
    run('docker','run','-d','--name',container,'--label','com.remedigenius.ce=validator',
        '--network',network,'--network-alias','ce-validator','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--memory','1024m','--cpus','1','--pids-limit','128',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=256m','--restart','unless-stopped',image)
    return network


def stop(name):
    container=name+'-validator'
    result=subprocess.run(['docker','inspect',container],capture_output=True,text=True)
    if result.returncode==0 and json.loads(result.stdout)[0]['Config']['Labels'].get('com.remedigenius.ce')=='validator':
        run('docker','stop',container)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['start','stop']);p.add_argument('--name',required=True)
    a=p.parse_args();(start if a.action=='start' else stop)(a.name)
