from flask import Blueprint, render_template
from flask_login import login_required

# اجعل الاسم مطابقاً لما يُستخدم في url_for في index
vacations_page_bp = Blueprint("vacations_page_bp", __name__)

@vacations_page_bp.route("/vacations")
@login_required
def vacations_page():
    return render_template("vacations.html")