"""Cleanup is tested only against a temporary SQLite database and archive."""
import json,os,tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND']='sqlite';os.environ['VERA_DB']=str(Path(folder)/'cleanup.db')
    from service import db
    from cleanup_legacy import cleanup,LEGACY_TABLES,table_names
    with db() as c:
        c.execute('INSERT INTO customers(id,company) VALUES(?,?)',(1,'Retained company'))
        c.execute('INSERT INTO customers(id,company) VALUES(?,?)',(2,'Old orphan'))
        c.execute('INSERT INTO portal_profiles VALUES(?,?,?,?)',(1,'retained','test-hash','{"customer_id":1}'))
        c.execute('INSERT INTO operations_records VALUES(?,?,?,?)',('project-test','project',1,'{"id":"project-test","total":"100"}'))
        for table in LEGACY_TABLES:
            c.execute(f'CREATE TABLE "{table}"(id INTEGER PRIMARY KEY,data TEXT)')
            c.execute(f'INSERT INTO "{table}" VALUES(?,?)',(1,'retired test record'))
    with db() as c:
        result=cleanup(c)
        assert not result['applied'] and len(result['legacy_tables'])==len(LEGACY_TABLES)
        assert set(LEGACY_TABLES)<=table_names(c)
    archive=Path(folder)/'private-archive.json'
    with db() as c:
        result=cleanup(c,True,archive)
        assert result['applied'] and not (set(LEGACY_TABLES)&table_names(c))
        assert [r['id'] for r in c.execute('SELECT id FROM customers')]==[1]
        assert c.execute('SELECT data FROM operations_records').fetchone()['data']=='{"id":"project-test","total":"100"}'
        assert c.execute('SELECT COUNT(*) AS n FROM users').fetchone()['n']==1
    saved=json.loads(archive.read_text(encoding='utf-8'))
    assert len(saved['tables'])==len(LEGACY_TABLES) and saved['unlinked_customers'][0]['id']==2
    with db() as c:
        assert cleanup(c)['legacy_tables']=={}
    print('PASS dry run is non-destructive; explicit cleanup archives/removes legacy tables and orphan data; current records unchanged; repeat plan empty')
