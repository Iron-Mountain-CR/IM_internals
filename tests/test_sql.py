"""
Tests for im_internals.sql.SqlDatabase.

Thin coverage: only a single query()/fetchall() round-trip against a monkeypatched pyodbc.connect.
Does not test commit, rollback, call_sql_procedure, column_names, or the sql_retry decorator
(imported but unused), per the trailing comment.
"""
import pytest
from im_internals.sql import SqlDatabase, sql_retry

# NOTE: DummyConn/DummyCursor below are dead code - the patch_pyodbc fixture defines its own
# separate inline Dummy/DummyCursor pair instead of using this class. Also, DummyConn.cursor is
# both an instance attribute (in __init__) and a method of the same name, which would collide if
# this class were ever actually instantiated.
class DummyCursor:
    def execute(self, *args, **kwargs): pass
    def fetchall(self): return [(1,)]

class DummyConn:
    def __init__(self): self.cursor = DummyCursor()
    def cursor(self): return self.cursor
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass

@pytest.fixture(autouse=True)
def patch_pyodbc(monkeypatch):
    import pyodbc
    class Dummy:
        def __init__(*args, **kwargs): pass
        def cursor(self): return DummyCursor()
        def close(self): pass
    monkeypatch.setattr(pyodbc, "connect", lambda *a, **kw: Dummy())
    return

def test_query_and_fetch(tmp_path):
    db = SqlDatabase("srv", "db", "u", "p", 1433, "DRIVER")
    res = db.query("SELECT 1")
    assert res == [(1,)]

# ... tests for commit, rollback, call_sql_procedure, column_names
