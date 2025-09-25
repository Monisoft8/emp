from flask import Blueprint, request, jsonify, send_file
from flask_login import login_required, current_user
from msd.absences import service_absences as svc
from msd.absences import reporting as rpt
from io import BytesIO

absences_api = Blueprint("absences_api", __name__)

@absences_api.get("/absences")
@login_required
def list_absences():
    args = request.args
    data = svc.list_absences(
        page=args.get("page",1,type=int),
        limit=args.get("limit",10,type=int),
        employee_id=args.get("employee_id", type=int),
        type_code=args.get("type"),
        date_from=args.get("from"),
        date_to=args.get("to"),
        search=args.get("q")
    )
    for it in data["items"]:
        it["type_label"] = svc.type_label(it["type"])
    return jsonify(data)

@absences_api.post("/absences")
@login_required
def create_absence():
    data = request.get_json(force=True)
    try:
        rid = svc.create_absence(
            employee_id=data["employee_id"],
            type_code=data["type"],
            single_date=data.get("date"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            notes=data.get("notes")
        )
        return jsonify({"id":rid,"message":"created"}), 201
    except Exception as e:
        return jsonify({"error":str(e)}), 400

@absences_api.get("/absences/<int:aid>")
@login_required
def get_absence(aid):
    row = svc.get_absence(aid)
    if not row:
        return jsonify({"error":"not found"}),404
    row["type_label"] = svc.type_label(row["type"])
    return jsonify(row)

@absences_api.put("/absences/<int:aid>")
@login_required
def update_absence(aid):
    data = request.get_json(force=True)
    try:
        svc.update_absence(
            aid,
            actor_role=current_user.role,
            type_code=data.get("type"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            notes=data.get("notes")
        )
        return jsonify({"message":"updated"})
    except Exception as e:
        return jsonify({"error":str(e)}), 400

@absences_api.delete("/absences/<int:aid>")
@login_required
def delete_absence(aid):
    try:
        svc.delete_absence(aid, current_user.role)
        return jsonify({"message":"deleted"})
    except Exception as e:
        return jsonify({"error":str(e)}), 400

# ------------------ التقارير ------------------

@absences_api.get("/absences/report")
@login_required
def absences_report():
    """
    استرجاع JSON لعرضه في الواجهة.
    بارامترات متوقعة حسب النوع:
      report_type=month&year=2025&month=9
      report_type=range&start_date=2025-09-01&end_date=2025-09-19
      report_type=employee&employee_id=5&start_date=2025-01-01&end_date=2025-09-30 (اختياري start/end)
    """
    rtype = request.args.get("report_type")
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    employee_id = request.args.get("employee_id", type=int)
    try:
        data = rpt.generate_report(
            report_type=rtype,
            year=year,
            month=month,
            start_date=start_date,
            end_date=end_date,
            employee_id=employee_id
        )
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@absences_api.get("/absences/report/export")
@login_required
def absences_report_export():
    """
    تنزيل التقرير (Excel).
    """
    rtype = request.args.get("report_type")
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    employee_id = request.args.get("employee_id", type=int)
    try:
        data = rpt.generate_report(
            report_type=rtype,
            year=year,
            month=month,
            start_date=start_date,
            end_date=end_date,
            employee_id=employee_id
        )
        content, filename, mime = rpt.export_report_to_excel(data)
        bio = BytesIO(content)
        bio.seek(0)
        return send_file(bio, as_attachment=True, download_name=filename, mimetype=mime)
    except Exception as e:
        return jsonify({"error":str(e)}), 400