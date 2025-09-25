from datetime import datetime, date
from msd.database.connection import get_conn
from msd.vacations.workflow import can_transition
from msd.vacations.mapping import ONE_TIME_TYPES
from msd.vacations import notifications as vac_notif

# ============= وقت / تواريخ ==============

def _now():
    return datetime.utcnow().isoformat()

def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def _inclusive_days(start_str: str, end_str: str) -> int:
    sd = _parse_date(start_str)
    ed = _parse_date(end_str)
    if ed < sd:
        raise ValueError("تاريخ النهاية قبل البداية")
    return (ed - sd).days + 1

# ============= ميتاداتا الأنواع ==============

def _fetch_type_meta(cur):
    cur.execute("""
        SELECT code, fixed_duration, max_per_request,
               affects_annual_balance, affects_emergency_balance,
               requires_relation, name_ar
        FROM vacation_types
    """)
    meta = {}
    for r in cur.fetchall():
        meta[r["code"]] = {
            "fixed_duration": r["fixed_duration"],
            "max_per_request": r["max_per_request"],
            "aff_annual": r["affects_annual_balance"],
            "aff_emergency": r["affects_emergency_balance"],
            "requires_relation": r["requires_relation"],
            "name_ar": r["name_ar"]
        }
    return meta

# ============= تداخل ==============

def check_overlap(emp_id, start_date, end_date):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) c FROM vacation_requests
            WHERE employee_id=?
              AND status NOT IN ('cancelled','rejected_dept','rejected_manager')
              AND (
                (? BETWEEN start_date AND end_date)
                OR (? BETWEEN start_date AND end_date)
                OR (start_date BETWEEN ? AND ?)
                OR (end_date BETWEEN ? AND ?)
              )
        """, (emp_id, start_date, end_date,
              start_date, end_date, start_date, end_date))
        return cur.fetchone()[0] > 0

# ============= History ==============

def log_history(conn, vacation_request_id, action, from_status=None, to_status=None,
                actor_role=None, actor_user_id=None, note=None):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO vacation_request_history
        (vacation_request_id, action, from_status, to_status,
         actor_role, actor_user_id, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (vacation_request_id, action, from_status, to_status,
          actor_role, actor_user_id, note))
    conn.commit()

# ============= Audit ==============

def _audit(conn, action: str, record_id: int, changes: str, table_name: str = "vacation_requests"):
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_log (action, table_name, record_id, changes, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (action, table_name, record_id, changes))
        conn.commit()
    except Exception:
        pass

# ============= إنشاء طلب ==============

def create_request(employee_id, type_code, start_date, end_date,
                   relation=None, notes=""):
    with get_conn() as conn:
        cur = conn.cursor()
        vt_meta = _fetch_type_meta(cur)
        if type_code not in vt_meta:
            raise ValueError("نوع إجازة غير معروف")
        meta = vt_meta[type_code]

        if meta["requires_relation"] and not relation:
            raise ValueError("يجب تحديد صلة القرابة")

        try:
            _parse_date(start_date); _parse_date(end_date)
        except ValueError:
            raise ValueError("تنسيق تاريخ غير صالح (YYYY-MM-DD)")

        if meta["fixed_duration"]:
            expected_days = meta["fixed_duration"]
            actual_days = _inclusive_days(start_date, end_date)
            if actual_days != expected_days:
                sd = _parse_date(start_date)
                corrected_end = (sd.fromordinal(sd.toordinal() + expected_days - 1)).isoformat()
                end_date = corrected_end
            requested_days = expected_days
        else:
            requested_days = _inclusive_days(start_date, end_date)

        if meta["max_per_request"] and meta["max_per_request"] > 0 and requested_days > meta["max_per_request"]:
            raise ValueError("تجاوزت الحد الأقصى المسموح")

        if type_code in ONE_TIME_TYPES:
            cur.execute("""
                SELECT 1 FROM vacation_requests
                WHERE employee_id=? AND type_code=? AND status='approved'
            """, (employee_id, type_code))
            if cur.fetchone():
                raise ValueError("هذه الإجازة لا تُمنح إلا مرة واحدة")

        if check_overlap(employee_id, start_date, end_date):
            raise ValueError("هناك إجازة متداخلة")

        initial_status = "pending_dept"
        cur.execute("""
            INSERT INTO vacation_requests
            (employee_id, type_code, relation, start_date, end_date,
             requested_days, status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (employee_id, type_code, relation, start_date, end_date,
              requested_days, initial_status, notes, _now()))
        rid = cur.lastrowid
        conn.commit()

        log_history(conn, rid, action="create", from_status=None,
                    to_status=initial_status, actor_role=None,
                    actor_user_id=None, note=f"create {type_code}")
        _audit(conn, "CREATE", rid,
               f"type={type_code} start={start_date} end={end_date} days={requested_days}")

        payload = {
            "id": rid,
            "employee_id": employee_id,
            "type_code": type_code,
            "requested_days": requested_days,
            "start_date": start_date,
            "end_date": end_date,
            "status": initial_status
        }
        if hasattr(vac_notif, "notify_new_request"):
            vac_notif.notify_new_request(payload)
        return rid

