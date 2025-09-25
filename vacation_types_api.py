from flask import Blueprint, jsonify
from flask_login import login_required
from msd.database.connection import get_conn

vacation_types_api_bp = Blueprint("vacation_types_api_bp", __name__, url_prefix="/api/v1")

SEED_TYPES = [
    ("annual", "سنوية", None, 90, 0, 1, 0),
    ("emergency", "طارئة", None, 3, 0, 0, 1),
    ("death_spouse", "وفاة الزوج", 130, 130, 1, 0, 0),  # جديد
    ("death1", "وفاة درجة أولى", 7, 7, 1, 0, 0),
    ("death2", "وفاة درجة ثانية", 3, 3, 1, 0, 0),
    ("hajj", "حج", 20, 20, 0, 0, 0),
    ("marriage", "زواج", 14, 14, 0, 0, 0),
    ("birth_single", "وضع (عادي)", 98, 98, 0, 0, 0),
    ("birth_twins", "وضع (توأم)", 112, 112, 0, 0, 0),
    ("sick", "مرضية", None, 30, 0, 0, 0),
]

def seed_if_empty(conn):
    cur = conn.execute("SELECT COUNT(*) FROM vacation_types")
    if cur.fetchone()[0] == 0:
        conn.executemany("""
          INSERT INTO vacation_types(code,name_ar,fixed_duration,max_per_request,
                                     requires_relation,affects_annual_balance,affects_emergency_balance)
          VALUES (?,?,?,?,?,?,?)
        """, SEED_TYPES)
        conn.commit()

@vacation_types_api_bp.get("/vacation-types")
@login_required
def list_vacation_types():
    with get_conn() as conn:
        seed_if_empty(conn)
        rows = conn.execute("""
          SELECT code,name_ar,fixed_duration,max_per_request,
                 requires_relation,affects_annual_balance,affects_emergency_balance
            FROM vacation_types
            ORDER BY name_ar
        """).fetchall()
    out=[]
    for r in rows:
        out.append({
            "code": r[0],
            "name_ar": r[1],
            "fixed_duration": r[2],
            "max_per_request": r[3],
            "requires_relation": bool(r[4]),
            "affects_annual_balance": bool(r[5]),
            "affects_emergency_balance": bool(r[6])
        })
    return jsonify(out)