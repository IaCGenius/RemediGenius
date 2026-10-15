"""Bounded, read-only native Hermes metadata export. Never exports chat content."""
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path


def snapshot(home, days=3, limit=10):
    if not 1 <= days <= 30 or not 1 <= limit <= 50:
        raise ValueError('days must be 1..30 and limit 1..50')
    db = Path(home).resolve() / 'state.db'
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        now = dt.datetime.now(dt.timezone.utc)
        cutoff = (now - dt.timedelta(days=days)).timestamp()
        rows = con.execute('SELECT id, started_at FROM sessions WHERE started_at >= ? '
                           'ORDER BY started_at DESC LIMIT ?', (cutoff, limit + 1)).fetchall()
        sessions = []
        for row in rows[:limit]:
            counts = con.execute('SELECT role, COUNT(*) AS n FROM messages '
                                 'WHERE session_id=? GROUP BY role', (row['id'],)).fetchall()
            sessions.append(dict(id=row['id'], started_at=row['started_at'],
                                 message_counts={r['role']: r['n'] for r in counts},
                                 outcome='NOT_REVIEWED'))
    return dict(schema='rgce-review-index/1', generated_at=now.isoformat(), days=days,
                truncated=len(rows) > limit, sessions=sessions,
                limitations=['Metadata only: messages and secrets excluded.',
                             'Message counts do not prove success, retries, token usage or cost.',
                             'Operator selects session detail for review; outcomes are not inferred.'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=Path, required=True)
    p.add_argument('--days', type=int, default=3)
    p.add_argument('--limit', type=int, default=10)
    args = p.parse_args()
    print(json.dumps(snapshot(args.home, args.days, args.limit), indent=2))
