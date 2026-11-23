"""Bounded read models and additive migrations for the unchanged paper ledger."""
import json
from pathlib import Path
import sqlite3

SCHEMA_VERSION = 1


def connect(path, readonly=False):
    path = Path(path).resolve()
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10) if readonly else sqlite3.connect(path, timeout=10)
    conn.execute('PRAGMA busy_timeout=10000')
    return conn


def migrate(path):
    """Never rewrite account JSON, policy fingerprints or historical trades."""
    with connect(path) as conn:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError('Ledger schema is newer than this application')
        for table, required in [('account', {'id', 'body'}), ('trades', {'id', 'entry', 'body'}), ('events', {'timestamp', 'body'})]:
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            if not required <= columns:
                raise ValueError('Unrecognised paper ledger schema')
        conn.execute('PRAGMA journal_mode=WAL')
        if version == 0:
            conn.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ledger_totals(id INTEGER PRIMARY KEY CHECK(id=1), trades INTEGER NOT NULL, pnl REAL NOT NULL);
                INSERT OR IGNORE INTO ledger_totals SELECT 1,COUNT(*),COALESCE(SUM(json_extract(body,'$.net_pnl_rs')),0) FROM trades;
                CREATE TRIGGER IF NOT EXISTS ledger_total_insert AFTER INSERT ON trades BEGIN
                    UPDATE ledger_totals SET trades=trades+1,pnl=pnl+COALESCE(json_extract(NEW.body,'$.net_pnl_rs'),0) WHERE id=1;
                END;
                CREATE TRIGGER IF NOT EXISTS ledger_total_delete AFTER DELETE ON trades BEGIN
                    UPDATE ledger_totals SET trades=trades-1,pnl=pnl-COALESCE(json_extract(OLD.body,'$.net_pnl_rs'),0) WHERE id=1;
                END;
                CREATE TRIGGER IF NOT EXISTS ledger_total_update AFTER UPDATE ON trades BEGIN
                    UPDATE ledger_totals SET pnl=pnl-COALESCE(json_extract(OLD.body,'$.net_pnl_rs'),0)+COALESCE(json_extract(NEW.body,'$.net_pnl_rs'),0) WHERE id=1;
                END;
                INSERT OR IGNORE INTO schema_migrations VALUES(1,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
                PRAGMA user_version=1;
                COMMIT;
            ''')


def snapshot(path, trade_limit=200, event_limit=1000):
    with connect(path, readonly=True) as conn:
        conn.execute('BEGIN')
        state = json.loads(conn.execute('SELECT body FROM account WHERE id=1').fetchone()[0])
        trades = [dict(json.loads(body), id=ident) for ident, body in conn.execute('SELECT id,body FROM trades ORDER BY id DESC LIMIT ?', (trade_limit,))]
        events = [json.loads(row[0]) for row in conn.execute('SELECT body FROM events ORDER BY timestamp DESC LIMIT ?', (event_limit,))][::-1]
        has_totals = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ledger_totals'").fetchone()
        count, pnl = conn.execute('SELECT trades,pnl FROM ledger_totals WHERE id=1').fetchone() if has_totals else conn.execute("SELECT COUNT(*),COALESCE(SUM(json_extract(body,'$.net_pnl_rs')),0) FROM trades").fetchone()
    position = state['position']
    unrealised = position['mark']['gross_rs'] - position['mark']['exit_charges_rs'] if position else 0
    return {'available': True, **{k: v for k, v in state.items() if k != 'fingerprint'},
            'initial_capital_rs': state['initial_capital'], 'realised_equity_rs': state['equity'],
            'marked_equity_rs': state['equity'] + unrealised, 'closed_trades': count,
            'open_trades': int(position is not None), 'net_closed_pnl_rs': pnl,
            'trades': trades, 'decisions': events, 'notes': [], 'last_processed': state['last_timestamp'],
            'start_date': state['started_at'], 'orders_submitted': False,
            'history_window': {'trade_limit': trade_limit, 'event_limit': event_limit,
                               'has_older_trades': count > len(trades), 'pagination': '/api/v1/history/trades'}}


def history(path, kind, limit=50, cursor=None):
    if kind not in ('trades', 'events') or not 1 <= limit <= 200:
        raise ValueError('Use trades/events and a limit between 1 and 200')
    column = 'id' if kind == 'trades' else 'timestamp'
    if cursor is not None:
        if kind == 'trades':
            cursor = int(cursor)
            if cursor < 1:
                raise ValueError('Invalid trade cursor')
        elif len(cursor) > 40:
            raise ValueError('Invalid event cursor')
    clause = f'WHERE {column} < ?' if cursor is not None else ''
    params = (cursor, limit + 1) if cursor is not None else (limit + 1,)
    with connect(path, readonly=True) as conn:
        rows = conn.execute(f'SELECT {column},body FROM {kind} {clause} ORDER BY {column} DESC LIMIT ?', params).fetchall()
    items = [dict(json.loads(body), **{column: key}) for key, body in rows[:limit]]
    return {'items': items, 'next_cursor': str(rows[limit - 1][0]) if len(rows) > limit else None,
            'limit': limit, 'mode': 'paper'}
