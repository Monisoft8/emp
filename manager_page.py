from flask import Blueprint, render_template
from flask_login import login_required, current_user

manager_page_bp = Blueprint("manager_page_bp", __name__)

@manager_page_bp.get("/manager")
@login_required
def manager_portal():
    if current_user.role not in ("manager", "admin"):
        return "غير مسموح", 403
    # الصفحة الرئيسية (البوابة) ذات الأزرار الخمسة
    return render_template("manager_portal.html")