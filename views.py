from flask import Blueprint, render_template
from flask_login import login_required, current_user

service_requests_pages = Blueprint("service_requests_pages", __name__)

@service_requests_pages.get("/manager/service-requests")
@login_required
def service_requests_ui():
    if current_user.role not in ("manager","admin"):
        return "غير مصرح", 403
    return render_template("service_requests.html")