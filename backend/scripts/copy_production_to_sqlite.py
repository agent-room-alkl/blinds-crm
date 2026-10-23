"""Copy the production PostgreSQL schema into a local SQLite file for testing.

Read-only against production (SET TRANSACTION READ ONLY, then rollback). The
SQLite file gets the app's own table definitions, then every row of every app
table except login sessions. Connection settings come from DATABASE_URL and
VERA_DB_SCHEMA and are never printed.

    python scripts/copy_production_to_sqlite.py --target vera-prod-copy.db
"""
import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
SKIPPED = {'sessions', 'portal_sessions'}


def create_app_schema(target: Path):
    """Let the app build its current schema in a fresh SQLite file, then empty it."""
    if target.exists():
        raise SystemExit(f'{target} already exists; choose a new file')
    env = {**os.environ, 'VERA_DB_BACKEND': 'sqlite', 'VERA_DB': str(target), 'VERA_STORAGE_BACKEND': 'local'}
    env.pop('DATABASE_URL', None)
    subprocess.run([sys.executable, '-c', 'import service'], cwd=BACKEND, env=env, check=True)
    con = sqlite3.connect(target)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    con.execute('PRAGMA foreign_keys=OFF')
    for table in tables:
        con.execute(f'DELETE FROM "{table}"')
    con.commit()
    return con, tables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, required=True)
    args = parser.parse_args()
    from scripts.migrate_review_catalog import database_url
    import psycopg

    url, schema = database_url(), os.getenv('VERA_DB_SCHEMA', 'vera')
    if not url:
        raise SystemExit('DATABASE_URL is not set')
    target = args.target if args.target.is_absolute() else BACKEND / args.target
    local, tables = create_app_schema(target)
    with psycopg.connect(url, autocommit=False) as remote:
        remote.execute('SET TRANSACTION READ ONLY')
        remote_tables = {r[0] for r in remote.execute(
            'SELECT table_name FROM information_schema.tables WHERE table_schema=%s', (schema,))}
        for table in sorted(tables):
            if table in SKIPPED:
                print(f'{table}: skipped (login sessions are not copied)')
                continue
            if table not in remote_tables:
                print(f'{table}: not in production')
                continue
            local_cols = [r[1] for r in local.execute(f'PRAGMA table_info("{table}")')]
            remote_cols = [r[0] for r in remote.execute(
                'SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s', (schema, table))]
            cols = [c for c in local_cols if c in remote_cols]
            rows = remote.execute(f'SELECT {",".join(chr(34)+c+chr(34) for c in cols)} FROM "{schema}"."{table}"').fetchall()
            local.executemany(f'INSERT INTO "{table}"({",".join(cols)}) VALUES({",".join("?" * len(cols))})', rows)
            dropped = sorted(set(remote_cols) - set(local_cols))
            print(f'{table}: {len(rows)} rows' + (f' (production-only columns not copied: {dropped})' if dropped else ''))
        extra = sorted(remote_tables - set(tables))
        if extra:
            print('production tables the app no longer defines (not copied):', extra)
        remote.rollback()
    local.commit()
    local.close()
    print('copied to', target.name)


if __name__ == '__main__':
    main()
