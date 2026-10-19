"""The PostgreSQL result wrapper must retain DB-API affected-row semantics."""
from types import SimpleNamespace
from database import Result

cursor = SimpleNamespace(rowcount=1)
result = Result(cursor)
assert result.rowcount == 1
cursor.rowcount = 0
assert result.rowcount == 0
cursor.rowcount = -1
assert result.rowcount == -1
print('PASS PostgreSQL Result forwards current affected-row count for update, not-found and unknown results')
