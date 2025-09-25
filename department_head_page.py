from flask import Blueprint, render_template, redirect
from flask_login import login_required, current_user

department_head_page_bp = Blueprint("department_head_page_bp", __name__)

@department_head_page_bp.get("/dept-head")
@login_required
def dept_head_page():
    # السماح فقط لرئيس القسم
    if getattr(current_user, "role", "") != "department_head":
        if getattr(current_user, "role", "") in ("manager", "admin"):
            return redirect("/manager")
        return redirect("/login")
    return render_template("department_head.html")