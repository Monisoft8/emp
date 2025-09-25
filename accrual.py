from datetime import date
from msd.database.connection import get_conn
import math

def run_monthly_accrual():
    today = date.today()
    y, m = today.year, today.month
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS accrual_runs(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              year INTEGER,
              month INTEGER,
              run_at TEXT DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(year, month)
            )
        """)
        try:
            cur.execute("INSERT INTO accrual_runs(year, month) VALUES (?, ?)", (y, m))
        except Exception:
            # تم التراكم لهذا الشهر
            return
        # حساب التراكم
        cur.execute("SELECT id, hiring_date FROM employees")
        rows = cur.fetchall()
        for r in rows:
            emp_id, hiring = r["hiring_date"], 
            # hiring_date محفوظ كنص
            try:
                cur.execute("SELECT hiring_date FROM employees WHERE id=?", (r["id"],))
                hd = cur.fetchone()["hiring_date"]
                if not hd:
                    continue
                yy, mm, dd = map(int, hd.split("-"))
                years = y - yy - (1 if m < mm else 0)
                if years < 0:
                    continue
                annual_cap = 45 if years >= 20 else 30
                monthly = annual_cap / 12.0
                cur.execute("UPDATE employees SET annual_balance = annual_balance + ? WHERE id=?",
                            (monthly, r["id"]))
            except Exception:
                continue
        conn.commit()