from msd.database.connection import get_conn

SCHEMA_SQL = """
-- مثال، عدّل حسب المخطط الفعلي
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user'
);
"""

def init_database():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executescript(SCHEMA_SQL)
        conn.commit()