# ============= قائمة بسيطة (قديمة) ==============

def list_requests(filters=None):
    """
    يعيد نتائج بدون ترقيم (للتوافق القديم) – الآن يتضمن اسم الموظف.
    """
    filters = filters or {}
    sql = """
      SELECT vr.id, vr.employee_id, e.name AS employee_name,
             vr.type_code, vr.relation, vr.start_date, vr.end_date,
             vr.requested_days, vr.status, vr.notes, vr.created_at,
             vr.rejection_reason
        FROM vacation_requests vr
        LEFT JOIN employees e ON e.id=vr.employee_id
    """
    clauses = []
    params = []
    if "status" in filters:
        clauses.append("vr.status=?")
        params.append(filters["status"])
    if "employee_id" in filters:
        clauses.append("vr.employee_id=?")
        params.append(filters["employee_id"])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY vr.created_at DESC"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

# ============= قائمة مترقمة ==============

def list_requests_paginated(page=1, limit=10, status=None,
                            employee_id=None, type_code=None, q=None):
    page = max(page, 1)
    limit = min(max(limit, 1), 200)
    offset = (page - 1) * limit
    clauses = []
    params = []

    if status:
        clauses.append("vr.status=?")
        params.append(status)
    if employee_id:
        clauses.append("vr.employee_id=?")
        params.append(employee_id)
    if type_code:
        clauses.append("vr.type_code=?")
        params.append(type_code)
    if q:
        like = f"%{q.strip()}%"
        clauses.append("(vr.notes LIKE ? OR vr.relation LIKE ? OR vr.type_code LIKE ? OR e.name LIKE ?)")
        params.extend([like, like, like, like])

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    base = f"""
        FROM vacation_requests vr
        LEFT JOIN employees e ON e.id=vr.employee_id
        {where_sql}
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) {base}", params)
        total = cur.fetchone()[0]
        cur.execute(f"""
            SELECT vr.id, vr.employee_id, e.name AS employee_name,
                   vr.type_code, vr.relation, vr.start_date, vr.end_date,
                   vr.requested_days, vr.status, vr.notes, vr.created_at,
                   vr.rejection_reason
              {base}
             ORDER BY vr.id DESC
             LIMIT ? OFFSET ?
        """, params + [limit, offset])
        items = [dict(r) for r in cur.fetchall()]
    pages = (total + limit - 1) // limit if total else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": pages,
        "limit": limit
    }

# ============= انتقال حالة داخلي ==============

def _update_status(request_id, expected_current, target, actor_role,
                   actor_user_id=None, note=None, rejection_reason=None):
    from msd.balances.service import consume_balance, restore_balance
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
          SELECT id, employee_id, type_code, requested_days, status,
                 start_date, end_date
          FROM vacation_requests WHERE id=?
        """, (request_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("طلب غير موجود")
        rid, emp_id, type_code, days, current, sdate, edate = row
        if current != expected_current or not can_transition(current, target):
            raise ValueError("انتقال غير صالح")

        if target == "approved" and actor_role == "manager":
            consume_balance(emp_id, type_code, days)

        if target == "cancelled" and current == "approved":
            restore_balance(emp_id, type_code, days)

        decision_field = None
        if actor_role == "department_head":
            decision_field = "dept_decision_at"
        elif actor_role == "manager":
            decision_field = "manager_decision_at"

        base_sql = "UPDATE vacation_requests SET status=? {extra} {rej} WHERE id=?"
        extra = f", {decision_field}=?" if decision_field else ""
        rej = ", rejection_reason=?" if rejection_reason is not None else ""
        params = [target]
        if decision_field:
            params.append(_now())
        if rejection_reason is not None:
            params.append(rejection_reason)
        params.append(rid)
        cur.execute(base_sql.format(extra=extra, rej=rej), params)
        conn.commit()

        action_name = _derive_action(current, target, rejection_reason)
        log_history(conn, rid,
                    action=action_name,
                    from_status=current, to_status=target,
                    actor_role=actor_role, actor_user_id=actor_user_id,
                    note=note or rejection_reason)

        desc = f"{current}->{target}"
        if rejection_reason:
            desc += f" reason={rejection_reason}"
        _audit(conn, "TRANSITION", rid, desc)

def _derive_action(current, target, rejection_reason):
    if target.startswith("rejected"):
        return "reject"
    if target == "cancelled":
        return "cancel"
    if current.startswith("pending") and target.startswith("pending"):
        return "advance"
    if target == "approved":
        return "approve"
    return "transition"

# ============= موافقة ==============

def approve(request_id, actor_role, actor_user_id=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
           SELECT id, employee_id, type_code, requested_days,
                  start_date, end_date, status
             FROM vacation_requests WHERE id=?
        """, (request_id,))
        row = cur.fetchone()
    if not row:
        raise ValueError("طلب غير موجود")
    vac_data = dict(row)

    if actor_role == "department_head":
        _update_status(request_id, "pending_dept", "pending_manager", actor_role, actor_user_id)
        if hasattr(vac_notif, "notify_after_dept_approve"):
            vac_notif.notify_after_dept_approve(vac_data)
    elif actor_role == "manager":
        _update_status(request_id, "pending_manager", "approved", actor_role, actor_user_id)
        if hasattr(vac_notif, "notify_manager_approve"):
            vac_notif.notify_manager_approve(vac_data)
    else:
        raise ValueError("دور غير مدعوم")

# ============= رفض ==============

def reject(request_id, actor_role, actor_user_id=None, reason=None):
    if not reason:
        raise ValueError("سبب الرفض مطلوب")

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
           SELECT id, employee_id, type_code, requested_days,
                  start_date, end_date, status
             FROM vacation_requests WHERE id=?
        """, (request_id,))
        row = cur.fetchone()
    if not row:
        raise ValueError("طلب غير موجود")
    vac_data = dict(row)

    if actor_role == "department_head":
        _update_status(request_id, "pending_dept", "rejected_dept", actor_role,
                       actor_user_id, rejection_reason=reason)
        if hasattr(vac_notif, "notify_rejection"):
            vac_notif.notify_rejection(vac_data, reason, "رئيس القسم")
    elif actor_role == "manager":
        _update_status(request_id, "pending_manager", "rejected_manager", actor_role,
                       actor_user_id, rejection_reason=reason)
        if hasattr(vac_notif, "notify_manager_reject"):
            vac_notif.notify_manager_reject(vac_data, reason)
    else:
        raise ValueError("دور غير مدعوم")

# ============= إلغاء ==============

def cancel(request_id, actor_role, actor_user_id=None, note=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
           SELECT id, employee_id, type_code, requested_days,
                  start_date, end_date, status
             FROM vacation_requests WHERE id=?
        """, (request_id,))
        row = cur.fetchone()
    if not row:
        raise ValueError("غير موجود")
    vac_data = dict(row)
    status = row["status"]

    allowed_next = {
        "pending_dept": "cancelled",
        "pending_manager": "cancelled",
        "approved": "cancelled"
    }
    if status not in allowed_next:
        raise ValueError("لا يمكن الإلغاء في هذه الحالة")

    _update_status(request_id, status, "cancelled", actor_role, actor_user_id, note=note)
    if hasattr(vac_notif, "notify_cancel"):
        vac_notif.notify_cancel(vac_data, "رئيس القسم" if actor_role == "department_head" else "المدير")

# ============= السجل التاريخي ==============

def get_history(request_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, action, from_status, to_status,
                   actor_role, actor_user_id, note, created_at
            FROM vacation_request_history
            WHERE vacation_request_id=?
            ORDER BY id ASC
        """, (request_id,))
        rows = cur.fetchall()
        return [dict(r) for r in rows]

# ============= تعديل / حذف طلب ==============

def update_request(request_id: int, actor_role: str, actor_user_id: int,
                   start_date: str = None, end_date: str = None,
                   type_code: str = None, notes: str = None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, employee_id, type_code, start_date, end_date, requested_days, status, notes
              FROM vacation_requests WHERE id=?
        """, (request_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("الطلب غير موجود")
        rid, emp_id, old_type, old_start, old_end, old_days, status, old_notes = row
        if status not in ("pending_dept", "pending_manager"):
            raise ValueError("لا يمكن تعديل طلب بحالته الحالية")
        if actor_role == "department_head" and status != "pending_dept":
            raise ValueError("لا يمكن تعديل الطلب بعد خروجه من القسم")

        new_type = type_code or old_type
        new_start = start_date or old_start
        new_end = end_date or old_end
        try:
            ndays = _inclusive_days(new_start, new_end)
        except ValueError:
            raise ValueError("تواريخ غير صالحة")

        if (new_start != old_start) or (new_end != old_end):
            if check_overlap(emp_id, new_start, new_end):
                raise ValueError("تداخل مع طلب آخر")

        cur.execute("""
            UPDATE vacation_requests
               SET type_code=?, start_date=?, end_date=?, requested_days=?, notes=?
             WHERE id=?
        """, (new_type, new_start, new_end, ndays, notes if notes is not None else old_notes, rid))
        conn.commit()

        log_history(conn, rid, action="edit",
                    from_status=status, to_status=status,
                    actor_role=actor_role, actor_user_id=actor_user_id,
                    note=f"edit start={new_start} end={new_end} type={new_type}")
        return {
            "id": rid,
            "employee_id": emp_id,
            "type_code": new_type,
            "start_date": new_start,
            "end_date": new_end,
            "requested_days": ndays,
            "status": status,
            "notes": notes if notes is not None else old_notes
        }

def hard_delete_request(request_id: int, actor_role: str):
    if actor_role not in ("manager", "admin"):
        raise ValueError("مسموح للمدير فقط")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM vacation_requests WHERE id=?", (request_id,))
        r = cur.fetchone()
        if not r:
            raise ValueError("الطلب غير موجود")
        if r[0] == "approved":
            raise ValueError("لا يمكن حذف طلب معتمد")
        cur.execute("DELETE FROM vacation_requests WHERE id=?", (request_id,))
        conn.commit()
    return True

# ============= الأنواع ==============

def list_vacation_types():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT code, name_ar, fixed_duration, max_per_request,
                   requires_relation, affects_annual_balance, affects_emergency_balance
            FROM vacation_types
            ORDER BY id ASC
        """)
        return [dict(r) for r in cur.fetchall()]