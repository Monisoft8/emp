from datetime import datetime

def ensure_iso(date_str: str):
    # مجرد تحقق شكلي
    datetime.strptime(date_str, "%Y-%m-%d")
    return date_str