"""Offline synthetic evidence walkthrough; no model, cloud or console required."""
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rgce import core
from rgce.store import Store


def main():
    previous = os.environ.pop('RGCE_STORAGE_BUCKET', None)
    try:
        with tempfile.TemporaryDirectory(prefix='rgce-offline-demo-') as directory:
            store = Store(directory)
            result = core.demo(store)
            before, after = result['before'], result['after']
            comparison = core.compare(store, before['id'], after['id'])
            print(result['notice'])
            print('1. Observe: example SSH rule allows 0.0.0.0/0.')
            print('2. Assess: existing deterministic rule finds', len(before['body']['findings']), 'finding(s).')
            print('3. Proposal: operator reviews and restricts SSH source access (illustration only).')
            print('4. Reassess: second synthetic snapshot has', len(after['body']['findings']), 'finding(s).')
            print('Comparison origin:', comparison['origin'])
            print('No change was executed. This does not prove reachability or overall security.')
            print('Next: START-HERE.md for live Hermes with your AWS and model accounts.')
    finally:
        if previous is not None:
            os.environ['RGCE_STORAGE_BUCKET'] = previous


if __name__ == '__main__':
    main()
