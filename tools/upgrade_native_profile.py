"""Back up and explicitly upgrade a retained native CE profile inside Hermes.

Run as the profile owner during a maintenance window, then restart the gateway.
Never copies credentials or resets sessions, model routing, or user plugins.

Two upstream surfaces are settled here through supported config only:

* ``skills.disabled`` keeps CE's bundled skills and any operator skill enabled while
  disabling unrelated bundled upstream skills *by name* (their files stay on disk and
  the operator can re-enable one from the dashboard Skills page).
* ``telemetry.shared_metrics.offer_version`` answers upstream's one-time
  "Help improve Hermes?" offer as CE's "No thanks" unless the operator opted in, so no
  dashboard or terminal surface asks again.
"""
import argparse
import ast
import json
from pathlib import Path
import shutil
import time

try:
    import hermes_yaml as yaml
except ImportError:
    import yaml

# Cannot be disabled from any surface (mirrors agent.skill_utils.ESSENTIAL_SKILLS).
ESSENTIAL_SKILLS = frozenset({'hermes-agent'})
_EXCLUDED_SKILL_PARTS = frozenset({
    '.git', '.github', 'node_modules', '__pycache__', '.venv', 'venv', 'site-packages',
    '.tox', '.nox', '.pytest_cache', '.mypy_cache', '.ruff_cache'})


def _skill_name(skill_md):
    """Declared skill name (YAML frontmatter ``name:``) or the skill directory name."""
    try:
        text = skill_md.read_text(encoding='utf-8', errors='replace')[:4000]
    except OSError:
        return skill_md.parent.name
    if text.startswith('---'):
        for line in text.splitlines()[1:]:
            if line.strip() == '---':
                break
            if line.lstrip().startswith('name:'):
                value = line.split(':', 1)[1].strip().strip('"\'')
                if value:
                    return value
    return skill_md.parent.name


def _discover_skill_names(root):
    """Skill names under *root* (category structure irrelevant)."""
    names = set()
    root = Path(root)
    if not root.is_dir():
        return names
    for md in root.rglob('SKILL.md'):
        if any(part in _EXCLUDED_SKILL_PARTS for part in md.parts):
            continue
        names.add(_skill_name(md))
    return names


def _names(value):
    """Config list value -> set of names (mirrors agent.skill_utils parsing)."""
    if value is None:
        return set()
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith('['):
            try:
                value = ast.literal_eval(stripped)
            except (ValueError, SyntaxError):
                value = [stripped]
        else:
            value = [stripped]
    try:
        return {str(v).strip() for v in value if str(v).strip()}
    except TypeError:
        return set()


def _bundled_skill_names(home):
    """Unrelated upstream skills seeded into this profile, by name.

    ``.bundled_manifest`` records exactly what ``hermes profile install`` seeded; the
    image's bundled/optional trees are a fallback when that manifest is missing.
    """
    names = set()
    manifest = Path(home) / 'skills/.bundled_manifest'
    if manifest.is_file():
        for line in manifest.read_text(encoding='utf-8', errors='replace').splitlines():
            name = line.partition(':')[0].strip()
            if name and not name.startswith('#'):
                names.add(name)
    for directory in _image_skill_dirs():
        names |= _discover_skill_names(directory)
    return names


def _image_skill_dirs():
    """The pinned image's bundled and optional skill trees."""
    try:
        from hermes_constants import get_bundled_skills_dir, get_optional_skills_dir
        return [get_bundled_skills_dir(), get_optional_skills_dir()]
    except Exception:
        return [Path('/opt/hermes/skills'), Path('/opt/hermes/optional-skills')]


