"""Explicit SSM acceptance of the isolated CE Docker host; stop it afterwards."""
import argparse
import json
import shlex
import subprocess
import time
from pathlib import Path
import boto3


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True,action='store_true');parser.add_argument('--expect-existing',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];private=root/'.rgce/aws-acceptance'
    cfg=json.loads((private/'rc7-host.tfvars.json').read_text(encoding='utf-8'))
    instance=subprocess.check_output(['terraform','-chdir='+str(root/'deploy/aws-workspace'),'output','-raw','instance_id'],text=True).strip()
    ec2=boto3.client('ec2',region_name=cfg['region']);ssm=boto3.client('ssm',region_name=cfg['region'])
    detail=ec2.describe_instances(InstanceIds=[instance])['Reservations'][0]['Instances'][0]
    assert any(t['Key']=='Name' and t['Value']=='rgce-workspace-acceptance' for t in detail['Tags'])
    def command(commands):
        cid=ssm.send_command(InstanceIds=[instance],DocumentName='AWS-RunShellScript',Parameters={'commands':commands,'executionTimeout':['300']})['Command']['CommandId']
        for _ in range(90):
            time.sleep(4)
            try:r=ssm.get_command_invocation(CommandId=cid,InstanceId=instance)
            except ssm.exceptions.InvocationDoesNotExist:continue
            if r['Status'] in ('Success','Failed','TimedOut','Cancelled'):
                (private/('host-command-'+cid+'.json')).write_text(json.dumps(r,default=str,indent=2),encoding='utf-8')
                if r['Status']!='Success':raise RuntimeError('SSM command failed; see private transcript')
                return r['StandardOutputContent']
        raise TimeoutError('SSM command timed out')
    try:
        for _ in range(90):
            online=ssm.describe_instance_information(Filters=[{'Key':'InstanceIds','Values':[instance]}])['InstanceInformationList']
            if online and online[0]['PingStatus']=='Online':break
            time.sleep(5)
        else:raise TimeoutError('Host did not register with SSM')
        command(['set -e','for i in $(seq 1 90); do curl -fsS http://127.0.0.1:8765/api/session >/dev/null && exit 0; sleep 3; done','tail -n 60 /var/log/cloud-init-output.log','exit 1'])
        code="""import json,urllib.request,pathlib
base='http://127.0.0.1:8765/api/'
token=json.load(urllib.request.urlopen(base+'session'))['token']
existing_count=len(json.load(urllib.request.urlopen(base+'state'))['assessments'])
request=urllib.request.Request(base+'demo',data=b'{}',headers={'Content-Type':'application/json','X-RGCE-Token':token})
demo=json.load(urllib.request.urlopen(request))
state=json.load(urllib.request.urlopen(base+'state'))
assert state['storage']['mode']=='s3'
pathlib.Path('/data/ephemeral-marker').write_text('must disappear on restart')
print(json.dumps({'assessment':demo['before']['id'],'count':len(state['assessments']),'existing_count':existing_count}))"""
        before=json.loads(command(['docker exec rgce python -c '+shlex.quote(code)]))
        if args.expect_existing: assert before['existing_count']>0, 'Replacement host did not recover the prior workspace'
        command(['docker restart rgce >/dev/null','for i in $(seq 1 60); do curl -fsS http://127.0.0.1:8765/api/session >/dev/null && exit 0; sleep 2; done','exit 1'])
        code="""import json,urllib.request,pathlib
state=json.load(urllib.request.urlopen('http://127.0.0.1:8765/api/state'))
assert not pathlib.Path('/data/ephemeral-marker').exists()
assert any(a['id']==%r for a in state['assessments'])
assert len(state['assessments'])==%r
print(json.dumps({'aws_host_health':True,'s3_mode':state['storage']['mode']=='s3','tmpfs_replaced':True,'records_survived_restart':True}))"""%(before['assessment'],before['count'])
        report=json.loads(command(['docker exec rgce python -c '+shlex.quote(code)]))
        groups=ec2.describe_security_groups(GroupIds=[g['GroupId'] for g in detail['SecurityGroups']])['SecurityGroups']
        assert all(not g['IpPermissions'] for g in groups)
        report['no_inbound_rules']=True
        report['prior_workspace_recovered']=before['existing_count']>0
        code="""import boto3,json
client=boto3.client('ssm')
try:client.get_parameter(Name='/rgce-ce-test/no-such-parameter')
except client.exceptions.ClientError as exc:
 assert exc.response['Error']['Code']=='AccessDeniedException'
 print(json.dumps({'parameter_store_read_denied':True}))
else:raise AssertionError('Host unexpectedly read Parameter Store')
"""
        report.update(json.loads(command(['docker exec rgce python -c '+shlex.quote(code)])))
        (private/'rc9-host-proof.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)
    finally:
        ec2.stop_instances(InstanceIds=[instance])
        ec2.get_waiter('instance_stopped').wait(InstanceIds=[instance])
        (private/'rc9-host-stopped.json').write_text(json.dumps({'stopped':True}),encoding='utf-8')
        print('Isolated CE test host stopped; retained S3 and EBS remain.',flush=True)


if __name__=='__main__':main()
