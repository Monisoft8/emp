"""
Notifications module (stub / safe).

يوفّر دوال يتم استدعاؤها من service دون إحداث استثناء.
يمكن لاحقاً ربطها بتيليجرام أو بريد.
كل دالة ترجع True في حال مرورها بنجاح ظاهرياً.
"""

from typing import Dict, Any, Optional
import traceback

ENABLED = True  # يمكن تعطيل الإشعارات بدون إزالة الاستدعاءات

def _safe(fn):
    def wrapper(*args, **kwargs):
        if not ENABLED:
            return False
        try:
            return fn(*args, **kwargs)
        except Exception:
            print("[notifications] ERROR in", fn.__name__)
            traceback.print_exc()
            return False
    return wrapper

@_safe
def notify_new_request(vac_req: Dict[str, Any]):
    print(f"[notify] new vacation request #{vac_req.get('id')} emp={vac_req.get('employee_id')}")
    return True

@_safe
def notify_after_dept_approve(vac_req: Dict[str, Any]):
    print(f"[notify] dept approved request #{vac_req.get('id')}")
    return True

@_safe
def notify_manager_approve(vac_req: Dict[str, Any]):
    print(f"[notify] manager approved request #{vac_req.get('id')}")
    return True

@_safe
def notify_rejection(vac_req: Dict[str, Any], reason: str, who: str):
    print(f"[notify] rejection request #{vac_req.get('id')} by {who} reason={reason}")
    return True

@_safe
def notify_manager_reject(vac_req: Dict[str, Any], reason: str):
    print(f"[notify] manager reject request #{vac_req.get('id')} reason={reason}")
    return True

@_safe
def notify_cancel(vac_req: Dict[str, Any], actor_label: str):
    print(f"[notify] cancel request #{vac_req.get('id')} by {actor_label}")
    return True