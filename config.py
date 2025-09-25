import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "employees.db")
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    # يمكن إضافة إعدادات أخرى لاحقاً