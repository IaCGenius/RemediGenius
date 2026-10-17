"""SDK schema errors are recoverable evidence, not cloud-access failures."""
import json
from pathlib import Path
import subprocess
import sys

HELPER=Path(__file__).resolve().parents[1]/'profiles/ce/desk/skills/ce-aws-read/scripts/aws_read.py'

def test_nested_schema_discovery_recovers_from_wrong_root_field():
    def query(field):
        result=subprocess.run([sys.executable,str(HELPER),'schema','--service','cloudformation',
            '--operation','list_types','--field',field],capture_output=True,text=True,timeout=20)
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout)
    rejected=query('TypeNamePrefix')
    assert rejected['status']=='ERROR'
    assert rejected['errors'][0]['code']=='UNKNOWN_SCHEMA_FIELD'
    assert 'Filters' in rejected['available_fields']
    parent=query('Filters')
    assert 'TypeNamePrefix' in parent['schema']['fields']
    child=query('Filters.TypeNamePrefix')
    assert child['schema']['type']=='string'
