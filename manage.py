import os
import click
from msd import create_app
from msd.vacations.mapping import VACATION_TYPES
from msd.auth.service import create_user_if_not_exists
from msd.balances.accrual import run_monthly_accrual
from msd.balances.reset import reset_emergency_if_needed
from msd.database.connection import get_conn
from msd.database.migrations.runner import run_all_migrations

# ضمان تعرّف Flask CLI على التطبيق
os.environ.setdefault("FLASK_APP", "manage.py")

app = create_app()

@app.cli.command("migrate")
def migrate():
    """تشغيل كل الهجرات."""
    run_all_migrations()
    click.echo("✅ الهجرات اكتملت.")

@app.cli.command("seed-vacation-types")
def seed_vacation_types():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vacation_types (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              code TEXT UNIQUE NOT NULL,
              name_ar TEXT NOT NULL,
              fixed_duration INTEGER,
              max_per_request INTEGER,
              affects_annual_balance INTEGER DEFAULT 0,
              affects_emergency_balance INTEGER DEFAULT 0,
              approval_flow TEXT DEFAULT 'dept_then_manager',
              requires_relation INTEGER DEFAULT 0
            )
        """)
        for vt in VACATION_TYPES:
            cur.execute("""
                INSERT OR IGNORE INTO vacation_types
                (code, name_ar, fixed_duration, max_per_request,
                 affects_annual_balance, affects_emergency_balance,
                 approval_flow, requires_relation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                vt["code"], vt["name_ar"], vt["fixed_duration"],
                vt["max_per_request"], vt["affects_annual_balance"],
                vt["affects_emergency_balance"], vt["approval_flow"],
                vt["requires_relation"]
            ))
        conn.commit()
    click.echo("✅ تم إدخال أنواع الإجازات.")

@app.cli.command("create-dept-head")
@click.option("--username", required=True)
@click.option("--password", required=True)
@click.option("--department", required=True, type=int)
@click.option("--telegram", required=False)
def create_dept_head(username, password, department, telegram):
    """
    إنشاء أو تحديث مستخدم رئيس قسم.
    """
    from msd.auth.service import create_user_if_not_exists
    uid = create_user_if_not_exists(
        username=username,
        password=password,
        role="department_head",
        department_id=department,
        telegram_chat_id=telegram
    )
    click.echo(f"✅ رئيس القسم جاهز id={uid} username={username} department={department}")

def create_manager(username, password):
    create_user_if_not_exists(username=username, password=password, role="manager")
    click.echo("✅ تم إنشاء/تحديث المدير.")

@app.cli.command("accrual-run")
def accrual_run():
    run_monthly_accrual()
    click.echo("✅ تم تنفيذ التراكم.")

@app.cli.command("emergency-reset")
@click.option("--force", is_flag=True, help="تنفيذ رغم عدم حلول أول السنة")
def emergency_reset(force):
    reset_emergency_if_needed(force=force)
    click.echo("✅ فحص/تنفيذ إعادة ضبط الطارئة.")

if __name__ == "__main__":
    # الآن يمكن:
    #   python manage.py migrate
    #   python manage.py seed-vacation-types
    #   python manage.py create-manager --username admin --password 123456
    # أو استخدام: flask migrate (بعد set FLASK_APP=manage.py)
    from flask.cli import main as flask_main
    flask_main()