import importlib.util
import sys
import types
from pathlib import Path

import pytest
import yaml

spec = importlib.util.spec_from_file_location('model_probe', Path(__file__).parents[1] / 'tools/model_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize('status,code', [(401,'AUTH'),(403,'AUTH'),(404,'ENDPOINT'),(429,'QUOTA'),(500,'CONNECTION')])
def test_error_does_not_echo_provider_secret(status, code):
    result = probe.failure(status, 'private-provider-response')
    assert 'CE-MODEL-'+code in result
    assert 'private-provider-response' not in result
    assert 'interactive-only' not in result


def test_probe_uses_retained_config_once_without_evidence(tmp_path, monkeypatch):
    config = tmp_path/'config.yaml'
    config.write_text('model:\n  provider: custom\n  default: retained-model\n  base_url: https://example.invalid/v1\n  key_env: MODEL_API_KEY\n')
    monkeypatch.setattr(sys, 'argv', ['probe',str(config),str(tmp_path/'missing-seed')])
    monkeypatch.setenv('MODEL_API_KEY','test-only-not-a-real-key')
    monkeypatch.setitem(sys.modules,'hermes_yaml',yaml)
    calls=[]
    def create(**kwargs):
        calls.append(kwargs)
        fn=types.SimpleNamespace(name='ce_probe',arguments='{"ok":true}')
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(tool_calls=[types.SimpleNamespace(function=fn)]))])
    def client(**kwargs):
        assert kwargs['max_retries']==0
        assert kwargs['timeout']==40
        return types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
    monkeypatch.setitem(sys.modules,'openai',types.SimpleNamespace(OpenAI=client))
    probe.main()
    assert len(calls)==1
    assert calls[0]['model']=='retained-model'
    assert calls[0]['tool_choice']=='auto'
    assert calls[0]['messages']==[{'role':'user','content':'Call ce_probe with ok=true. This is a startup connectivity test.'}]
