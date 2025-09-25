from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from msd.database.connection import get_conn

employees_api_bp = Blueprint("employees_api_bp", __name__, url_prefix="/api/v1")

def _row_to_emp(r):
    return {
        "id": r["id"],
        "serial_number": r["serial_number"],
        "name": r["name"],
        "department": r["department"],
        "department_id": r["department_id"],
        "job_grade": r["job_grade"],
        "vacation_balance": r["vacation_balance"],
        "emergency_vacation_balance": r.get("emergency_vacation_balance"),
        "status": r.get("status")
    }

@employees_api_bp.get("/employees")
@login_required
def list_employees():
    """
    يدعم:
      search= نص يبحث في name أو serial_number
      dept_only=1 لو المستخدم رئيس قسم (يعيد موظفي قسمه فقط)
      limit / offset اختيارية
    """
    args = request.args
    search = (args.get("search") or "").strip()
    dept_only = args.get("dept_only") == "1"
    limit = min(max(int(args.get("limit", 500)), 1), 2000)
    offset = max(int(args.get("offset", 0)), 0)

    filters = []
    params = []

    # حصر بالقسم في حالة dept_only وكان للمستخدم department_id
    if dept_only and getattr(current_user, "department_id", None):
        filters.append("(e.department_id = ? OR (e.department_id IS NULL AND e.department = (SELECT name FROM departments WHERE id=?)))")
        params.extend([current_user.department_id, current_user.department_id])

    if search:
        filters.append("(e.name LIKE ? OR e.serial_number LIKE ?)")
        s = f"%{search}%"
        params.extend([s, s])

    where = "WHERE " + " AND ".join(filters) if filters else ""
    sql = f"""
        SELECT e.id, e.serial_number, e.name, e.department, e.department_id,
               e.job_grade, e.vacation_balance,
               COALESCE(e.emergency_vacation_balance, e.emergency_balance, 0) AS emergency_vacation_balance,
               COALESCE(e.status,'active') as status
          FROM employees e
          {where}
         ORDER BY e.name ASC
         LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    with get_conn() as conn:
        conn.row_factory = lambda c, r: {d[0]: r[i] for i, d in enumerate(c.description)}
        rows = conn.execute(sql, params).fetchall()
    return jsonify([_row_to_emp(r) for r in rows])