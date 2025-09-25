from flask_login import UserMixin

class User(UserMixin):
    """
    يمثل مستخدم النظام ويُستخدم مع Flask-Login.
    """
    def __init__(self, id, username, role, department_id=None, telegram_chat_id=None):
        self.id = id
        self.username = username
        self.role = role
        self.department_id = department_id
        self.telegram_chat_id = telegram_chat_id

    # خصائص مساعدة اختيارية
    @property
    def is_department_head(self):
        return self.role == "department_head"

    @property
    def is_manager(self):
        return self.role == "manager"

    @property
    def is_admin(self):
        return self.role == "admin"