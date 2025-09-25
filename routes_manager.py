from flask import Blueprint, request, jsonify, send_file
from flask_login import login_required, current_user
from io import BytesIO
from msd.manager import service_manager as svc

manager_api = Blueprint("manager_api", __name__)

def _ensure_role():
    return getattr(current_user, "role", "") in ("manager", "admin")

@manager_api.get("/manager/employees")
@login_required
def list_employees():
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    args = request.args
    data = svc.list_employees(
        page=args.get("page", 1, type=int),
        limit=args.get("limit", 25, type=int),
        search=args.get("search"),
        department_id=args.get("department_id", type=int),
        status=args.get("status"),
        order=args.get("order","name")
    )
    # نرجّع Array مباشرة لتوافق الواجهة (EMPLOYEES.forEach)
    return jsonify(data)

@manager_api.get("/manager/employees/lookup")
@login_required
def lookup_employees():
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    q = request.args.get("search") or request.args.get("q")
    dept = request.args.get("department_id", type=int)
    data = svc.list_employee_names(search=q, department_id=dept)
    return jsonify(data)

@manager_api.get("/manager/employees/<int:eid>")
@login_required
def get_employee(eid):
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    row = svc.get_employee(eid)
    if not row: 
        return jsonify({"error":"not found"}), 404
    return jsonify(row)

@manager_api.post("/manager/employees")
@login_required
def create_employee():
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    data = request.get_json(force=True)
    eid = svc.create_employee(data, actor_id=current_user.id)
    return jsonify({"id": eid, "message":"created"}), 201

@manager_api.put("/manager/employees/<int:eid>")
@login_required
def update_employee(eid):
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    data = request.get_json(force=True)
    svc.update_employee(eid, data, actor_id=current_user.id, actor_role=current_user.role)
    return jsonify({"message":"updated"})

@manager_api.delete("/manager/employees/<int:eid>")
@login_required
def delete_employee(eid):
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    svc.delete_employee(eid, actor_id=current_user.id)
    return jsonify({"message":"deleted"})

@manager_api.get("/manager/employees/<int:eid>/stats")
@login_required
def employee_stats(eid):
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    stats = svc.employee_stats(eid)
    if not stats: 
        return jsonify({"error":"not found"}), 404
    return jsonify(stats)

@manager_api.post("/manager/employees/import")
@login_required
def import_employees():
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    if "file" not in request.files:
        return jsonify({"error":"no file"}), 400
    f = request.files["file"]
    mode = request.form.get("mode") or request.args.get("mode") or "replace"
    report = svc.import_employees_file(f, actor_id=current_user.id, mode=mode)
    return jsonify(report)

@manager_api.get("/manager/employees/export")
@login_required
def export_employees():
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    fmt = request.args.get("format","xlsx")
    df = svc.export_dataframe()
    if fmt == "csv":
        buf = BytesIO()
        buf.write(df.to_csv(index=False).encode("utf-8-sig"))
        buf.seek(0)
        return send_file(buf, as_attachment=True,
                         download_name="employees_export.csv",
                         mimetype="text/csv")
    else:
        xbuf = BytesIO()
        df.to_excel(xbuf, index=False)
        xbuf.seek(0)
        return send_file(xbuf, as_attachment=True,
                         download_name="employees_export.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@manager_api.get("/manager/departments")
@login_required
def list_departments_api():
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    return jsonify(svc.list_departments())

@manager_api.post("/manager/departments")
@login_required
def create_department_api():
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    data = request.get_json(force=True)
    did = svc.create_department(data.get("name"), actor_id=current_user.id)
    return jsonify({"id":did,"message":"created"}), 201

@manager_api.put("/manager/departments/<int:did>")
@login_required
def update_department_api(did):
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    data = request.get_json(force=True)
    svc.update_department(did, data.get("name"), actor_id=current_user.id)
    return jsonify({"message":"updated"})

@manager_api.delete("/manager/departments/<int:did>")
@login_required
def delete_department_api(did):
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    svc.delete_department(did, actor_id=current_user.id)
    return jsonify({"message":"deleted"})

@manager_api.post("/manager/departments/<int:did>/assign-head")
@login_required
def assign_head(did):
    if not _ensure_role(): 
        return jsonify({"error":"forbidden"}), 403
    data = request.get_json(force=True)
    user_id = svc.assign_department_head(
        dept_id=did,
        employee_id=data.get("employee_id"),
        username=data.get("username"),
        password=data.get("password"),
        actor_id=current_user.id
    )
    return jsonify({"user_id":user_id,"message":"assigned"})