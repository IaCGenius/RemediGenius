"""Trusted host-only process. Never mount Docker's socket in CE or Hermes."""
import hashlib
import json
import os
import queue
import re
import subprocess
import threading
import time
import contextlib
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4


def atomic(path, value):
    # Directory descriptors prevent a spool symlink from redirecting a root write.
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    pending = '.pending-' + uuid4().hex
    try:
        fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=directory)
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(value))
        os.rename(pending, path.name, src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        os.close(directory)


def identity(envfile):
    values = {}
    for line in envfile.read_text(encoding='utf-8').splitlines():
        key, sep, value = line.partition('=')
        if sep and key in ('RGCE_MODEL_PROVIDER', 'RGCE_MODEL_NAME', 'RGCE_MODEL_BASE_URL', 'RGCE_MODEL_KEY_ENV'):
            values[key] = value
    config_digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    return values.get('RGCE_MODEL_PROVIDER', ''), values.get('RGCE_MODEL_NAME', ''), config_digest


def validate(folder, config_digest=None):
    if folder.is_symlink() or not re.fullmatch('[a-f0-9]{32}', folder.name):
        raise ValueError('Invalid job directory')
    request = folder / 'request.json'
    if request.is_symlink() or request.stat().st_size > 200000:
        raise ValueError('Invalid request')
    payload = json.loads(request.read_text(encoding='utf-8'))
    if payload.get('job_id') != folder.name:
        raise ValueError('Job identity mismatch')
    if config_digest is not None and payload.get('config_digest') != config_digest:
        raise ValueError('Model configuration changed after consent')
    inputs = folder / 'input'
    if inputs.is_symlink():
        raise ValueError('Invalid input directory')
    total = 0
    actual_files = set()
    for path in inputs.rglob('*'):
        if path.is_symlink() or not path.resolve().is_relative_to(inputs.resolve()):
            raise ValueError('Input must contain ordinary files')
        if path.is_file():
            actual_files.add(path.relative_to(inputs).as_posix())
            total += path.stat().st_size
            if total > 2_100_000 or path.stat().st_size > 1_048_576 or len(actual_files) > 512:
                raise ValueError('Input exceeds limit')
            os.chmod(path, 0o444)
        else:
            os.chmod(path, 0o555)
    if actual_files != set(payload['files']):
        raise ValueError('Unexpected snapshot files')
    for name, expected in payload['files'].items():
        path = inputs / name
        if not path.resolve().is_relative_to(inputs.resolve()):
            raise ValueError('Input path escape')
        text = path.read_text(encoding='utf-8')
        actual = hashlib.sha256(json.dumps(text, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        if actual != expected:
            raise ValueError('Input hash mismatch')
    os.chmod(inputs, 0o555)


def execute(folder, image, envfile, network, heartbeat):
    if folder.is_symlink() or not re.fullmatch('[a-f0-9]{32}', folder.name):
        return
    name = 'rgce-agent-' + folder.name
    result = {'state': 'failed', 'text': '', 'error': 'The agent did not complete. Inspect host diagnostics.'}
    process = None
    try:
        validate(folder, identity(envfile)[2])
        if (folder / 'cancel').exists():
            result = {'state': 'cancelled', 'text': ''}
            return
        command = ['docker', 'run', '--rm', '--name', name, '--network', network,
            '--user', '10001:10001', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--memory', '3g', '--cpus', '2', '--pids-limit', '256',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=256m,mode=1777',
            '--env-file', str(envfile), '--env', 'AWS_EC2_METADATA_DISABLED=true',
            '--mount', 'type=bind,source=' + str(folder / 'input') + ',target=/input,readonly', image]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8')
        events = queue.Queue(maxsize=100)
        def read():
            while True:
                line = process.stdout.readline(300001)
                if not line:
                    break
                if len(line) > 300000:
                    continue
                try:
                    events.put(json.loads(line), timeout=1)
                except (ValueError, queue.Full):
                    continue
        threading.Thread(target=read, daemon=True).start()
        deadline = time.monotonic() + 300
        atomic(folder / 'progress.json', {'tool_calls': 0})
        while time.monotonic() < deadline:
            heartbeat()
            if (folder / 'cancel').exists():
                result = {'state': 'cancelled', 'text': ''}
                break
            try:
                event = events.get(timeout=.5)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            if event.get('type') == 'progress':
                atomic(folder / 'progress.json', {'tool_calls': min(int(event.get('tool_calls', 0)), 1000)})
            elif event.get('type') == 'result':
                if event.get('state') == 'completed' and event.get('exit_code') == 0 and isinstance(event.get('text'), str) and 0 < len(event['text']) <= 200000:
                    result = {'state': 'completed', 'text': event['text']}
                else:
                    result = {'state': 'failed', 'text': '', 'error': 'Hermes did not return a complete result. Check the model configuration and retry.'}
                    stage = event.get('error_stage', '')
                    if isinstance(stage, str) and re.fullmatch('[a-z_]{1,40}', stage):
                        result['error'] += ' Stage: ' + stage + '.'
                break
        else:
            result['error'] = 'Investigation exceeded the five-minute runtime limit.'
    except (OSError, ValueError, KeyError, TypeError):
        result = {'state': 'failed', 'text': '', 'error': 'Agent launch or snapshot validation failed.'}
    finally:
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if process:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        result['finished_at'] = datetime.now(timezone.utc).isoformat()
        if not folder.is_symlink():
            atomic(folder / 'result.json', result)


def main():
    root = Path(os.environ['RGCE_HERMES_JOBS'])
    image = os.environ['RGCE_HERMES_IMAGE']
    envfile = Path(os.environ['RGCE_HERMES_ENV_FILE'])
    network = os.environ['RGCE_HERMES_NETWORK']
    import fcntl
    lock = (root / 'broker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    provider, model, config_digest = identity(envfile)
    if not provider or not model:
        raise SystemExit('Model identity is not configured')
    def heartbeat():
        atomic(root / 'status.json', {'ready': True, 'provider': provider, 'model': model, 'image': image, 'config_digest': config_digest,
            'notice': 'On-demand Hermes investigations. Selected evidence is sent only after your consent.'})
    # A broker restart never silently repeats a potentially charged model call.
    for folder in root.iterdir():
        if not folder.is_symlink() and re.fullmatch('[a-f0-9]{32}', folder.name) and folder.is_dir() and (folder / 'claimed').exists() and not (folder / 'result.json').exists():
            if re.fullmatch('[a-f0-9]{32}', folder.name):
                with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                    subprocess.run(['docker', 'rm', '-f', 'rgce-agent-' + folder.name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            atomic(folder / 'result.json', {'state': 'interrupted', 'text': '', 'error': 'Agent host restarted. Start a fresh investigation.'})
    while True:
        heartbeat()
        for folder in sorted(root.iterdir()):
            if not folder.is_symlink() and re.fullmatch('[a-f0-9]{32}', folder.name) and folder.is_dir() and (folder / 'ready').exists() and not (folder / 'claimed').exists():
                try:
                    with (folder / 'claimed').open('x'):
                        pass
                except FileExistsError:
                    continue
                execute(folder, image, envfile, network, heartbeat)
        time.sleep(1)


if __name__ == '__main__':
    main()
