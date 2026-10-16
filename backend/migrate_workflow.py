"""Add workflow tables without recreating or reseeding existing business data."""
from service import db
from workflow_schema import migrate
from operations import migrate as migrate_operations
tables=('customers','inquiries','quotes','quote_versions','orders','products','users')
with db() as c:
    c.execute('BEGIN IMMEDIATE')
    before={t:c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tables}
    migrate(c)
    migrate_operations(c)
    after={t:c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tables}
    assert before==after,'Existing business counts changed'
print('PASS: additive workflow migration; existing business row counts unchanged')
