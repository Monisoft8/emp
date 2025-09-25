from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from msd.database.connection import get_conn

departments_api_bp = Blueprint("departments_api_bp", __name__, url_prefix="/api/v1")

def as_row_dict(cur, row):
    return {d[0]: row[i] for i, d in enumerate(cur.description)}

@departments_api_bp.get("/departments")
@login_required
def list_departments():
    with get_conn() as conn:
        conn.row_factory = as_row_dict
        rows = conn.execute("""
            SELECT d.id, d.name,
                   d.department_head_employee_id,
                   e.name AS head_employee_name,
                   d.head_password
              FROM departments d
              LEFT JOIN employees e ON e.id=d.department_head_employee_id
              ORDER BY d.name
        """).fetchall()
    return jsonify(rows)

@departments_api_bp.post("/departments/<int:dept_id>/head")
@login_required
def set_department_head(dept_id):
    # السماح فقط للمدير أو الأدمن
    if getattr(current_user, "role", "") not in ("manager", "admin"):
        return jsonify(error="غير مسموح"), 403
    data = request.get_json(force=True)
    employee_id = data.get("employee_id")
    head_password = (data.get("head_password") or "").strip() or None
    if not employee_id:
        return jsonify(error="employee_id مطلوب"), 400
    with get_conn() as conn:
        # تحقق أن الموظف في نفس القسم (اختياري)
        emp = conn.execute("SELECT department_id, department FROM employees WHERE id=?", (employee_id,)).fetchone()
        if not emp:
            return jsonify(error="موظف غير موجود"), 404
        # تحديث
        conn.execute("""
            UPDATE departments
               SET department_head_employee_id=?, head_password=COALESCE(?, head_password)
             WHERE id=?
        """, (employee_id, head_password, dept_id))
        conn.commit()
    return jsonify(success=True)