def admit_ce_skills(source, home, value):
    """Enable CE bundled skills, keep operator skills, disable unrelated bundled ones.

    Files are never deleted: the disable list is the supported ``skills.disabled`` config.
    Any unexpected state leaves the existing ``skills`` section untouched (fail closed).
    """
    ce = _discover_skill_names(Path(source) / 'skills')
    if not ce:
        return {'status': 'SKILLS_UNCHANGED', 'reason': 'no CE package skills found'}
    bundled = _bundled_skill_names(home) - ce - ESSENTIAL_SKILLS
    if not bundled:
        return {'status': 'SKILLS_UNCHANGED', 'reason': 'no bundled upstream skills found'}
    skills = value.setdefault('skills', {})
    if not isinstance(skills, dict):
        return {'status': 'SKILLS_UNCHANGED', 'reason': 'malformed skills section'}
    # Operator disables of their OWN skills survive; CE skills are re-enabled.
    operator_disabled = _names(skills.get('disabled')) - ce - ESSENTIAL_SKILLS
    skills['disabled'] = sorted(operator_disabled | bundled)
    return {'status': 'SKILLS_ADMITTED', 'ce_enabled': len(ce), 'bundled_disabled': len(bundled)}


def settle_telemetry_offer(value):
    """Settle upstream's one-time shared-metrics offer as CE's "No thanks".

    An explicit operator opt-in (``enabled: true``) is preserved; otherwise the answer
    is recorded so the dashboard banner and the terminal offer stop asking.
    """
    telemetry = value.setdefault('telemetry', {})
    if not isinstance(telemetry, dict):
        return {'status': 'TELEMETRY_UNCHANGED', 'reason': 'malformed telemetry section'}
    section = telemetry.setdefault('shared_metrics', {})
    if not isinstance(section, dict):
        return {'status': 'TELEMETRY_UNCHANGED', 'reason': 'malformed shared_metrics section'}
    if section.get('enabled') is not True:
        section['enabled'] = False
        section['send'] = False
        section['offer_version'] = 2
    return {'status': 'TELEMETRY_SETTLED', 'enabled': section.get('enabled')}


def upgrade(source, home):
    source, home = source.resolve(), home.resolve()
    if source == home or not (source/'plugins/ce-runtime/manifest.json').is_file():
        raise ValueError('Select the mounted reviewed CE package')
    config = home/'config.yaml'
    value = yaml.safe_load(config.read_text())
    backup = home/'upgrade-backups'/str(time.time_ns())
    backup.mkdir(parents=True)
    shutil.copy2(config,backup/'config.yaml')
    for relative in ['SOUL.md'] + [p.relative_to(source).as_posix() for p in (source/'skills').rglob('*')
                                   if p.is_file() and '__pycache__' not in p.parts]:
        path=source/relative;target=home/relative
        if target.exists():
            prior=backup/relative;prior.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,prior)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    plugins=home/'plugins';plugins.mkdir(exist_ok=True)
    link=plugins/'ce-runtime'
    if link.is_symlink():
        if link.resolve()!=source/'plugins/ce-runtime':
            raise ValueError('Existing runtime symlink points elsewhere; operator review required')
    else:
        if link.exists(): shutil.move(str(link),str(backup/'ce-runtime'))
        link.symlink_to(source/'plugins/ce-runtime',target_is_directory=True)
    value.setdefault('platform_toolsets',{})['cli']=['skills','clarify','ce_runtime']
    value['platform_toolsets']['cron']=['skills','ce_runtime']
    enabled=value.setdefault('plugins',{}).get('enabled',[])
    value['plugins']['enabled']=list(dict.fromkeys([*enabled,'ce-runtime']))
    value.setdefault('auxiliary',{}).setdefault('ce_review',{}).setdefault('reasoning_effort','none')
    # Migrate only CE's prior defaults; preserve operator-selected budgets.
    agent=value.setdefault('agent',{})
    if agent.get('max_turns') == 12: agent['max_turns']=24
    if agent.get('run_budget_seconds') == 240: agent['run_budget_seconds']=480
    value.setdefault('kanban',{}).update({'auto_decompose':False,'auto_promote_children':False,
        'dispatch_in_gateway':False,'review_dispatch':False,'dispatch_profiles':[]})
    telemetry_report = settle_telemetry_offer(value)
    try:
        skills_report = admit_ce_skills(source, home, value)
    except Exception as exc:  # fail closed: never rewrite skills on unexpected state
        skills_report = {'status': 'SKILLS_UNCHANGED', 'reason': type(exc).__name__}
    pending=config.with_suffix('.pending');pending.write_text(yaml.safe_dump(value,sort_keys=False))
    pending.chmod(0o600);pending.replace(config)
    return {'backup':str(backup),'status':'UPGRADED_RESTART_REQUIRED',
            'skills':skills_report,'telemetry':telemetry_report}


