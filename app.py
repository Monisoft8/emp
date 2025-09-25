# هيكل app.py الجديد
from flask import Flask
from auth import auth_bp
from telegram_bot import telegram_bp
from models import db, Employee, LeaveRequest

app = Flask(__name__)
app.config.from_pyfile('config.py')

# تسجيل Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(telegram_bp)

# دمج Routes من الملفات المختلفة
@app.route('/absences')
def absences():
    # دمج منطق absences هنا
    pass

@app.route('/approvals') 
def approvals():
    # دمج منطق approvals هنا
    pass