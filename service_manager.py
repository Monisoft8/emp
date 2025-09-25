import re
from datetime import datetime
from msd.database.connection import get_conn
from msd.auth.service import create_user_if_not_exists

# الحقول التي نسمح بتعديلها عبر API
EDITABLE_FIELDS = {
    "serial_number","name","national_id","department_id","job_grade","job_title",
    "hiring_date","grade_date","bonus","vacation_balance","emergency_vacation_balance",
    "work_days","status"
}

DATE_FIELDS = {"hiring_date","grade_date"}
NUMERIC_FIELDS = {"bonus","vacation_balance","emergency_vacation_balance"}

def _now():
    return datetime.utcnow().isoformat()

def _audit(conn, action, record_id, changes, table_name="employees", actor_id=None):
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_log(action, table_name, record_id, changes, created_at)
            VALUES(?,?,?,?,CURRENT_TIMESTAMP)
        """, (action, table_name, record_id,
              (f"[actor={actor_id}] " if actor_id else "") + changes))
        conn.commit()
    except Exception:
        pass

def _normalize_date(val):
    if val is None: return None
    s = str(val).strip()
    if not s or s in ("0","0000-00-00","None","nan"):
        return None
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%Y/%m/%d","%d-%m-%Y","%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    if re.fullmatch(r"\d{4,6}", s):
        try:
            import pandas as pd
            base = datetime(1899,12,30)
            return (base + pd.Timedelta(days=int(s))).date().isoformat()
        except Exception:
            return None
    return None

# ============ موظفون ============

def list_employees(page=1, limit=25, search=None, department_id=None, status=None, order="name"):
    """
    تُرجع List[dict] لواجهة المدير.
    يدعم: page, limit, search, department_id, status, order.
    """
    page = max(int(page or 1), 1)
    limit = min(max(int(limit or 25), 1), 500)
    offset = (page - 1) * limit

    filters = []
    params = []

    if search:
        s = f"%{str(search).strip()}%"
        filters.append("(e.name LIKE ? OR e.serial_number LIKE ?)")
        params.extend([s, s])

    if department_id:
        filters.append("e.department_id = ?")
        params.append(int(department_id))

    if status:
        filters.append("e.status = ?")
        params.append(status)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    order_cols = {
        "name": "e.name",
        "id": "e.id",
        "serial": "e.serial_number",
        "dept": "e.department_id"
    }
    order_by = order_cols.get(order, "e.name")

    sql = f"""
      SELECT
         e.id,
         e.serial_number,
         e.name,
         e.national_id,
         e.department,
         e.department_id,
         COALESCE(e.job_title, e.job_grade) AS job_title,
         e.job_grade,
         COALESCE(e.vacation_balance, 0) AS vacation_balance,
         COALESCE(e.emergency_vacation_balance, e.emergency_balance, 0) AS emergency_vacation_balance,
         COALESCE(e.status,'active') AS status
      FROM employees e
      {where}
      ORDER BY {order_by} ASC
      LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    out = []
    for r in rows:
        out.append({
            "id": r[0],
            "serial_number": r[1],
            "name": r[2],
            "national_id": r[3],
            "department": r[4],
            "department_id": r[5],
            "job_title": r[6],
            "job_grade": r[7],
            "vacation_balance": r[8],
            "emergency_vacation_balance": r[9],
            "status": r[10],
        })
    return out

def get_employee(emp_id: int):
    """
    تُرجع dict ثابتة. تتعامل مع غياب job_title عبر COALESCE إلى job_grade.
    """
    sql = """
      SELECT
        e.id,
        e.serial_number,
        e.name,
        e.national_id,
        e.department,
        e.department_id,
        COALESCE(e.job_title, e.job_grade) AS job_title,
        e.job_grade,
        e.hiring_date,
        e.grade_date,
        e.bonus,
        COALESCE(e.vacation_balance,0) AS vacation_balance,
        COALESCE(e.emergency_vacation_balance, e.emergency_balance, 0) AS emergency_vacation_balance,
        COALESCE(e.work_days,'') AS work_days,
        COALESCE(e.status,'active') AS status
      FROM employees e
      WHERE e.id = ?
    """
    with get_conn() as conn:
        r = conn.execute(sql, (emp_id,)).fetchone()
    if not r:
        return None
    return {
        "id": r[0],
        "serial_number": r[1],
        "name": r[2],
        "national_id": r[3],
        "department": r[4],
        "department_id": r[5],
        "job_title": r[6],
        "job_grade": r[7],
        "hiring_date": r[8],
        "grade_date": r[9],
        "bonus": r[10],
        "vacation_balance": r[11],
        "emergency_vacation_balance": r[12],
        "work_days": r[13],
        "status": r[14],
    }

