from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from msd.database.connection import get_conn

dept_head_api = Blueprint("dept_head_api", __name__)

@dept_head_api.get("/dept/vacations")
@login_required
def dept_vacations():
    if current_user.role != "department_head":
        return jsonify({"error":"غير مصرح"}), 403
    status = request.args.get("status")
    # خريطة الحالات المتاحة لرئيس القسم (يمكنك تعديل القائمة)
    allowed_statuses = {
        "pending": ("pending_dept", "pending_manager"),  # لو أردت استخدام كلمة pending عامة
        "pending_dept": ("pending_dept",),
        "pending_manager": ("pending_manager",),
        "approved": ("approved",),
        "rejected_dept": ("rejected_dept",),
        "rejected_manager": ("rejected_manager",),
        "cancelled": ("cancelled",)
    }
    status_filter = None
    params = [current_user.department_id]
    if status and status in allowed_statuses:
        placeholders = ",".join("?"*len(allowed_statuses[status]))
        status_filter = f" AND vr.status IN ({placeholders})"
        params.extend(list(allowed_statuses[status]))
    sql = f"""
        SELECT vr.id, vr.employee_id, e.name AS employee_name,
               vr.type_code, vr.start_date, vr.end_date, vr.requested_days,
               vr.status, vr.rejection_reason, vr.notes, vr.created_at
          FROM vacation_requests vr
          JOIN employees e ON e.id=vr.employee_id
         WHERE e.department_id=? {status_filter or ""}
         ORDER BY vr.id DESC
         LIMIT 500
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    return jsonify(rows)