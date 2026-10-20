"""Focused tests for the reviewed native CE profile upgrade.

They prove the two supported config surfaces (``skills.disabled`` and the
shared-metrics offer version) are written without destroying operator settings:
model routing, opted-in telemetry, plugin choices and operator-disabled skills all
survive, and unexpected state fails closed.
"""
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def upgrade_mod():
    return _load('rgce_upgrade_native_profile_test', ROOT / 'tools/upgrade_native_profile.py')


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _ce_source(root):
    """Minimal reviewed CE package: manifest + one CE skill + SOUL."""
    _write(root / 'SOUL.md', '# CE desk\n')
    _write(root / 'plugins/ce-runtime/manifest.json', '{}\n')
    _write(root / 'skills/ce-one/SKILL.md', '---\nname: ce-one\n---\n# CE\n')
    return root


# --- telemetry offer -------------------------------------------------------

def test_settle_telemetry_records_no_thanks(upgrade_mod):
    value = {'telemetry': {'shared_metrics': {'enabled': False}}}
    report = upgrade_mod.settle_telemetry_offer(value)
    assert report['status'] == 'TELEMETRY_SETTLED'
    assert value['telemetry']['shared_metrics'] == {'enabled': False, 'send': False, 'offer_version': 2}


def test_settle_telemetry_preserves_operator_opt_in(upgrade_mod):
    value = {'telemetry': {'shared_metrics': {'enabled': True, 'send': True}}}
    upgrade_mod.settle_telemetry_offer(value)
    assert value['telemetry']['shared_metrics']['enabled'] is True
    assert value['telemetry']['shared_metrics']['send'] is True


def test_settle_telemetry_fails_closed_on_malformed_section(upgrade_mod):
    value = {'telemetry': 'not-a-mapping'}
    report = upgrade_mod.settle_telemetry_offer(value)
    assert report['status'] == 'TELEMETRY_UNCHANGED'


# --- skill admission -------------------------------------------------------

def _source_with_skills(tmp_path, names):
    root = _ce_source(tmp_path / 'source')
    for name in names:
        _write(tmp_path / 'source/skills' / name / 'SKILL.md', f'---\nname: {name}\n---\n# {name}\n')
    return tmp_path / 'source'


def test_admit_ce_skills_disables_bundled_and_keeps_operator(tmp_path, upgrade_mod):
    source = _source_with_skills(tmp_path, ['ce-one', 'ce-two'])
    home = tmp_path / 'home'
    _write(home / 'skills/.bundled_manifest', 'upstream-a:aaa\nupstream-b:bbb\n')
    value = {'skills': {'external_dirs': [], 'disabled': ['operator-custom', 'ce-one']}}
    report = upgrade_mod.admit_ce_skills(source, home, value)
    assert report['status'] == 'SKILLS_ADMITTED'
    assert value['skills']['disabled'] == ['operator-custom', 'upstream-a', 'upstream-b']
    assert value['skills']['external_dirs'] == []


def test_admit_ce_skills_fails_closed_without_ce_package(tmp_path, upgrade_mod):
    empty = tmp_path / 'empty'
    empty.mkdir()
    value = {'skills': {'disabled': ['operator-custom']}}
    report = upgrade_mod.admit_ce_skills(empty, tmp_path / 'home', value)
    assert report['status'] == 'SKILLS_UNCHANGED'
    assert value['skills']['disabled'] == ['operator-custom']


def test_admit_ce_skills_keeps_essential_skill(upgrade_mod, tmp_path):
    source = _source_with_skills(tmp_path, ['ce-one'])
    home = tmp_path / 'home'
    _write(home / 'skills/.bundled_manifest', 'hermes-agent:aaa\nupstream-a:aaa\n')
    value = {}
    upgrade_mod.admit_ce_skills(source, home, value)
    assert 'hermes-agent' not in value['skills']['disabled']
    assert value['skills']['disabled'] == ['upstream-a']


