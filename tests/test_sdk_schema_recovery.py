"""SDK schema errors are recoverable evidence, not cloud-access failures."""
import json
from pathlib import Path
import subprocess
import sys

def test_nested_schema_discovery_recovers_from_wrong_root_field(monkeypatch):
    import importlib.util
    root=Path(__file__).resolve().parents[1]/'deploy/collector'
    monkeypatch.syspath_prepend(str(root))
    spec=importlib.util.spec_from_file_location('schema_collector',root/'server.py')
    collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
    def query(field):
        return collector.dispatch({'action':'schema','service':'cloudformation',
                                   'operation':'list_types','field':field})
    rejected=query('TypeNamePrefix')
    assert rejected['status']=='ERROR'
    assert rejected['errors'][0]['code']=='UNKNOWN_SCHEMA_FIELD'
    assert 'Filters' in rejected['available_fields']
    parent=query('Filters')
    assert 'TypeNamePrefix' in parent['schema']['fields']
    child=query('Filters.TypeNamePrefix')
    assert child['schema']['type']=='string'
