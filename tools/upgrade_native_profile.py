"""Back up and explicitly upgrade a retained native CE profile inside Hermes.

Run as the profile owner during a maintenance window, then restart the gateway.
Never copies credentials or resets sessions, model routing, or user plugins.
"""
import argparse
import json
from pathlib import Path
import shutil
import time

try:
    import hermes_yaml as yaml
except ImportError:
    import yaml


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
    enabled=value.setdefault('plugins',{}).get('enabled',[])
    value['plugins']['enabled']=list(dict.fromkeys([*enabled,'ce-runtime']))
    value.setdefault('auxiliary',{}).setdefault('ce_review',{}).setdefault('reasoning_effort','none')
    value.setdefault('kanban',{}).update({'auto_decompose':False,'auto_promote_children':False,
        'dispatch_in_gateway':False,'review_dispatch':False,'dispatch_profiles':[]})
    pending=config.with_suffix('.pending');pending.write_text(yaml.safe_dump(value,sort_keys=False))
    pending.chmod(0o600);pending.replace(config)
    return {'backup':str(backup),'status':'UPGRADED_RESTART_REQUIRED'}


def guard_default(home):
    """Make upstream's default navigation route use the same CE boundary/provider."""
    root = home.parent.parent
    value = yaml.safe_load((home/'config.yaml').read_text())
    original = root/'config.yaml'
    backup = root/'ce-default-backups'/str(time.time_ns())
    backup.mkdir(parents=True)
    if original.exists(): shutil.copy2(original,backup/'config.yaml')
    root_value = yaml.safe_load(original.read_text()) if original.exists() else {}
    for key in ('model','agent','platform_toolsets','plugins','auxiliary','tools','memory','curator','mcp_servers'):
        if key in value: root_value[key] = value[key]
    root_value.setdefault('kanban',{}).update({'auto_decompose':False,'auto_promote_children':False,
        'dispatch_in_gateway':False,'review_dispatch':False,'dispatch_profiles':[]})
    original.write_text(yaml.safe_dump(root_value,sort_keys=False));original.chmod(0o600)
    for name in ('SOUL.md','skills','plugins'):
        target = root/name
        if target.is_symlink() and target.resolve() == (home/name).resolve(): continue
        if target.exists() or target.is_symlink(): shutil.move(str(target),str(backup/name))
        target.symlink_to(home/name,target_is_directory=name!='SOUL.md')
    return {'status':'DEFAULT_ROUTE_GUARDED','backup':str(backup)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('/opt/ce-package'))
    parser.add_argument('--home',type=Path,required=True)
    parser.add_argument('--guard-default',action='store_true')
    parser.add_argument('--guard-default-only',action='store_true')
    args=parser.parse_args()
    if not args.guard_default_only: print(json.dumps(upgrade(args.source,args.home)))
    if args.guard_default or args.guard_default_only: print(json.dumps(guard_default(args.home)))
