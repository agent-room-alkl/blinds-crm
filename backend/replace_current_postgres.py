"""Replace only the configured VERA PostgreSQL application's data from a verified SQLite source.
Dry run by default. --apply requires a private JSON archive outside version control.
The owner explicitly authorizes this one-schema replacement; other schemas are never touched.
"""
import argparse,os,sqlite3,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
os.environ['VERA_DB_BACKEND']='postgres';os.environ['VERA_AUTO_INIT']='0'
from database import connect,SCHEMA,AUTO_IDS
from psycopg import sql
CURRENT=('products','customers','users','sessions','portal_profiles','portal_sessions','operations_records','providers','provider_templates','order_providers')
LEGACY=('project_tasks','communications','quote_drafts','integration_state','status_history','orders','quote_lines','quote_versions','quotes','followups','inquiries','contacts')
COPY=('products','customers','users','portal_profiles','operations_records','providers','provider_templates','order_providers')
def digest(rows):return hashlib.sha256(json.dumps(sorted([dict(r) for r in rows],key=lambda r:json.dumps(r,sort_keys=True,default=str)),sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path);p.add_argument('--apply',action='store_true');a=p.parse_args()
 source=a.source.resolve()
 if not source.is_file():raise RuntimeError('Missing SQLite source')
 if SCHEMA!='vera':raise RuntimeError('This reviewed replacement is limited to schema vera')
 with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as src:
  src.row_factory=sqlite3.Row
  if src.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('SQLite integrity check failed')
  data={t:[dict(r) for r in src.execute('SELECT * FROM '+t)] for t in COPY}
  assert len(data['products'])==5 and len(data['customers'])==19
 with connect(str(source)) as c:
  c.execute('BEGIN IMMEDIATE')
  present={r['table_name'] for r in c.execute('SELECT table_name FROM information_schema.tables WHERE table_schema=? AND table_type=?',(SCHEMA,'BASE TABLE'))}
  if present-set(CURRENT)-set(LEGACY):raise RuntimeError('Unrecognized target tables; no replacement performed')
  cross=c.execute('SELECT tc.table_schema,tc.table_name FROM information_schema.table_constraints tc JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name=ccu.constraint_name AND tc.constraint_schema=ccu.constraint_schema WHERE tc.constraint_type=? AND ccu.table_schema=? AND tc.table_schema<>?',('FOREIGN KEY',SCHEMA,SCHEMA)).fetchall()
  if cross:raise RuntimeError('Other-schema foreign keys depend on application data')
  old={t:[dict(r) for r in c.connection.execute(sql.SQL('SELECT * FROM {}.{}').format(sql.Identifier(SCHEMA),sql.Identifier(t))).fetchall()] for t in sorted(present)}
  print('Target schema',SCHEMA,'old row counts',{t:len(rows) for t,rows in old.items()});print('Source row counts',{t:len(rows) for t,rows in data.items()})
  if not a.apply:return
  if not a.archive:raise RuntimeError('--archive is required for apply')
  archive=a.archive.resolve();private=(Path(__file__).parent/'.legacy-backups').resolve()
  if archive.parent!=private:raise RuntimeError('Archive must be inside backend/.legacy-backups')
  archive.parent.mkdir(exist_ok=True)
  archive.write_text(json.dumps({'schema':SCHEMA,'created_at':datetime.now(timezone.utc).isoformat(),'tables':old},ensure_ascii=False,default=str),encoding='utf-8') if not archive.exists() else (_ for _ in ()).throw(RuntimeError('Archive already exists'))
  # No CASCADE: a dependency outside the explicitly inventoried tables aborts the transaction.
  if present:c.connection.execute(sql.SQL('TRUNCATE {} RESTART IDENTITY').format(sql.SQL(',').join(sql.SQL('{}.{}').format(sql.Identifier(SCHEMA),sql.Identifier(t)) for t in sorted(present))))
  for table in LEGACY:
   if table in present:c.connection.execute(sql.SQL('DROP TABLE {}.{}').format(sql.Identifier(SCHEMA),sql.Identifier(table)))
  from service import init_db
  init_db(connection=c,seed_admin=False,seed_catalog=False)
  for table in COPY:
   for row in data[table]:
    columns=list(row);query=sql.SQL('INSERT INTO {}.{} ({}) VALUES ({})').format(sql.Identifier(SCHEMA),sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder() for _ in columns))
    c.connection.execute(query,[row[k] for k in columns])
   copied=c.connection.execute(sql.SQL('SELECT * FROM {}.{}').format(sql.Identifier(SCHEMA),sql.Identifier(table))).fetchall()
   if digest(copied)!=digest(data[table]):raise RuntimeError('Content mismatch: '+table)
   if table in AUTO_IDS or table=='products':
    seq=c.execute("SELECT pg_get_serial_sequence(?, 'id') AS seq",(SCHEMA+'.'+table,)).fetchone()['seq']
    if seq:
     maximum=max((r['id'] for r in data[table]),default=0);c.execute('SELECT setval(?, ?, ?)',(seq,maximum or 1,bool(maximum)))
  for table in ['sessions','portal_sessions']:
   assert c.execute('SELECT COUNT(*) AS n FROM '+table).fetchone()['n']==0
  print('All copied table row hashes match; sessions intentionally cleared; legacy tables removed; transaction ready to commit')
 print('COMMITTED',SCHEMA,'archive',archive.name)
if __name__=='__main__':
 try:main()
 except Exception as e:print('Migration failed',type(e).__name__,str(e) if isinstance(e,RuntimeError) else 'SQLSTATE='+str(getattr(e,'sqlstate',None)));raise SystemExit(1)
