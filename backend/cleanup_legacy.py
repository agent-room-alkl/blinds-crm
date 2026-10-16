"""Explicit, transactional removal of the retired Support History data model.

Default is a row-count dry run. --apply requires a private archive path.
Never called by app startup. No CASCADE and no dynamically discovered drop targets.
"""
import argparse
import hashlib
import json
import os
from datetime import datetime,timezone
from pathlib import Path
from database import BACKEND,SCHEMA,connect

LEGACY_TABLES=('project_tasks','communications','quote_drafts','integration_state','status_history',
               'orders','quote_lines','quote_versions','quotes','followups','inquiries','contacts')
KEEP_TABLES=('products','customers','users','sessions','portal_profiles','portal_sessions','operations_records')


def table_names(c):
    if BACKEND=='sqlite':
        return {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {r['name'] for r in c.execute('SELECT table_name AS name FROM information_schema.tables WHERE table_schema=?',(SCHEMA,))}


def plan(c):
    present=table_names(c)
    if not {'portal_profiles','operations_records'}<=present:
        raise RuntimeError('Run migrate_operations.py before cleaning retired data')
    counts={t:c.execute(f'SELECT COUNT(*) AS n FROM "{t}"').fetchone()['n'] for t in LEGACY_TABLES if t in present}
    orphan_query='SELECT * FROM customers WHERE id NOT IN (SELECT customer_id FROM portal_profiles) AND id NOT IN (SELECT customer_id FROM operations_records WHERE customer_id IS NOT NULL)'
    orphans=[dict(r) for r in c.execute(orphan_query)]
    return counts,orphans


def cleanup(c,apply=False,backup_path=None):
    c.execute('BEGIN IMMEDIATE')
    counts,orphans=plan(c)
    summary={'legacy_tables':counts,'unlinked_legacy_customers':len(orphans),'applied':False}
    if not apply:
        return summary
    if backup_path is None:
        raise RuntimeError('An explicit private archive path is required')
    retained={t:[dict(r) for r in c.execute(f'SELECT * FROM "{t}"')] for t in KEEP_TABLES if t!='customers'}
    keep_customer_ids={r['customer_id'] for r in retained['portal_profiles']} | {r['customer_id'] for r in retained['operations_records'] if r['customer_id'] is not None}
    retained_customers=[dict(r) for r in c.execute('SELECT * FROM customers') if r['id'] in keep_customer_ids]
    archive={'created_at':datetime.now(timezone.utc).isoformat(),'schema':SCHEMA,'backend':BACKEND,
             'tables':{t:[dict(r) for r in c.execute(f'SELECT * FROM "{t}"')] for t in counts},'unlinked_customers':orphans}
    if BACKEND=='sqlite':
        archive['schema_sql']={r['name']:r['sql'] for r in c.execute("SELECT name,sql FROM sqlite_master WHERE type='table'") if r['name'] in counts}
    path=Path(backup_path).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(archive,ensure_ascii=False,indent=2,default=str)
    with path.open('x',encoding='utf-8') as f:
        f.write(payload)
    for table in counts:
        c.execute(f'DROP TABLE "{table}"')
    c.execute('DELETE FROM customers WHERE id NOT IN (SELECT customer_id FROM portal_profiles) AND id NOT IN (SELECT customer_id FROM operations_records WHERE customer_id IS NOT NULL)')
    for table,rows in retained.items():
        canonical=lambda items:sorted(json.dumps(r,sort_keys=True,default=str) for r in items)
        if canonical(rows)!=canonical([dict(r) for r in c.execute(f'SELECT * FROM "{table}"')]):
            raise RuntimeError('Current business data changed; rolling back: '+table)
    if canonical(retained_customers)!=canonical([dict(r) for r in c.execute('SELECT * FROM customers')]):
        raise RuntimeError('Current customer data changed; rolling back')
    if set(counts)&table_names(c):
        raise RuntimeError('Legacy tables remain; rolling back')
    return {**summary,'applied':True,'archive':str(path),'archive_sha256':hashlib.sha256(payload.encode()).hexdigest()}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--backup',type=Path,help='Private new JSON archive; never place it in Git')
    args=parser.parse_args()
    db_path=os.environ.get('VERA_DB',str(Path(__file__).with_name('vera.db')))
    if BACKEND=='sqlite' and not Path(db_path).is_file():
        raise SystemExit('Configured SQLite database does not exist')
    if args.apply and not args.backup:
        parser.error('--apply requires --backup <private-new-file.json>')
    with connect(db_path) as c:
        result=cleanup(c,apply=args.apply,backup_path=args.backup)
    print(json.dumps(result,ensure_ascii=False,indent=2))