def _validate_employee_payload(data, partial=False):
    cleaned = {}
    for k, v in (data or {}).items():
        if k in EDITABLE_FIELDS:
            if k in DATE_FIELDS:
                cleaned[k] = _normalize_date(v)
            else:
                cleaned[k] = v
    if not partial:
        for r in ("name","serial_number"):
            if r not in cleaned or not str(cleaned[r]).strip():
                raise ValueError(f"حقل {r} مطلوب")
    return cleaned

def create_employee(data, actor_id=None):
    payload = _validate_employee_payload(data)
    payload.setdefault("status","active")
    with get_conn() as conn:
        cur = conn.cursor()
        if payload.get("national_id"):
            cur.execute("SELECT 1 FROM employees WHERE national_id=?", (payload["national_id"],))
            if cur.fetchone():
                raise ValueError("national_id موجود مسبقاً")
        cur.execute("SELECT 1 FROM employees WHERE serial_number=?", (payload["serial_number"],))
        if cur.fetchone():
            raise ValueError("serial_number موجود مسبقاً")
        cols = list(payload.keys())
        vals = [payload[c] for c in cols]
        cols_sql = ",".join(cols)
        qs = ",".join(["?"]*len(cols))
        cur.execute(f"""
            INSERT INTO employees ({cols_sql}, created_at, updated_at)
            VALUES ({qs}, ?, ?)
        """, vals + [_now(), _now()])
        eid = cur.lastrowid
        conn.commit()
        _audit(conn,"CREATE", eid, f"create employee name={payload.get('name')}", actor_id=actor_id)
        return eid

def update_employee(eid, data, actor_id=None, actor_role=None):
    payload = _validate_employee_payload(data, partial=True)
    if not payload:
        return
    if actor_role not in ("manager","admin"):
        payload.pop("vacation_balance", None)
        payload.pop("emergency_vacation_balance", None)
    with get_conn() as conn:
        cur = conn.cursor()
        if "national_id" in payload and payload["national_id"]:
            cur.execute("SELECT id FROM employees WHERE national_id=? AND id<>?", (payload["national_id"], eid))
            if cur.fetchone():
                raise ValueError("national_id مستخدم لموظف آخر")
        if "serial_number" in payload and payload["serial_number"]:
            cur.execute("SELECT id FROM employees WHERE serial_number=? AND id<>?", (payload["serial_number"], eid))
            if cur.fetchone():
                raise ValueError("serial_number مستخدم لموظف آخر")
        sets = []
        vals = []
        for k,v in payload.items():
            sets.append(f"{k}=?")
            vals.append(v)
        sets.append("updated_at=?")
        vals.append(_now())
        vals.append(eid)
        cur.execute(f"UPDATE employees SET {', '.join(sets)} WHERE id=?", vals)
        if cur.rowcount == 0:
            raise ValueError("الموظف غير موجود")
        conn.commit()
        _audit(conn,"UPDATE", eid, "update fields="+",".join(payload.keys()), actor_id=actor_id)

