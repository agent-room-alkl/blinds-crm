"""One-time non-destructive copy into a NEW isolated PostgreSQL schema.
Requires the user-approved DATABASE_URL/POSTGRES_URL in .env. Never logs secrets.
Refuses an existing schema. DDL and all copied rows are in one transaction.
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from service import init_db,DB_PATH,BACKEND
from database import connect,SCHEMA,AUTO_IDS
TABLES=['products','customers','contacts','inquiries','followups','quotes','quote_versions','quote_lines','orders','status_history','users']

def migrate():
    if BACKEND!='postgres':raise RuntimeError('Configure PostgreSQL before migration')
    source_path=Path(DB_PATH)
    if not source_path.is_file():raise RuntimeError('Local SQLite source is missing')
    backup_path=source_path.with_name('vera-before-postgres-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db')
    source=sqlite3.connect(source_path);backup=sqlite3.connect(backup_path)
    source.backup(backup);source.close();backup.close()
    source=sqlite3.connect(backup_path);source.row_factory=sqlite3.Row
    counts={}
    try:
        with connect(DB_PATH) as target:
            present=target.execute('SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name=?) AS present',(SCHEMA,)).fetchone()['present']
            if present:raise RuntimeError('Target schema already exists; migration refuses to overwrite it')
            init_db(connection=target,seed_admin=False)
            for table in TABLES:
                rows=source.execute(f'SELECT * FROM {table}').fetchall()
                for row in rows:
                    keys=list(row.keys());values=[row[k] for k in keys]
                    query=f"INSERT INTO {table} ({','.join(keys)}) VALUES({','.join('?' for _ in keys)})"
                    if table=='products':query+=' ON CONFLICT(id) DO UPDATE SET data=EXCLUDED.data'
                    target.execute(query,values)
                counts[table]=len(rows)
                actual=target.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n']
                if actual!=len(rows):raise RuntimeError(f'Row count mismatch: {table}')
                if table in AUTO_IDS or table=='products':
                    maximum=target.execute(f'SELECT MAX(id) AS maximum FROM {table}').fetchone()['maximum']
                    target.execute("SELECT setval(pg_get_serial_sequence(?, 'id'), ?, ?)",(SCHEMA+'.'+table,maximum or 1,bool(maximum)))
            for table,column in [('quote_versions','data'),('orders','snapshot')]:
                originals={r['id']:r[column] for r in source.execute(f'SELECT id,{column} FROM {table}')}
                copied={r['id']:r[column] for r in target.execute(f'SELECT id,{column} FROM {table}')}
                if originals!=copied:raise RuntimeError(f'Frozen data mismatch: {table}')
            if target.execute('SELECT COUNT(*) AS n FROM sessions').fetchone()['n']!=0:raise RuntimeError('Sessions must not be migrated')
        print('Migrated into new schema:',SCHEMA)
        print('Row counts:',counts)
        print('Quote/version/order snapshots identical; no old sessions copied.')
        print('Local backup:',backup_path.name)
    finally:source.close()

if __name__=='__main__':
    try:migrate()
    except Exception as exc:
        print('Migration failed:',type(exc).__name__,str(exc) if isinstance(exc,RuntimeError) else 'SQLSTATE='+str(getattr(exc,'sqlstate',None)))
        raise SystemExit(1)
