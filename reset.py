from datetime import date
from msd.database.connection import get_conn

def reset_emergency_if_needed(force=False):
    today = date.today()
    if not force and not (today.month == 1 and today.day == 1):
        return
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE employees SET emergency_balance = 12")
        conn.commit()