# --- full upgrade preserves operator state ---------------------------------

def test_upgrade_preserves_operator_configuration(tmp_path, upgrade_mod, monkeypatch):
    source = _source_with_skills(tmp_path, ['ce-one'])
    home = tmp_path / 'home'
    _write(home / 'skills/.bundled_manifest', 'upstream-a:aaa\n')
    original = {
        'model': {'default': 'operator-model', 'provider': 'custom'},
        'agent': {'max_turns': 24, 'api_max_retries': 2},
        'skills': {'external_dirs': [], 'disabled': ['operator-custom']},
        'telemetry': {'shared_metrics': {'enabled': True, 'send': True}},
        'plugins': {'enabled': ['operator-plugin']},
    }
    _write(home / 'config.yaml', yaml.safe_dump(original, sort_keys=False))
    # The runtime symlink is exercised implicitly; skip it on hosts without symlink rights.
    monkeypatch.setattr(Path, 'symlink_to', lambda self, target, target_is_directory=False: None)

    report = upgrade_mod.upgrade(source, home)
    value = yaml.safe_load((home / 'config.yaml').read_text(encoding='utf-8'))

    assert report['status'] == 'UPGRADED_RESTART_REQUIRED'
    assert value['model'] == original['model']
    assert value['agent']['max_turns'] == 24
    assert set(value['plugins']['enabled']) == {'operator-plugin', 'ce-runtime'}
    assert value['telemetry']['shared_metrics']['enabled'] is True
    assert value['skills']['disabled'] == ['operator-custom', 'upstream-a']
    assert (home / 'skills/ce-one/SKILL.md').is_file()
    assert json.loads(json.dumps(report))  # JSON-serializable report for the launcher


def test_upgrade_rejects_an_unreviewed_package(tmp_path, upgrade_mod):
    source = tmp_path / 'source'
    _write(source / 'SOUL.md', '# nope\n')
    home = tmp_path / 'home'
    _write(home / 'config.yaml', 'model: {}\n')
    with pytest.raises(ValueError):
        upgrade_mod.upgrade(source, home)

# --- admission against the exact deployed v0.21.7 bundled set --------------

CE_SKILLS = [
    'ce-attack-path', 'ce-aws-read', 'ce-aws-security', 'ce-business-context-prioritizer',
    'ce-case-summary', 'ce-cis-mapping', 'ce-cloudtrail-triage', 'ce-explain-review',
    'ce-iam-least-privilege', 'ce-investigation', 'ce-knowledge', 'ce-reassessment-playbook',
    'ce-s3-deep-dive', 'ce-scanner-interpreter', 'ce-source-tools', 'ce-terraform-snippets',
    'ce-validate-fix', 'shared-evidence',
]


def test_admission_matches_the_real_v0217_manifest(tmp_path, upgrade_mod):
    """Fixture is the deployed profile's skills/.bundled_manifest (Hermes v0.21.7, 71d34bad)."""
    manifest = (ROOT / 'tests/fixtures/bundled_manifest_v0.21.7.txt').read_text().split()
    assert len(manifest) == 57 and 'hermes-agent' in manifest
    home = tmp_path / 'home'
    _write(home / 'skills/.bundled_manifest', ''.join(f'{n}:deadbeef\n' for n in manifest))
    source = tmp_path / 'source'
    _write(source / 'SOUL.md', '# ce\n')
    _write(source / 'plugins/ce-runtime/manifest.json', '{}\n')
    for name in CE_SKILLS:
        _write(source / 'skills' / name / 'SKILL.md', f'---\nname: {name}\n---\n')
    value = {'skills': {'disabled': ['operator-custom']}}
    report = upgrade_mod.admit_ce_skills(source, home, value)
    disabled = set(value['skills']['disabled'])
    assert report['status'] == 'SKILLS_ADMITTED'
    assert disabled == (set(manifest) - set(CE_SKILLS) - {'hermes-agent'}) | {'operator-custom'}
    assert not (set(CE_SKILLS) & disabled)          # CE 17 + shared-evidence stay enabled
    assert 'hermes-agent' not in disabled             # essential can never be disabled
    assert 'operator-custom' in disabled              # operator's own disable preserved


