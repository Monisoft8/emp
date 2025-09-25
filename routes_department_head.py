from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from msd.database.connection import get_conn
from msd.vacations import service as vac_service

dept_head_api = Blueprint("dept_head_api", __name__)

def _require_role():
    if current_user.role != "department_head":
        return False
    return True

@dept_head_api.get("/department-head/dashboard")
@login_required
def dh_dashboard():
    if not _require_role():
        return jsonify({"error":"forbidden"}), 403
    with get_conn() as conn:
        cur = conn.cursor()
        # عدد الطلبات المعلقة لديه
        cur.execute("""
            SELECT COUNT(*) FROM vacation_requests vr
            JOIN employees e ON e.id=vr.employee_id
           WHERE vr.status='pending_dept' AND e.department_id=?""", (current_user.department_id,))
        pending = cur.fetchone()[0]

        # عدد الموظفين في قسمه
        cur.execute("SELECT COUNT(*) FROM employees WHERE department_id=?", (current_user.department_id,))
        emp_count = cur.fetchone()[0]

        return jsonify({
            "pending_requests": pending,
            "employees": emp_count
        })

@dept_head_api.get("/department-head/employees")
@login_required
def dh_employees():
    if not _require_role():
        return jsonify({"error":"forbidden"}), 403
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT id, name FROM employees WHERE department_id=? ORDER BY name""",
                    (current_user.department_id,))
        rows = [dict(id=r[0], name=r[1]) for r in cur.fetchall()]
    return jsonify(rows)

@dept_head_api.get("/department-head/requests")
@login_required
def dh_requests():
    if not _require_role():
        return jsonify({"error":"forbidden"}), 403
    status = request.args.get("status","pending_dept")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
          SELECT vr.id, vr.employee_id, vr.type_code, vr.start_date, vr.end_date,
                 vr.requested_days, vr.status, vr.notes
            FROM vacation_requests vr
            JOIN employees e ON e.id=vr.employee_id
           WHERE e.department_id=? AND vr.status=?
           ORDER BY vr.id DESC
        """,(current_user.department_id, status))
        rows = [dict(r) for r in cur.fetchall()]
    return jsonify(rows)

@dept_head_api.post("/department-head/requests/<int:rid>/approve")
@login_required
def dh_approve(rid):
    if not _require_role(): return jsonify({"error":"forbidden"}), 403
    try:
        vac_service.approve(rid, current_user.role, current_user.id)
        return jsonify({"message":"advanced"})
    except Exception as e:
        return jsonify({"error":str(e)}), 400

@dept_head_api.post("/department-head/requests/<int:rid>/reject")
@login_required
def dh_reject(rid):
    if not _require_role(): return jsonify({"error":"forbidden"}), 403
    data = request.get_json(silent=True) or {}
    reason = data.get("reason")
    try:
        vac_service.reject(rid, current_user.role, current_user.id, reason=reason)
        return jsonify({"message":"rejected"})
    except Exception as e:
        return jsonify({"error":str(e)}), 400

@dept_head_api.post("/department-head/requests/<int:rid>/cancel")
@login_required
def dh_cancel(rid):
    if not _require_role(): return jsonify({"error":"forbidden"}), 403
    data = request.get_json(silent=True) or {}
    note = data.get("note")
    try:
        vac_service.cancel(rid, current_user.role, current_user.id, note=note)
        return jsonify({"message":"cancelled"})
    except Exception as e:
        return jsonify({"error":str(e)}), 400