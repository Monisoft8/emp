# bo.py
from msd import create_app
from msd.auth.service import create_user_if_not_exists

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        create_user_if_not_exists(
            username="dept1",
            password="12345",
            role="department_head",
            department_id=1
        )
        print("تم إنشاء/تحديث dept1")
