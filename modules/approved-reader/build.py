"""Reuse the kiosk's hash-locked dependency layer builder and deterministic ZIP writer."""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
spec = importlib.util.spec_from_file_location('kiosk_build', ROOT / 'modules/lambda-kiosk/build.py')
kiosk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kiosk)


def source_bytes(path):
    # Git checkouts can use CRLF on Windows and LF on Linux. Pin identical source bytes.
    return path.read_text(encoding='utf-8').encode('utf-8')


def main():
    out = HERE / 'build'
    out.mkdir(exist_ok=True)
    kiosk.write_zip(out / 'runtime-layer.zip', kiosk.layer('runtime.lock'))
    files = {'handler.py': source_bytes(HERE / 'handler.py')}
    files['rgce/__init__.py'] = b'"""Approved reader adapter package."""\n'
    for name in ('onboarding.py', 'store.py'):
        files['rgce/' + name] = source_bytes(ROOT / 'rgce' / name)
    kiosk.write_zip(out / 'reader.zip', files)


if __name__ == '__main__':
    main()
