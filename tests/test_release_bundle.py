import zipfile
import pytest
from tools.package_preview import inspect_source


@pytest.mark.parametrize('name', ['../escape.py', '.rgce/evidence.json', '.git/config', 'deploy/terraform.tfstate', 'auth.json'])
def test_release_rejects_private_or_unsafe_members(tmp_path, name):
    path=tmp_path/'source.zip'
    with zipfile.ZipFile(path,'w') as z:z.writestr(name,'synthetic')
    with pytest.raises(ValueError):inspect_source(path)


def test_release_scans_privacy_test_itself(tmp_path):
    path=tmp_path/'source.zip'
    with zipfile.ZipFile(path,'w') as z:z.writestr('tests/test_community.py','synthetic-private-marker')
    with pytest.raises(ValueError,match='Private identifier'):
        inspect_source(path,['synthetic-private-marker'])
