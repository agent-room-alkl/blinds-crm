"""Initialize only the configured VERA schema; never touches public/shared app tables."""
from service import init_db, BACKEND, SCHEMA
if __name__=='__main__':
    init_db()
    print(f'Initialized {BACKEND} schema {SCHEMA} (no secrets printed)')
