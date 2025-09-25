from flask import Blueprint, render_template
from flask_login import login_required

absences_page_bp = Blueprint("absences_page_bp", __name__)

@absences_page_bp.get("/absences")
@login_required
def absences_page():
    return render_template("absences.html")