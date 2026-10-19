"""Migration: Deactivate/reactivate roller/venetian/vertical/exterior blind products.

NOTE: As of the latest implementation, blind products from the Excel template import 
are ALREADY inactive (published=False, orderable=False) when created. This script 
exists for manual reactivation or for toggling the state.

The 18+ inactive blind products (from Excel template, various IDs):
Examples include:
- Roller blinds: Roller_Blinds_BO_VIBE, Roller_Blinds_BO_LeReve, Roller_Blinds_BO_Skye, 
  Roller_Blinds_BO_Karma, Roller_Blinds_BO_Mantra, Roller_Blinds_Sunscreen, 
  Roller_Blinds_LF_LeReve, Roller_Blinds_LF_Skye, Roller_Blinds_LF_Mantra
- Venetian blinds: Venetian_Blinds_PVC, Venetian_Blinds_Wood, Venetian_Blinds_Aluminium_25mm, 
  Venetian_Blinds_Aluminium_50mm
- Vertical blinds: Vertical_Blinds_VIBE_89mm, Vertical_Blinds_VIBE_100mm, Vertical_Blinds_Karma_89mm
- Exterior blinds: Exterior_Blinds_Mesh, Exterior_Blinds_ClearPVC

To REACTIVATE these products (undo the deactivation):
    python backend/deactivate_blind_products.py --undo

To manually DEACTIVATE (if needed):
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


def deactivate_products(undo=False):
    """Deactivate or reactivate blind products imported from Excel template."""
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
            
            # Target products with category='blinds' from template import
            # These are the roller/venetian/vertical/exterior products
            if d.get('category') != 'blinds':
                continue
            
            # Skip sample products
            if d.get('sample', False):
                continue
            
            # Check if this is a template-imported blind by having a source_code
            if not d.get('source_code'):
                continue
            
            # This is a blind product from template import
            old_published = d.get('published', True)
            old_orderable = d.get('orderable', True)
            
            d['published'] = new_status
            d['orderable'] = new_status
            
            c.execute('UPDATE products SET data=? WHERE id=?', (dump(d), pid))
            modified.append({
                'id': pid,
                'source_code': d.get('source_code', 'N/A'),
                'name_en': d.get('name_en', 'N/A'),
                'name_zh': d.get('name_zh', 'N/A'),
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
        print(f"{'ID':<6} {'Source Code':<35} {'Name (EN)':<40} {'Status'}")
        print("-" * 100)
        for p in modified:
            status = f"{p['old_published']}/{p['old_orderable']} → {p['new_published']}/{p['new_orderable']}"
            print(f"{p['id']:<6} {p['source_code']:<35} {p['name_en']:<40} {status}")
        
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
