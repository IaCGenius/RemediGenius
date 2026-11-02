"""A baked runtime must be invalidated when the shared dependency snapshot changes."""
import hashlib
import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize('marker_kind,install', [('missing',True),('legacy',True),('changed',True),('matching',False)])
def test_runtime_resolves_against_shared_snapshot(tmp_path, monkeypatch, marker_kind, install):
    source=Path(__file__).resolve().parents[1]/'deploy/aws-single/host.py'
    spec=importlib.util.spec_from_file_location('constraint_host',source)
    host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
    snapshot=tmp_path/'source/deploy/aws-single/aws-mcp-constraints.txt'
    snapshot.parent.mkdir(parents=True);snapshot.write_bytes(b'cachetools==7.2.7\n')
    venv=tmp_path/'venv';(venv/'bin').mkdir(parents=True);(venv/'bin/python').touch()
    code=tmp_path/'code'
    monkeypatch.setattr(host,'SOURCE',tmp_path/'source');monkeypatch.setattr(host,'VENV',venv);monkeypatch.setattr(host,'CODE',code)
    monkeypatch.setattr(host,'ensure_user',lambda:None);monkeypatch.setattr(host,'install_wrapper',lambda:None)
    monkeypatch.setattr(host,'install_zip_binary',lambda *a:None)
    monkeypatch.setattr(host.shutil,'copytree',lambda src,dst,**kw:dst.mkdir(parents=True))
    calls=[];monkeypatch.setattr(host,'run',lambda *args,**kw:calls.append(args))
    marker=None if marker_kind=='missing' else {'packages':host.PACKAGES}
    if marker_kind in ('changed','matching'):
        marker['runtime_constraints_sha256']='old' if marker_kind=='changed' else hashlib.sha256(snapshot.read_bytes()).hexdigest()
    monkeypatch.setattr(host,'baked_marker',lambda:marker)
    host.install_runtime()
    assert bool(calls)==install
    if install:
        assert calls[0][calls[0].index('-c')+1]==str(snapshot)


def test_guidance_restore_selects_only_enabled_shipped_runtime():
    source=Path(__file__).resolve().parents[1]/'deploy/aws-single/host.py'
    spec=importlib.util.spec_from_file_location('guidance_host',source)
    host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
    server={'command':'/usr/bin/env','args':['-i','/opt/data/installs/terraform-mcp/1.4.1/terraform-mcp-server','stdio']}
    assert host.terraform_guidance_selected(server)
    assert not host.terraform_guidance_selected({**server,'enabled':False})
    assert not host.terraform_guidance_selected({**server,'command':'custom-wrapper'})
    assert not host.terraform_guidance_selected({})
