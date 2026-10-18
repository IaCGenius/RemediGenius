"""Boundary tests for the optional, credential-free UI sidecar."""
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_ui
from package_native_hermes import package
import zipfile


def test_sidecar_boundary():
    gateway={'State': {'Running':True},'NetworkSettings': {'Networks':{}}}
    def inspected(kind,name):
        if kind=='container' and name=='rgce-test': return gateway
        if kind=='image': return {'Id':'test'}
        return None
    with patch.object(native_ui,'inspect',side_effect=inspected), patch.object(native_ui,'run') as run:
        native_ui.start('rgce-test',9126)
    calls=[c.args for c in run.call_args_list]
    launch=next(c for c in calls if c[:3]==('docker','run','-d'))
    assert '127.0.0.1:9126:8080' in launch
    assert '--read-only' in launch and '--cap-drop' in launch
    assert '--env-file' not in launch and '-v' not in launch and '--mount' not in launch
    assert any(c[:4]==('docker','network','create','--internal') for c in calls)
    seed=next(c for c in run.call_args_list if c.args[:3]==('docker','exec','-i'))
    compile(seed.kwargs['input'],'seed','exec')


def test_refuse_unowned_container():
    with patch.object(native_ui,'inspect',return_value={'Config':{'Labels':{}}}), pytest.raises(ValueError):
        native_ui.stop('rgce-test')


def test_package_contains_ui_without_private_files(tmp_path):
    archive=tmp_path/'ce.zip';package(archive)
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
    assert 'tools/native_ui.py' in names
    for f in ['Dockerfile','patch_profile.py','nginx.conf','UPSTREAM-LICENSE']:
        assert 'deploy/hermes-ui/'+f in names
    assert not any('.env' in p or '.rgce' in p for p in names)
