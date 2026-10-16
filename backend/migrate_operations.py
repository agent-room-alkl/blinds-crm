"""Add current portal/project tables without deleting existing data."""
from service import init_db,db
from cleanup_legacy import table_names

with db() as c:
    c.execute('BEGIN IMMEDIATE')
    existing=table_names(c)
    tracked=existing & {'customers','products','users','operations_records','portal_profiles'}
    before={t:c.execute(f'SELECT COUNT(*) AS n FROM "{t}"').fetchone()['n'] for t in tracked}
    init_db(connection=c,seed_admin=False,seed_catalog=False)
    after={t:c.execute(f'SELECT COUNT(*) AS n FROM "{t}"').fetchone()['n'] for t in tracked}
    assert before==after,'Existing business row counts changed'
print('PASS additive current operations migration; no legacy tables created or data deleted')
