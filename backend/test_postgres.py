"""Run the actual workflow/catalogue suites in disposable, uniquely named schemas.
Never runs the test suites against the application schema or public.
"""
import os,re,secrets,subprocess,sys
from pathlib import Path
from database import connect,BACKEND
from psycopg import sql
if BACKEND!='postgres':raise SystemExit('PostgreSQL configuration required')
allowed=['test_api.py','test_products.py','test_concurrent_postgres.py','test_storage_api_live.py','test_manual_email.py','test_workflow.py']
suites=sys.argv[1:] or allowed
assert all(s in allowed for s in suites)
for suite in suites:
    schema='vera_test_'+secrets.token_hex(6)
    assert re.fullmatch(r'vera_test_[a-f0-9]{12}',schema)
    with connect('unused.db') as c:
        assert not c.execute('SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name=?) AS present',(schema,)).fetchone()['present']
    env=dict(os.environ);env.update(VERA_TEST_SCHEMA=schema,VERA_DB_SCHEMA=schema,VERA_DB_BACKEND='postgres',VERA_AUTO_INIT='0',VERA_DEMO_PASSWORD=secrets.token_urlsafe(20),VERA_STORAGE_BACKEND='local')
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).with_name(suite))],env=env,capture_output=True,text=True)
        print(suite, 'exit',result.returncode)
        # Test outputs contain assertions/results, never connection credentials.
        if result.stdout:print(result.stdout.strip())
        if result.returncode:
            print(result.stderr[-2500:]);raise SystemExit(result.returncode)
    finally:
        with connect('unused.db') as c:
            c.connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
        print('Disposable test schema removed:',schema)
print('PASS: real PostgreSQL workflow + catalogue/image/gallery suites; application/public schemas unchanged by tests')