def delete_employee(eid, actor_id=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM employees WHERE id=?", (eid,))
        if cur.rowcount == 0:
            raise ValueError("غير موجود")
        conn.commit()
        _audit(conn,"DELETE", eid, "delete employee", actor_id=actor_id)

def employee_stats(eid: int):
    emp = get_employee(eid)
    if not emp:
        return None
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT status, COUNT(*) c, IFNULL(SUM(requested_days),0) total_days
              FROM vacation_requests
             WHERE employee_id=?
             GROUP BY status
        """, (eid,))
        vac_stats = {r[0]: {"count": r[1], "days": r[2]} for r in cur.fetchall()}
        approved_days = vac_stats.get("approved", {}).get("days",0)
        cur.execute("""
            SELECT type, COUNT(*) c, IFNULL(SUM(duration),0) durations
              FROM absences
             WHERE employee_id=?
             GROUP BY type
        """, (eid,))
        abs_stats = {r[0]: {"count": r[1], "days_or_duration": r[2]} for r in cur.fetchall()}
    return {
        "employee": {"id": emp["id"], "name": emp["name"], "department_id": emp["department_id"]},
        "vacations": vac_stats,
        "approved_days": approved_days,
        "absences": abs_stats
    }

# ============ إدارة الأقسام ============

def list_departments():
    """
    إرجاع الأقسام مع اسم رئيس القسم (إن وُجد) عبر users.role='department_head' و users.department_id.
    لا حاجة لعمود head_user_id في جدول الأقسام.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT d.id, d.name,
                   u.username AS head_username
              FROM departments d
              LEFT JOIN users u
                     ON u.role='department_head' AND u.department_id = d.id
             ORDER BY d.name
        """)
        rows = cur.fetchall()
        return [{"id": r[0], "name": r[1], "head_username": r[2]} for r in rows]

def create_department(name, actor_id=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم القسم مطلوب")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM departments WHERE name=?", (name,))
        if cur.fetchone():
            raise ValueError("القسم موجود")
        cur.execute("INSERT INTO departments(name) VALUES(?)", (name,))
        did = cur.lastrowid
        conn.commit()
        _audit(conn, "CREATE_DEPT", did, f"create department name={name}", table_name="departments", actor_id=actor_id)
        return did

def update_department(dept_id, name, actor_id=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم القسم مطلوب")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE departments SET name=? WHERE id=?", (name, dept_id))
        if cur.rowcount == 0:
            raise ValueError("القسم غير موجود")
        conn.commit()
        _audit(conn, "UPDATE_DEPT", dept_id, f"update department name={name}", table_name="departments", actor_id=actor_id)

def delete_department(dept_id, actor_id=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM departments WHERE id=?", (dept_id,))
        if cur.rowcount == 0:
            raise ValueError("القسم غير موجود")
        conn.commit()
        _audit(conn, "DELETE_DEPT", dept_id, "delete department", table_name="departments", actor_id=actor_id)

def assign_department_head(dept_id, employee_id, username, password, actor_id=None):
    """
    ينشئ/يحدّث مستخدم بدور department_head ويضبط department_id له على رقم القسم.
    لا يكتب أي شيء داخل جدول الأقسام.
    """
    username = (username or "").strip()
    if not username or not password:
        raise ValueError("اسم مستخدم وكلمة مرور مطلوبة")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM departments WHERE id=?", (dept_id,))
        if not cur.fetchone():
            raise ValueError("القسم غير موجود")
        cur.execute("SELECT id FROM employees WHERE id=?", (employee_id,))
        if not cur.fetchone():
            raise ValueError("الموظف غير موجود")
    user_id = create_user_if_not_exists(
        username=username,
        password=password,
        role="department_head",
        department_id=dept_id
    )
    with get_conn() as conn:
        _audit(conn, "ASSIGN_HEAD", dept_id, f"assign head user={user_id}", table_name="departments", actor_id=actor_id)
    return user_id

# ============ أسماء الموظفين للكومبو ============

def list_employee_names(search=None, department_id=None, limit=200):
    where = []
    params = []
    if department_id:
        where.append("department_id=?")
        params.append(department_id)
    if search:
        like = f"%{str(search).strip()}%"
        where.append("name LIKE ?")
        params.append(like)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT id, name, department_id
          FROM employees
          {where_sql}
         ORDER BY name
         LIMIT ?
    """
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [{"id":r[0], "name":r[1], "department_id":r[2]} for r in rows]

# ============ استيراد / تصدير ============

IMPORT_COLUMNS_MAP = {
    "serial_number":"serial_number",
    "name":"name",
    "national_id":"national_id",
    "department":"department_id",
    "job_grade":"job_grade",
    "job_title":"job_title",
    "hiring_date":"hiring_date",
    "grade_date":"grade_date",
    "bonus":"bonus",
    "vacation_balance":"vacation_balance",
    "emergency_vacation_balance":"emergency_vacation_balance",
    "work_days":"work_days",
    "status":"status"
}

EXPORT_COLUMNS_ORDER = [
    "id","serial_number","name","national_id","department_id","job_grade","job_title",
    "hiring_date","grade_date","bonus","vacation_balance","emergency_vacation_balance","work_days","status",
    "created_at","updated_at"
]

def import_employees_file(file_storage, actor_id=None, mode="replace"):
    import pandas as pd
    filename = (file_storage.filename or "").lower()
    if filename.endswith(".csv"):
        df = pd.read_csv(file_storage)
    else:
        df = pd.read_excel(file_storage)
    df.columns = [str(c).strip() for c in df.columns]

    processed=0; created=0; updated=0; errors=[]
    with get_conn() as conn:
        cur = conn.cursor()
        for idx, row in df.iterrows():
            processed += 1
            try:
                mapped = {}
                for src,dst in IMPORT_COLUMNS_MAP.items():
                    if src in row and not pd.isna(row[src]):
                        val = row[src]
                        if dst in DATE_FIELDS: val = _normalize_date(val)
                        elif isinstance(val, str): val = val.strip()
                        mapped[dst] = val
                if not mapped.get("name") or not mapped.get("serial_number"):
                    raise ValueError("حقل name أو serial_number مفقود")
                if "department_id" in mapped and isinstance(mapped["department_id"], str):
                    try: mapped["department_id"] = int(mapped["department_id"])
                    except ValueError: mapped["department_id"] = None

                cur.execute("SELECT id FROM employees WHERE national_id=?", (mapped.get("national_id"),))
                erow = cur.fetchone()
                if not erow and mapped.get("serial_number"):
                    cur.execute("SELECT id FROM employees WHERE serial_number=?", (mapped.get("serial_number"),))
                    erow = cur.fetchone()

                if erow:
                    eid = erow[0]
                    sets=[]; vals=[]
                    if mode == "replace":
                        for k,v in mapped.items():
                            if k in EDITABLE_FIELDS:
                                sets.append(f"{k}=?"); vals.append(v)
                    elif mode == "merge":
                        cur.execute("SELECT "+",".join(EDITABLE_FIELDS)+" FROM employees WHERE id=?", (eid,))
                        current = cur.fetchone()
                        curr_map = dict(zip(EDITABLE_FIELDS, current)) if current else {}
                        for k,v in mapped.items():
                            if k in EDITABLE_FIELDS and (not curr_map.get(k) or str(curr_map.get(k)).strip()==""):
                                sets.append(f"{k}=?"); vals.append(v)
                    elif mode == "smart":
                        cur.execute("SELECT "+",".join(EDITABLE_FIELDS)+" FROM employees WHERE id=?", (eid,))
                        current = cur.fetchone()
                        curr_map = dict(zip(EDITABLE_FIELDS, current)) if current else {}
                        for k,v in mapped.items():
                            if k not in EDITABLE_FIELDS: continue
                            existing = curr_map.get(k)
                            if not existing or str(existing).strip()=="": sets.append(f"{k}=?"); vals.append(v)
                            else:
                                if k in NUMERIC_FIELDS and v not in (None,""):
                                    sets.append(f"{k}=?"); vals.append(v)
                                if k in DATE_FIELDS and v and not existing:
                                    sets.append(f"{k}=?"); vals.append(v)
                    else:
                        raise ValueError("وضع استيراد غير معروف")
                    if sets:
                        sets.append("updated_at=?"); vals.append(_now())
                        vals.append(eid)
                        cur.execute(f"UPDATE employees SET {', '.join(sets)} WHERE id=?", vals)
                        updated += 1
                        _audit(conn,"IMPORT_UPDATE", eid, f"row={idx} mode={mode}", actor_id=actor_id)
                else:
                    cols=[]; vals=[]
                    for k,v in mapped.items():
                        if k in EDITABLE_FIELDS:
                            cols.append(k); vals.append(v)
                    cols.append("created_at"); vals.append(_now())
                    cols.append("updated_at"); vals.append(_now())
                    cur.execute(f"INSERT INTO employees({','.join(cols)}) VALUES({','.join(['?']*len(vals))})", vals)
                    eid = cur.lastrowid
                    created += 1
                    _audit(conn,"IMPORT_CREATE", eid, f"row={idx}", actor_id=actor_id)
            except Exception as e:
                errors.append({"row": int(idx)+2, "error": str(e)})
        conn.commit()
    return {"processed":processed,"created":created,"updated":updated,"errors":errors,"mode":mode}

def export_dataframe():
    import pandas as pd
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT {', '.join(EXPORT_COLUMNS_ORDER)} FROM employees ORDER BY name")
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=EXPORT_COLUMNS_ORDER)
    return df