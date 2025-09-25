from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from msd.vacations import service as vac_service
from msd.database.connection import get_conn

vacations_api = Blueprint("vacations_api", __name__)

# ---------- أنواع ----------
@vacations_api.get("/vacation-types")
@login_required
def vacation_types():
    return jsonify(vac_service.list_vacation_types())

# ---------- قائمة الموظفين (تدعم dept_only) ----------
@vacations_api.get("/employees")
@login_required
def employees_list():
    """
    يدعم:
      ?search=...      بحث بالاسم أو ID
      ?dept_only=1     إرجاع موظفي قسم المستخدم (إذا كان رئيس قسم)
    """
    term = request.args.get("search", "").strip()
    dept_only = request.args.get("dept_only")
    with get_conn() as conn:
        cur = conn.cursor()
        base_where = ["status='active'"]
        params = []
        if dept_only and current_user.role == "department_head":
            base_where.append("department_id=?")
            params.append(current_user.department_id)
        if term:
            like = f"%{term}%"
            base_where.append("(name LIKE ? OR CAST(id AS TEXT)=?)")
            params.extend([like, term])
        where_sql = " WHERE " + " AND ".join(base_where)
        sql = f"""
            SELECT id, name FROM employees
            {where_sql}
            ORDER BY name LIMIT 200
        """
        cur.execute(sql, params)
        rows = cur.fetchall()
        return jsonify([{"id": r["id"], "name": r["name"]} for r in rows])

# ---------- إنشاء ----------
@vacations_api.post("/vacations")
@login_required
def create_vacation():
    data = request.get_json(force=True)
    try:
        rid = vac_service.create_request(
            employee_id=data["employee_id"],
            type_code=data["type_code"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            relation=data.get("relation"),
            notes=data.get("notes", "")
        )
        return jsonify({"id": rid, "message": "created"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------- قائمة مترقمة عامة ----------
@vacations_api.get("/vacations")
@login_required
def list_vacations():
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)
        status = request.args.get("status") or None
        employee_id = request.args.get("employee_id", type=int)
        type_code = request.args.get("type") or None
        q = request.args.get("q") or None
        data = vac_service.list_requests_paginated(
            page=page, limit=limit, status=status,
            employee_id=employee_id, type_code=type_code, q=q
        )
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------- تعديل ----------
@vacations_api.put("/vacations/<int:rid>")
@login_required
def update_vacation(rid):
    data = request.get_json(force=True, silent=True) or {}
    try:
        updated = vac_service.update_request(
            request_id=rid,
            actor_role=current_user.role,
            actor_user_id=current_user.id,
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            type_code=data.get("type_code"),
            notes=data.get("notes")
        )
        return jsonify({"message": "updated", "request": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------- حذف ----------
@vacations_api.delete("/vacations/<int:rid>")
@login_required
def delete_vacation(rid):
    try:
        vac_service.hard_delete_request(rid, current_user.role)
        return jsonify({"message": "deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------- تاريخ ----------
@vacations_api.get("/vacations/<int:rid>/history")
@login_required
def vacation_history(rid):
    try:
        return jsonify(vac_service.get_history(rid))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------- موافقة ----------
@vacations_api.post("/vacations/<int:rid>/approve")
@login_required
def approve_vacation(rid):
    try:
        vac_service.approve(rid, current_user.role, current_user.id)
        return jsonify({"message": "approved/advanced"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------- رفض ----------
@vacations_api.post("/vacations/<int:rid>/reject")
@login_required
def reject_vacation(rid):
    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason") or request.form.get("reason")
    try:
        vac_service.reject(rid, current_user.role, current_user.id, reason=reason)
        return jsonify({"message": "rejected", "reason": reason})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------- إلغاء ----------
@vacations_api.post("/vacations/<int:rid>/cancel")
@login_required
def cancel_vacation(rid):
    payload = request.get_json(silent=True) or {}
    note = payload.get("note") or request.form.get("note")
    try:
        vac_service.cancel(rid, current_user.role, current_user.id, note=note)
        return jsonify({"message": "cancelled"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------- طلبات موظفي القسم (لرئيس القسم) ----------
@vacations_api.get("/dept/vacations")
@login_required
def dept_vacations():
    if current_user.role != "department_head":
        return jsonify({"error": "غير مصرح"}), 403
    status = request.args.get("status")
    allowed_statuses = {
        "pending_dept": ("pending_dept",),
        "pending_manager": ("pending_manager",),
        "approved": ("approved",),
        "rejected_dept": ("rejected_dept",),
        "rejected_manager": ("rejected_manager",),
        "cancelled": ("cancelled",)
    }
    params = [current_user.department_id]
    status_clause = ""
    if status and status in allowed_statuses:
        placeholders = ",".join("?" * len(allowed_statuses[status]))
        status_clause = f" AND vr.status IN ({placeholders})"
        params.extend(allowed_statuses[status])

    sql = f"""
      SELECT vr.id, vr.employee_id, e.name AS employee_name,
             vr.type_code, vr.start_date, vr.end_date, vr.requested_days,
             vr.status, vr.rejection_reason, vr.notes, vr.created_at
        FROM vacation_requests vr
        JOIN employees e ON e.id=vr.employee_id
       WHERE e.department_id=? {status_clause}
       ORDER BY vr.id DESC
       LIMIT 500
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    return jsonify(rows)