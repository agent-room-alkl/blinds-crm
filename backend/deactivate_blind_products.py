"""Migration: Deactivate/reactivate roller/venetian/vertical/exterior blind products.

NOTE: As of the latest seed, these 18 products are ALREADY inactive (published=False, 
orderable=False) when the database is initialized. This script exists only for manual 
reactivation or for databases that were initialized before this change.

The 18 inactive products (IDs 10-27):
- Roller blinds (6): IDs 10-15 (Blockout, Translucent, Sheer, Dual, Zebra, Waterproof)
- Venetian blinds (6): IDs 16-21 (Alu 25mm, Alu 50mm, Wood Grain, Bamboo, Wood, Faux Wood)
- Vertical blinds (3): IDs 22-24 (89mm, 127mm, PVC)
- Exterior blinds (3): IDs 25-27 (Aluminium, Canvas, Shade Mesh)

To REACTIVATE these products (undo the deactivation):
    python backend/deactivate_blind_products.py --undo

To manually DEACTIVATE (if needed on an old database):
    python backend/deactivate_blind_products.py

Order history for these products is preserved regardless of their active/inactive state.
"""
import argparse
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from service import db, dump


# Product IDs to deactivate (18 roller/venetian/vertical/exterior products)
# These are placeholder IDs - adjust based on actual product IDs in the database
BLIND_PRODUCT_CATEGORIES = ['roller', 'venetian', 'vertical', 'exterior']
BLIND_PRODUCT_KEYWORDS = ['Roller', 'Venetian', 'Vertical', 'Exterior', 'Roman']


def deactivate_products(undo=False):
    """Deactivate or reactivate blind products."""
    action = "Reactivating" if undo else "Deactivating"
    new_status = True if undo else False
    
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        
        # Fetch all products
        products = list(c.execute('SELECT id, data FROM products ORDER BY id'))
        
        modified = []
        for row in products:
            pid = row['id']
            d = json.loads(row['data'])
            
            # Skip sample products and shutter products
            if d.get('sample', False):
                continue
            if d.get('category') == 'shutters':
                continue
            
            # Check if this is a blind product to deactivate
            should_modify = False
            
            # Check by category
            if d.get('category') in BLIND_PRODUCT_CATEGORIES:
                should_modify = True
            
            # Check by name keywords
            name_en = d.get('name_en', '')
            name_zh = d.get('name_zh', '')
            if any(keyword in name_en or keyword in name_zh for keyword in BLIND_PRODUCT_KEYWORDS):
                should_modify = True
            
            if should_modify:
                old_published = d.get('published', True)
                old_orderable = d.get('orderable', True)
                
                d['published'] = new_status
                d['orderable'] = new_status
                
                c.execute('UPDATE products SET data=? WHERE id=?', (dump(d), pid))
                modified.append({
                    'id': pid,
                    'name_en': name_en,
                    'name_zh': name_zh,
                    'category': d.get('category', 'unknown'),
                    'old_published': old_published,
                    'old_orderable': old_orderable,
                    'new_published': new_status,
                    'new_orderable': new_status
                })
        
        if not modified:
            print(f"No blind products found to {action.lower()}")
            return
        
        print(f"\n{action} {len(modified)} blind products:")
        print(f"{'ID':<6} {'Name (EN)':<40} {'Category':<15} {'Status'}")
        print("-" * 80)
        for p in modified:
            status = f"{p['old_published']}/{p['old_orderable']} → {p['new_published']}/{p['new_orderable']}"
            print(f"{p['id']:<6} {p['name_en']:<40} {p['category']:<15} {status}")
        
        print(f"\n✓ Successfully {action.lower()} {len(modified)} products")
        print("\nTo undo this change, run:")
        print("    python backend/deactivate_blind_products.py --undo")
        
        return modified


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--undo', action='store_true', help='Reactivate previously deactivated products')
    args = parser.parse_args()
    
    if args.undo:
        print("Reverting migration: Reactivating blind products...")
    else:
        print("Running migration: Deactivating blind products...")
    
    result = deactivate_products(undo=args.undo)
    
    if result is None:
        return 0
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