def _adopt_default_active_profile(root, home, backup):
    """Make this CE profile the sticky default unless the operator chose another profile.

    Upstream stores the canonical name + newline in ``<default home>/active_profile``
    (``profiles.set_active_profile``). The dashboard's new-tab scope falls back to the
    sticky profile, so leaving it unset/``default`` routes new tabs at the guarded root
    instead of ce-desk. An explicit selection of a different *existing* profile is kept.
    """
    name = home.name
    if home.parent.name != 'profiles' or not home.is_dir():
        return {'status': 'ACTIVE_PROFILE_UNCHANGED', 'reason': 'home is not a named profile'}
    sticky = root/'active_profile'
    existing = sticky.read_text(encoding='utf-8').strip().lower() if sticky.is_file() else ''
    # A deliberate choice of another profile that still exists wins; only default/unset
    # (or a stale name with no profile dir) is retargeted to this CE profile.
    if existing and existing != 'default' and (home.parent/existing).is_dir():
        return {'status': 'ACTIVE_PROFILE_PRESERVED', 'active': existing}
    if existing == name:
        return {'status': 'ACTIVE_PROFILE_PRESERVED', 'active': existing}
    if sticky.exists():
        shutil.copy2(sticky, backup/'active_profile')
    tmp = sticky.with_suffix('.tmp')  # atomic write, same shape upstream uses
    tmp.write_text(name + '\n', encoding='utf-8')
    tmp.chmod(0o600)
    tmp.replace(sticky)
    return {'status': 'ACTIVE_PROFILE_SET', 'active': name, 'previous': existing or None}


def guard_default(home):
    """Make upstream's default navigation route use the same CE boundary/provider."""
    root = home.parent.parent
    value = yaml.safe_load((home/'config.yaml').read_text())
    original = root/'config.yaml'
    backup = root/'ce-default-backups'/str(time.time_ns())
    backup.mkdir(parents=True)
    if original.exists(): shutil.copy2(original,backup/'config.yaml')
    root_value = yaml.safe_load(original.read_text()) if original.exists() else {}
    for key in ('model','agent','platform_toolsets','plugins','auxiliary','tools','memory','curator','mcp_servers',
                'skills','telemetry'):
        if key in value: root_value[key] = value[key]
    root_value.setdefault('kanban',{}).update({'auto_decompose':False,'auto_promote_children':False,
        'dispatch_in_gateway':False,'review_dispatch':False,'dispatch_profiles':[]})
    original.write_text(yaml.safe_dump(root_value,sort_keys=False));original.chmod(0o600)
    for name in ('SOUL.md','skills','plugins'):
        target = root/name
        if target.is_symlink() and target.resolve() == (home/name).resolve(): continue
        if target.exists() or target.is_symlink(): shutil.move(str(target),str(backup/name))
        target.symlink_to(home/name,target_is_directory=name!='SOUL.md')
    active_profile = _adopt_default_active_profile(root, home, backup)
    return {'status':'DEFAULT_ROUTE_GUARDED','backup':str(backup),'active_profile':active_profile}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('/opt/ce-package'))
    parser.add_argument('--home',type=Path,required=True)
    parser.add_argument('--guard-default',action='store_true')
    parser.add_argument('--guard-default-only',action='store_true')
    args=parser.parse_args()
    if not args.guard_default_only: print(json.dumps(upgrade(args.source,args.home)))
    if args.guard_default or args.guard_default_only: print(json.dumps(guard_default(args.home)))
