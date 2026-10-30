"""Running invoice numbers: the backfill numbers legacy invoices oldest first after any already numbered,
keeps the old name, and the reference is the order number. In-memory SQLite only.
"""
import json
import os
import sqlite3
import tempfile
from pathlib import Path

os.environ['VERA_DB_BACKEND'] = 'sqlite'
os.environ['VERA_DB'] = str(Path(tempfile.mkdtemp()) / 'test.db')

import invoice_mail
from operations import backfill_invoice_numbers

c = sqlite3.connect(':memory:')
c.row_factory = sqlite3.Row
c.execute('CREATE TABLE operations_records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,customer_id INTEGER,data TEXT NOT NULL)')


def put(kind, d):
    c.execute('INSERT INTO operations_records(id,kind,customer_id,data) VALUES(?,?,?,?)', (d['id'], kind, 1, json.dumps(d)))


put('project', {'id': 'p1', 'order_number': 'ABC-Sterling House'})
put('project', {'id': 'p2', 'order_number': 'R26103001A'})
put('invoice', {'id': 'balance:x', 'kind': 'balance', 'order_ids': ['p2', 'p1'], 'created_at': '2026-10-20T00:00:00'})
put('invoice', {'id': 'deposit:p1', 'kind': 'deposit', 'order_ids': ['p1'], 'created_at': '2026-10-10T00:00:00'})
put('invoice', {'id': 'manual:y', 'kind': 'manual', 'order_ids': [], 'fixed_number': 'ABC-M001', 'created_at': '2026-10-15T00:00:00'})
put('invoice', {'id': 'manual:new', 'kind': 'manual', 'order_ids': [], 'sequence': 1, 'fixed_number': 'INV-00001', 'created_at': '2026-10-30T00:00:00'})

assert backfill_invoice_numbers(c) == [('ABC-Sterling House-D', 'INV-00002'), ('ABC-M001', 'INV-00003'), ('ABC-Sterling House-B', 'INV-00004')]
assert backfill_invoice_numbers(c) == []  # repeatable
saved = {r['id']: json.loads(r['data']) for r in c.execute("SELECT id,data FROM operations_records WHERE kind='invoice'")}
numbers = {'p1': 'ABC-Sterling House', 'p2': 'R26103001A'}
assert invoice_mail.invoice_number(saved['deposit:p1'], numbers) == 'INV-00002' and saved['deposit:p1']['legacy_number'] == 'ABC-Sterling House-D'
assert invoice_mail.invoice_reference(saved['balance:x'], numbers) == 'R26103001A, ABC-Sterling House'
assert invoice_mail.invoice_reference(saved['manual:y'], numbers) == ''
print('PASS invoice numbers: running INV-00001 sequence, legacy backfill oldest first and repeatable, order number as reference')
