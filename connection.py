import sqlite3
from flask import current_app, g
from contextlib import contextmanager
import os

def _get_db_path():
    return current_app.config.get("DATABASE_PATH", "employees.db")

def _init_conn(conn: sqlite3.Connection):
    conn.row_factory = sqlite3.Row
    # إعدادات تقلل التعارض
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def get_db():
    if 'db_conn' not in g:
        path = _get_db_path()
        need_dir = os.path.dirname(os.path.abspath(path))
        os.makedirs(need_dir, exist_ok=True)
        conn = sqlite3.connect(path, timeout=10)
        _init_conn(conn)
        g.db_conn = conn
    return g.db_conn

@contextmanager
def get_conn():
    conn = get_db()
    try:
        yield conn
    finally:
        # لا نغلق هنا، الإغلاق في teardown
        pass

def close_db(e=None):
    conn = g.pop('db_conn', None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass