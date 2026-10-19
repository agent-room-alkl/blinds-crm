"""Assign readable order numbers without changing internal IDs or invoice references."""
import argparse
import json
from database import connect, BACKEND
from operations import backfill_order_numbers

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if BACKEND != 'postgres':
        raise SystemExit('This command requires the configured PostgreSQL database')
    with connect(None) as c:
        c.execute('BEGIN IMMEDIATE')
        rows = c.execute("SELECT data FROM operations_records WHERE kind='project'").fetchall()
        pending = sum(not json.loads(row['data']).get('order_number') for row in rows)
        if args.apply:
            changed = backfill_order_numbers(c)
            print(f'Assigned {changed} readable order numbers; internal IDs and references unchanged')
        else:
            print(f'Dry run: {pending} orders need numbers; use --apply to save')
