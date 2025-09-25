"""
Unified auth loader stub.

Important:
- The application registers the ONLY flask-login user_loader inside msd/__init__.py
  and loads users from the 'users' table.
- This module must NOT register another user_loader to avoid conflicts.
"""

from msd.database.connection import get_conn
from msd.auth.models import User

def get_user_by_id(user_id: str):
    """
    Helper used elsewhere if needed. NOT auto-registered with flask-login.
    """
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT id, username, role, department_id, telegram_chat_id "
                "FROM users WHERE id=?",
                (user_id,)
            ).fetchone()
        if row:
            return User(
                id=row[0],
                username=row[1],
                role=row[2],
                department_id=row[3],
                telegram_chat_id=row[4]
            )
    except Exception:
        pass
    return None