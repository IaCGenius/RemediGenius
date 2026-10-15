import importlib.util
import sqlite3
import time
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'profiles/native-sketch/desk/skills/ce-explain-review/scripts/review_log.py'
spec = importlib.util.spec_from_file_location('native_review_log', path)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def test_review_limits_and_excludes_content(tmp_path):
    with sqlite3.connect(tmp_path / 'state.db') as c:
        c.executescript('CREATE TABLE sessions(id TEXT, started_at REAL); '
                       'CREATE TABLE messages(session_id TEXT, role TEXT, content TEXT);')
        c.executemany('INSERT INTO sessions VALUES (?,?)', [('recent',time.time()), ('older',time.time()-100), ('expired',0)])
        c.execute('INSERT INTO messages VALUES (?,?,?)', ('recent','user','PRIVATE_CONTENT'))
    result = review.snapshot(tmp_path, days=3, limit=1)
    assert result['truncated'] is True
    assert [s['id'] for s in result['sessions']] == ['recent']
    assert result['sessions'][0]['outcome'] == 'NOT_REVIEWED'
    assert 'PRIVATE_CONTENT' not in str(result)
    assert result['sessions'][0]['message_counts'] == {'user':1}
