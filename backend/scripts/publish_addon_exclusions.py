"""Publish a new pricing knowledge version whose add-on exclusions match V5.

V5 marks stained colour N/A for PVC Eco, PVC and Pinewood, and double closure
N/A for PVC Eco and PVC. Knowledge version 52abc3 only excluded PVC Eco and PVC
from stained colour. This copies the active published version, replaces only the
add-on exclusion lists (and the matching fact excerpts), and publishes it as a
new version with the same hashing and pointer update as the in-app publish.
Orders and their price snapshots are never touched.

Default is a dry run. --apply writes. Uses the app's database settings
(VERA_DB_BACKEND, DATABASE_URL, VERA_DB_SCHEMA) and never prints them.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXCLUDE = {
    'stained_colour': ['Shutters_PVC', 'Shutters_PVC_Eco', 'Shutters_Pinewood'],
    'double_closure': ['Shutters_PVC', 'Shutters_PVC_Eco'],
}
EXCERPTS = {
    'fact:stained-colour': 'Stained Colour (per sqm): +$20; N/A for PVC Eco, PVC and Pinewood',
    'fact:double-closure': 'Double Closure (per sqm): +$35; N/A for PVC Eco and PVC',
}
ACTOR = 'maintenance:v5-addon-exclusions'


def corrected(manifest):
    """Return (new manifest, list of changes) without mutating the input."""
    value = json.loads(json.dumps(manifest))
    changes = []
    for addon in value.get('addons') or []:
        wanted = EXCLUDE.get(addon.get('key'))
        if wanted is not None and sorted(addon.get('exclude') or []) != sorted(wanted):
            changes.append(f"{addon['key']}: exclude {addon.get('exclude') or []} -> {wanted}")
            addon['exclude'] = list(wanted)
    for fact in value.get('knowledge_facts') or []:
        excerpt = EXCERPTS.get(fact.get('id'))
        if excerpt and fact.get('source_excerpt') != excerpt:
            changes.append(f"{fact['id']}: excerpt updated")
            fact['source_excerpt'] = excerpt
    return value, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    import service as s  # Postgres is not initialised on import unless VERA_AUTO_INIT=1.

    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        pointer_row = c.execute("SELECT data FROM operations_records WHERE id='template-current'").fetchone()
        if not pointer_row:
            raise SystemExit('No active pricing version')
        pointer = json.loads(pointer_row['data'])
        row = c.execute('SELECT data FROM operations_records WHERE id=?', (pointer['template_id'],)).fetchone()
        current = json.loads(row['data'])
        if not current.get('knowledge_published'):
            raise SystemExit('The active pricing version was not published through the knowledge base')
        manifest, changes = corrected(current)
        print('backend', s.BACKEND, '| active version', current['version'][:12])
        if not changes:
            print('already correct; nothing to publish')
            return
        for change in changes:
            print(' -', change)
        manifest['supersedes_version'] = current['version']
        manifest['source'] = current.get('source', '') + ' (V5 add-on availability corrected)'
        body = {k: v for k, v in manifest.items() if k not in ('id', 'version', 'actor', 'imported_at')}
        manifest['version'] = hashlib.sha256(s.dump(body).encode()).hexdigest()
        manifest.update(id='template:' + manifest['version'], imported_at=s.now(), actor=ACTOR, knowledge_published=True)
        print('new version', manifest['version'][:12])
        if not args.apply:
            print('dry run; nothing written')
            return
        if c.execute('SELECT 1 FROM operations_records WHERE id=?', (manifest['id'],)).fetchone():
            raise SystemExit('This exact version already exists')
        upsert = ('INSERT INTO operations_records(id,kind,customer_id,data) VALUES(?,?,?,?) '
                  'ON CONFLICT(id) DO UPDATE SET data=excluded.data')
        c.execute(upsert, (manifest['id'], 'template', None, s.dump(manifest)))
        c.execute(upsert, ('template-current', 'template_pointer', None,
                           s.dump({'id': 'template-current', 'template_id': manifest['id'], 'activated_at': s.now(), 'actor': ACTOR})))
        codes = {rule.get('source_code') for rule in manifest.get('products') or []}
        for pid, data in [(r['id'], json.loads(r['data'])) for r in c.execute('SELECT id,data FROM products').fetchall()]:
            if data.get('source_code') in codes and data.get('rule_version'):
                data['rule_version'] = manifest['version']
                c.execute('UPDATE products SET data=? WHERE id=?', (s.dump(data), pid))
        print('published; orders and their price snapshots were not touched')


if __name__ == '__main__':
    main()
