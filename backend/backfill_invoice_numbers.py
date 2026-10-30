"""Give invoices made before running numbers an INV-00001 style number, oldest first. Order numbers and invoice IDs are unchanged."""
import argparse
import json
from database import connect, BACKEND
from operations import backfill_invoice_numbers

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if BACKEND != 'postgres':
        raise SystemExit('This command requires the configured PostgreSQL database')
    with connect(None) as c:
        c.execute('BEGIN IMMEDIATE')
        if args.apply:
            for old, new in backfill_invoice_numbers(c):
                print(f'{old} -> {new}')
            print('Saved; the old names are kept as legacy_number')
        else:
            rows = c.execute("SELECT data FROM operations_records WHERE kind='invoice'").fetchall()
            pending = sum(not json.loads(row['data']).get('sequence') for row in rows)
            print(f'Dry run: {pending} invoices need running numbers; use --apply to save')
