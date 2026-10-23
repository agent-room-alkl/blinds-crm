"""Drop the unused customers.locale and customers.notes columns.

The app never reads either column: locale was always written as 'en' and notes
was never written outside the local seed. Two phases keep old and new code
working on PostgreSQL while a deploy is in flight:

  --phase relax  (before deploying code that no longer writes locale)
                 locale gets a default and loses NOT NULL, so both versions insert.
  --phase drop   (after that code is live) drops both columns.

SQLite has no ALTER COLUMN, so on SQLite only --phase drop applies.
Default is a dry run; pass --apply to write. Uses the app's database settings.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
COLUMNS = ('locale', 'notes')


def present_columns(c, backend, schema):
    if backend == 'sqlite':
        return {r['name'] for r in c.execute('PRAGMA table_info(customers)')}
    return {r['column_name'] for r in c.execute(
        'SELECT column_name FROM information_schema.columns WHERE table_schema=? AND table_name=?', (schema, 'customers'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('relax', 'drop'), required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    import service as s
    from database import SCHEMA

    with s.db() as c:
        found = present_columns(c, s.BACKEND, SCHEMA)
        todo = [col for col in COLUMNS if col in found]
        print('backend', s.BACKEND, '| customers columns', sorted(found))
        if not todo:
            print('nothing to do')
            return
        if args.phase == 'relax':
            if s.BACKEND == 'sqlite':
                raise SystemExit('SQLite cannot relax a column; use --phase drop')
            if 'locale' not in todo:
                print('locale already dropped')
                return
            statements = ["ALTER TABLE customers ALTER COLUMN locale SET DEFAULT 'en'",
                          'ALTER TABLE customers ALTER COLUMN locale DROP NOT NULL']
        else:
            statements = [f'ALTER TABLE customers DROP COLUMN {col}' for col in todo]
        for sql in statements:
            print(('apply: ' if args.apply else 'would run: ') + sql)
            if args.apply:
                c.execute(sql)
        if not args.apply:
            print('dry run; nothing written')


if __name__ == '__main__':
    main()
