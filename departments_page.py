from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from msd.database.connection import get_conn

departments_bp = Blueprint("departments_bp", __name__)

def manager_only():
    return current_user.is_authenticated and current_user.role in ("manager","admin")

@departments_bp.get("/manager/departments/list")
@login_required
def list_departments():
    if not manager_only():
        return jsonify(success=False, error="غير مسموح"), 403
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT d.id, d.name, d.department_head_id,
                   e.name AS head_name
              FROM departments d
              LEFT JOIN employees e ON e.id = d.department_head_id
             ORDER BY d.id
        """).fetchall()
    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "name": r["name"],
            "head_id": r["department_head_id"],
            "head_name": r["head_name"]
        })
    return jsonify(success=True, items=items)

@departments_bp.post("/manager/departments/add")
@login_required
def add_department():
    if not manager_only():
        return jsonify(success=False, error="غير مسموح"), 403
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(success=False, error="الاسم مطلوب"), 400
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO departments (name) VALUES (?)", (name,))
            conn.commit()
            return jsonify(success=True, id=cur.lastrowid, name=name)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 400

@departments_bp.put("/manager/departments/<int:dept_id>")
@login_required
def rename_department(dept_id):
    if not manager_only():
        return jsonify(success=False, error="غير مسموح"), 403
    data = request.get_json() or {}
    new_name = (data.get("name") or "").strip()
    if not new_name:
        return jsonify(success=False, error="الاسم مطلوب"), 400
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE departments SET name=? WHERE id=?", (new_name, dept_id))
            if cur.rowcount == 0:
                return jsonify(success=False, error="القسم غير موجود"), 404
            conn.commit()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 400

@departments_bp.put("/manager/departments/<int:dept_id>/head")
@login_required
def set_department_head(dept_id):
    """
    تعيين/إزالة رئيس قسم:
    body: { "head_id": 123 } أو head_id=null لإزالة.
    عند التعيين:
      - ترقية الموظف إلى role=department_head (إن لم يكن)
      - إزالة الدور عن أي موظف آخر في أقسام لا يرأسها (لا نلمس المديرين)
    """
    if not manager_only():
        return jsonify(success=False, error="غير مسموح"), 403
    data = request.get_json() or {}
    head_id = data.get("head_id")
    with get_conn() as conn:
        cur = conn.cursor()
        # تحقق القسم موجود
        row = cur.execute("SELECT id FROM departments WHERE id=?", (dept_id,)).fetchone()
        if not row:
            return jsonify(success=False, error="القسم غير موجود"), 404

        if head_id:
            # تحقق الموظف موجود
            emp = cur.execute("SELECT id, role FROM employees WHERE id=?", (head_id,)).fetchone()
            if not emp:
                return jsonify(success=False, error="الموظف غير موجود"), 404
            # عيّن الرئيس
            cur.execute("UPDATE departments SET department_head_id=? WHERE id=?", (head_id, dept_id))
            # اجعل دوره department_head إن لم يكن مديراً
            if emp["role"] not in ("manager","admin"):
                cur.execute("UPDATE employees SET role='department_head' WHERE id=?", (head_id,))
        else:
            # إزالة الرئيس
            cur.execute("UPDATE departments SET department_head_id=NULL WHERE id=?", (dept_id,))

        conn.commit()
    return jsonify(success=True)

@departments_bp.delete("/manager/departments/<int:dept_id>")
@login_required
def delete_department(dept_id):
    if not manager_only():
        return jsonify(success=False, error="غير مسموح"), 403
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            used = cur.execute("SELECT COUNT(*) FROM employees WHERE department_id=?", (dept_id,)).fetchone()[0]
            if used:
                return jsonify(success=False, error="لا يمكن الحذف – يوجد موظفون مرتبطون"), 400
            cur.execute("DELETE FROM departments WHERE id=?", (dept_id,))
            if cur.rowcount == 0:
                return jsonify(success=False, error="القسم غير موجود"), 404
            conn.commit()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 400

# قائمة موظفي قسم (مساعدة لاختيار الرئيس)
@departments_bp.get("/manager/departments/<int:dept_id>/employees")
@login_required
def department_employees(dept_id):
    if not manager_only():
        return jsonify(success=False, error="غير مسموح"), 403
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, name, role
              FROM employees
             WHERE department_id=?
             ORDER BY name
        """, (dept_id,)).fetchall()
    return jsonify(success=True, items=[{"id":r["id"],"name":r["name"],"role":r["role"]} for r in rows])