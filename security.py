from functools import wraps
from flask import abort
from flask_login import current_user, login_required

def role_required(*allowed_roles):
    """
    استخدمه مع @login_required لحماية المسارات حسب الدور:
    @login_required
    @role_required('manager')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                # لو لم يكن مسجلاً، لن يصل لهذه النقطة عادةً بسبب @login_required
                abort(401)
            if current_user.role not in allowed_roles:
                abort(403)
            return view_func(*args, **kwargs)
        return wrapper
    return decorator