# --- sticky active_profile (new-tab default scope) -------------------------

def _profile_home(tmp_path, name='ce-desk'):
    root = tmp_path / 'hermes'
    home = root / 'profiles' / name
    home.mkdir(parents=True)
    (home / 'config.yaml').write_text('model: {}\n', encoding='utf-8')
    return root, home


def _backup(root):
    path = root / 'ce-default-backups' / 't'
    path.mkdir(parents=True)
    return path


def test_active_profile_defaults_to_ce_desk(tmp_path, upgrade_mod):
    root, home = _profile_home(tmp_path)
    report = upgrade_mod._adopt_default_active_profile(root, home, _backup(root))
    assert report['status'] == 'ACTIVE_PROFILE_SET'
    assert (root / 'active_profile').read_text(encoding='utf-8') == 'ce-desk\n'


def test_active_profile_replaces_default_and_backs_up(tmp_path, upgrade_mod):
    root, home = _profile_home(tmp_path)
    (root / 'active_profile').write_text('default\n', encoding='utf-8')
    backup = _backup(root)
    report = upgrade_mod._adopt_default_active_profile(root, home, backup)
    assert report == {'status': 'ACTIVE_PROFILE_SET', 'active': 'ce-desk', 'previous': 'default'}
    assert (root / 'active_profile').read_text(encoding='utf-8') == 'ce-desk\n'
    assert (backup / 'active_profile').read_text(encoding='utf-8') == 'default\n'


def test_active_profile_preserves_operator_choice(tmp_path, upgrade_mod):
    root, home = _profile_home(tmp_path)
    (root / 'profiles' / 'operator').mkdir()
    (root / 'active_profile').write_text('operator\n', encoding='utf-8')
    backup = _backup(root)
    report = upgrade_mod._adopt_default_active_profile(root, home, backup)
    assert report['status'] == 'ACTIVE_PROFILE_PRESERVED' and report['active'] == 'operator'
    assert (root / 'active_profile').read_text(encoding='utf-8') == 'operator\n'
    assert not (backup / 'active_profile').exists()


def test_active_profile_retargets_stale_name(tmp_path, upgrade_mod):
    root, home = _profile_home(tmp_path)
    (root / 'active_profile').write_text('gone\n', encoding='utf-8')
    report = upgrade_mod._adopt_default_active_profile(root, home, _backup(root))
    assert report['status'] == 'ACTIVE_PROFILE_SET' and report['previous'] == 'gone'


def test_active_profile_noop_when_already_ce_desk(tmp_path, upgrade_mod):
    root, home = _profile_home(tmp_path)
    (root / 'active_profile').write_text('ce-desk\n', encoding='utf-8')
    report = upgrade_mod._adopt_default_active_profile(root, home, _backup(root))
    assert report['status'] == 'ACTIVE_PROFILE_PRESERVED'


def test_guard_default_wires_active_profile(tmp_path, upgrade_mod, monkeypatch):
    root, home = _profile_home(tmp_path)
    (home / 'SOUL.md').write_text('# ce\n', encoding='utf-8')
    (home / 'skills').mkdir()
    (home / 'plugins').mkdir()
    monkeypatch.setattr(Path, 'symlink_to', lambda self, target, target_is_directory=False: None)
    report = upgrade_mod.guard_default(home)
    assert report['status'] == 'DEFAULT_ROUTE_GUARDED'
    assert report['active_profile']['status'] == 'ACTIVE_PROFILE_SET'
    assert (root / 'active_profile').read_text(encoding='utf-8') == 'ce-desk\n'
